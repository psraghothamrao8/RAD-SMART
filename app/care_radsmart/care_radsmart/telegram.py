"""Telegram, for demonstrations. Real use sends on WhatsApp.

The patient opens the bot from their page (t.me/<bot>?start=<page token>), and
that chat is linked to the course. Staff then send each message from CARE: the
text in the patient's language and in English, the page link, and the voice
note. The patient answers with buttons (on my way, late, cannot come today,
another part of the day), and the answers go to the same board as the page's.
The bot sends nothing on its own, and nothing but the patient's first name and
times; any other text gets the buttons again.
"""

from __future__ import annotations

import hmac
import json
import logging

import requests
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from radsmart.config import BANDS, fmt

from care_radsmart import messages, sarvam
from care_radsmart.models import Course, Message
from care_radsmart.settings import plugin_settings

log = logging.getLogger(__name__)

API = "https://api.telegram.org"
LATE = (15, 30, 45, 60)
TEXT = {                                         # the bot's own words, besides the page's labels
    "linked": "You will get the department's messages here. Use the buttons to tell the department if you are "
              "on your way, late, cannot come today, or need another daily time.",
    "how_late": "How late will you be?",
    "pick_time": "When would you like to come? Staff will decide and tell you.",
    "page": "Your page, with your times and the check-in code",
    "back": "Back",
    "use_buttons": "Please use the buttons. To talk to someone, please call the department.",
}


class TelegramError(Exception):
    pass


def enabled() -> bool:
    return bool(str(plugin_settings.RADSMART_TELEGRAM_TOKEN or "").strip())


def call(method: str, payload: dict | None = None, files: dict | None = None, timeout: float = 20) -> dict:
    """One Bot API call. Errors never carry the URL, which holds the token."""
    url = f"{API}/bot{str(plugin_settings.RADSMART_TELEGRAM_TOKEN).strip()}/{method}"
    payload = {k: v for k, v in (payload or {}).items() if v is not None}
    try:
        if files:
            data = {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in payload.items()}
            r = requests.post(url, data=data, files=files, timeout=timeout)
        else:
            r = requests.post(url, json=payload, timeout=timeout)
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Telegram %s failed: %s", method, type(exc).__name__)
        raise TelegramError("Telegram could not be reached.") from None
    if not body.get("ok"):
        raise TelegramError(f"Telegram: {body.get('description') or r.status_code}")
    return body["result"]


def username() -> str:
    """The bot's username (from Telegram, kept for a day), or "" if unknown."""
    name = cache.get("radsmart:telegram:username")
    if not name:
        try:
            name = call("getMe", timeout=10)["username"]
        except (TelegramError, KeyError):
            return ""
        cache.set("radsmart:telegram:username", name, 24 * 3600)
    return name


def deep_link(course: Course) -> str:
    """The link that opens the bot and links that chat to this course."""
    if not enabled():
        return ""
    messages.ensure_link(course)
    name = username()
    return f"https://t.me/{name}?start={course.patient_token}" if name else ""


# ------------------------------------------------------------------ words
def _labels(course: Course) -> dict:
    from care_radsmart.patient import LABELS, _bare
    english = {**LABELS, **TEXT}
    got = sarvam.translate_many(list(english.values()), course.language)
    return {k: got.get(v, v) for k, v in english.items()} | {"bare": {k: _bare(got.get(v, v)) for k, v in english.items()}}


def _keyboard(course: Course, t: dict, menu: str = "main") -> dict:
    b, cid = t["bare"], str(course.external_id)

    def button(text, op, arg=""):
        return {"text": text, "callback_data": f"{op}:{cid}:{arg}"}

    if menu == "late":
        rows = [[button(f"{n} {b['min']}", "l", n) for n in LATE], [button(b["back"], "b")]]
    elif menu == "time":
        rows = [[button(b[k], "o", k)] for k in BANDS] + [[button(b["back"], "b")]]
    else:
        rows = [[button(b["on_way"], "w")], [button(b["late"], "L")], [button(b["not_today"], "n")],
                [button(b["other_time"], "O")]]
    return {"inline_keyboard": rows}


def _show(chat: int, message_id, markup: dict | None) -> None:
    """Swap the buttons under a message (Telegram refuses an unchanged set)."""
    try:
        call("editMessageReplyMarkup", {"chat_id": chat, "message_id": message_id, "reply_markup": markup})
    except TelegramError as exc:
        if "not modified" not in str(exc):
            raise


def _today_line(course: Course, t: dict) -> str:
    from care_radsmart.patient import _today
    day, _ = _today()
    s = course.sessions.filter(date=day, status="scheduled").first()
    return f"{t['bare']['today']}: {t['bare']['come_at']} {fmt(s.start - messages._lead(course))}" if s else ""


# ---------------------------------------------------------------- sending
def send(m: Message, link: str) -> None:
    """Send a drafted message to the patient's chat, then its voice note."""
    course = m.course
    if not course.telegram_chat:
        raise TelegramError("The patient has not opened the Telegram link yet.")
    t = _labels(course)
    call("sendMessage", {"chat_id": course.telegram_chat, "text": messages.full_text(m, link),
                         "link_preview_options": {"is_disabled": True},
                         "reply_markup": _keyboard(course, t) if course.status == "approved" else None})
    local = bool(m.local_text) and sarvam.voice_language(m.language) is not None
    audio = sarvam.speak(m.local_text if local else m.text, m.language if local else "English")
    if audio:
        call("sendVoice", {"chat_id": course.telegram_chat}, files={"voice": ("message.mp3", audio, "audio/mpeg")},
             timeout=60)


# ---------------------------------------------------------------- updates
def handle(update: dict) -> None:
    """One update from Telegram (webhook or polling)."""
    if "callback_query" in update:
        _button(update["callback_query"])
        return
    msg = update.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") != "private" or not chat.get("id"):
        return
    text = (msg.get("text") or "").strip()
    if text.startswith("/start"):
        _start(chat["id"], text.partition(" ")[2].strip(), msg.get("from") or {})
        return
    course = Course.objects.filter(telegram_chat=chat["id"], status="approved").order_by("-modified_date").first()
    if course is None:
        call("sendMessage", {"chat_id": chat["id"],
                             "text": "Please open the Telegram link on your radiotherapy page to get your messages here."})
        return
    t = _labels(course)
    call("sendMessage", {"chat_id": chat["id"], "text": t["use_buttons"], "reply_markup": _keyboard(course, t)})


def _start(chat: int, token: str, sender: dict) -> None:
    course = (Course.objects.select_related("patient").filter(patient_token=token, status="approved").first()
              if len(token) >= 16 else None)
    if course is None:
        call("sendMessage", {"chat_id": chat, "text": "This link is not valid. Please ask the department for the "
                                                      "link to your radiotherapy page."})
        return
    Course.objects.filter(pk=course.pk).update(telegram_chat=chat)
    t = _labels(course)
    from care_radsmart.patient import _first_name
    lines = [f"{plugin_settings.RADSMART_DEPARTMENT}", f"{_first_name(course.patient.name)}, {t['linked']}"]
    if today := _today_line(course, t):
        lines.append(today)
    lines.append(f"{t['bare']['page']}: {messages.page_url(course)}")
    call("sendMessage", {"chat_id": chat, "text": "\n\n".join(lines), "link_preview_options": {"is_disabled": True},
                         "reply_markup": _keyboard(course, t)})


def _button(q: dict) -> None:
    from care_radsmart.patient import record_reply
    msg = q.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    op, _, rest = str(q.get("data") or "").partition(":")
    cid, _, arg = rest.partition(":")
    try:
        # A client can send any button data: the course must be linked to this very chat.
        course = Course.objects.select_related("facility", "patient").filter(external_id=cid,
                                                                             telegram_chat=chat).first()
    except (ValidationError, ValueError):
        course = None
    if course is None or not chat:
        call("answerCallbackQuery", {"callback_query_id": q["id"]})
        return
    t = _labels(course)
    menu = {"L": "late", "O": "time", "b": "main"}.get(op)
    if menu:
        call("answerCallbackQuery", {"callback_query_id": q["id"]})
        _show(chat, msg.get("message_id"), _keyboard(course, t, menu))
        return
    kind = {"w": "on_way", "l": "late", "n": "not_today", "o": "other_time"}.get(op)
    if kind is None:
        call("answerCallbackQuery", {"callback_query_id": q["id"]})
        return
    try:
        number = int(arg) if arg and kind == "late" else None
    except ValueError:
        number = None
    band = arg if kind == "other_time" and arg in BANDS else None
    from care_radsmart.patient import _today
    day, _ = _today()
    if kind != "other_time" and not course.sessions.filter(date=day, status="scheduled").exists():
        result, said = "none", t["no_treatment"]
    else:
        result = record_reply(course, kind, minutes=number or 30, band=band, channel="telegram")
        detail = {"late": f": {number or 30} {t['bare']['min']}",
                  "other_time": f": {t['bare'][band]}" if band else ""}.get(kind, "")
        said = {"done": f"{t['bare'][kind]}{detail}\n\n{t['thanks']}", "too_many": t["too_many"]}.get(
            result, t["course_over"] if course.status != "approved" else t["use_buttons"])
    call("answerCallbackQuery", {"callback_query_id": q["id"]})
    _show(chat, msg.get("message_id"), _keyboard(course, t) if course.status == "approved" else None)
    call("sendMessage", {"chat_id": chat, "text": said})


# ----------------------------------------------------------------- webhook
@method_decorator(csrf_exempt, name="dispatch")
class Webhook(View):
    """Updates from Telegram, which sends the secret in a header. Anything
    else is answered as if the address did not exist."""

    def post(self, request):
        secret = str(plugin_settings.RADSMART_TELEGRAM_SECRET or "").encode()
        given = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "").encode()
        if not enabled() or not secret or not hmac.compare_digest(given, secret):
            raise Http404
        try:
            update = json.loads(request.body)
        except ValueError:
            return HttpResponse(status=400)
        try:
            handle(update)
        except Exception:      # Telegram resends an update until it gets a 200: never loop on a bad one
            log.exception("Telegram update %s", update.get("update_id"))
        return HttpResponse("ok")
