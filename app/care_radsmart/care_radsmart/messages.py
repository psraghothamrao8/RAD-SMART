"""Messages to patients, and the patient's own page.

A message is drafted only after a person approved the change (a course, a new
standing time, a breakdown response). It is translated into the patient's
language by Sarvam AI, and a technologist sends it with WhatsApp's
click-to-chat link (no paid gateway is needed for the pilot), then marks it
sent. For demonstrations the server can send it on Telegram instead
(telegram.py). Each message carries the link to the patient's page, which shows their
times live, plays the message aloud, and lets them say they are late, cannot
come, or need another time.
"""

from __future__ import annotations

import logging
import secrets
import threading
import urllib.parse

from django.db import close_old_connections, transaction

from radsmart.config import fmt

from care_radsmart import sarvam
from care_radsmart.models import Course, Message, Session
from care_radsmart.settings import plugin_settings

log = logging.getLogger(__name__)

CODE_LETTERS = "ACDEFGHJKMNPQRTUVWXY34679"   # no look-alikes (0/O, 1/I/L, 5/S, 8/B, 2/Z)


# ------------------------------------------------------------ patient link
def ensure_link(course: Course) -> Course:
    """Give the course its page token and check-in code (once)."""
    if course.patient_token and course.checkin_code:
        return course
    if not course.patient_token:
        course.patient_token = secrets.token_urlsafe(18)
    while not course.checkin_code:
        code = "".join(secrets.choice(CODE_LETTERS) for _ in range(6))
        if not Course.objects.filter(facility=course.facility, checkin_code=code).exists():
            course.checkin_code = code
    course.save(update_fields=["patient_token", "checkin_code", "modified_date"])
    return course


def base_url(request=None) -> str:
    url = str(plugin_settings.RADSMART_PUBLIC_URL or "").rstrip("/")
    if not url and request is not None:
        url = request.build_absolute_uri("/").rstrip("/")
    return url


def page_url(course: Course, request=None) -> str:
    ensure_link(course)
    return f"{base_url(request)}/api/care_radsmart/p/{course.patient_token}/"


def whatsapp_url(course: Course, text: str) -> str:
    """WhatsApp click-to-chat: opens a chat with the patient, the text filled in;
    staff press send. On a demonstration server no number is used, so WhatsApp
    asks whom to send it to."""
    phone = "".join(ch for ch in str(getattr(course.patient, "phone_number", "") or "") if ch.isdigit())
    if course.demo or plugin_settings.RADSMART_DEMO or len(phone) < 10:
        phone = ""
    elif len(phone) == 10:
        phone = "91" + phone
    return f"https://wa.me/{phone}?text={urllib.parse.quote(text)}"


# --------------------------------------------------------------- templates
def _dept() -> str:
    return str(plugin_settings.RADSMART_DEPARTMENT or "Radiotherapy department")


def _lead(course: Course) -> int:
    from radsmart.config import DEPARTMENT
    return DEPARTMENT["report_lead_pelvic_min"] if course.site == "PELVIS" else DEPARTMENT["report_lead_min"]


def course_text(course: Course) -> str:
    first = course.first or {}
    slot = (course.slots or [{}])[0]
    lead = _lead(course)
    out = f"{_dept()}: your radiotherapy starts on {_day(first.get('date'))}. Please come at {fmt(first['start'] - lead)}."
    if slot.get("start") is not None and course.fractions > 1:
        out += (f" After the first day, please come at {fmt(slot['start'] - lead)} on every treatment day. "
                "This time stays the same until your course ends.")
    if course.site == "PELVIS":
        out += " Please drink the water as the staff told you, before you come."
    return out


def slot_text(course: Course, from_date, start: int) -> str:
    return (f"{_dept()}: from {_day(from_date.isoformat())}, please come at {fmt(start - _lead(course))} "
            "on every treatment day. This is the new time you asked for.")


def breakdown_text(action: str, report_now: str | None, report_usual: str, next_day: str | None = None,
                   next_report: str | None = None) -> str | None:
    """next_day (ISO) and next_report are known once the change is approved; the
    preview before approval says "the next working day". A named day cannot be
    mistranslated as "next week"."""
    d = _dept()
    when = f"on {_day(next_day)}" if next_day else "on the next working day"
    if action == "new_time":
        return (f"{d}: the treatment machine has a fault. Please come at {report_now} today, "
                f"not at {report_usual}. Please do not leave home before then.")
    if action == "do_not_travel":
        return (f"{d}: the treatment machine is being repaired. Please do not travel today. "
                f"Please come {when} at your usual time, {report_usual}. "
                "The missed treatment is added at the end of your course.")
    if action == "send_home":
        return (f"{d}: the treatment machine is being repaired, so you cannot be treated today. "
                f"Please come {when} at your usual time, {report_usual}. "
                "The missed treatment is added at the end of your course.")
    if action == "start_next_day":
        come = f"Please come at {next_report}." if next_report else "We will tell you the time."
        return f"{d}: the treatment machine has a fault, so your first treatment moves to {_day(next_day) if next_day else 'the next working day'}. {come}"
    return None


def _day(iso: str | None) -> str:
    import datetime as dt
    if not iso:
        return "the planned day"
    d = dt.date.fromisoformat(iso)
    return d.strftime("%A, %d %B").replace(" 0", " ")


# ----------------------------------------------------------------- drafting
def draft(course: Course, kind: str, text: str, day, user, session: Session | None = None, action: str = "") -> Message:
    ensure_link(course)
    return Message.objects.create(facility=course.facility, course=course, session=session, date=day, kind=kind,
                                  action=action, text=text, language=course.language,
                                  local_status="pending" if course.language != "English" else "english",
                                  created_by=user, updated_by=user)


def for_course(course: Course, user, day) -> Message | None:
    if not course.first:
        return None
    return draft(course, "course", course_text(course), day, user)


def for_slot_change(course: Course, from_date, start: int, user, day) -> Message:
    return draft(course, "slot", slot_text(course, from_date, start), day, user)


def for_triage(proposal: dict, user, day) -> list[Message]:
    from care_radsmart.engine import ACTIVE
    out = []
    for a in proposal.get("actions", []):
        if not breakdown_text(a["action"], a.get("new_report"), a["report"]):
            continue
        s = Session.objects.select_related("course", "course__facility", "course__patient").filter(
            external_id=a["id"]).first()
        if s is None:
            continue
        # After approval the patient's next treatment is booked: name its day (and,
        # for a moved new start, its time unless staff still have to choose one).
        nxt = (Session.objects.filter(course=s.course, status__in=ACTIVE, date__gt=day)
               .order_by("date", "fraction_no").first())
        next_report = None
        if a["action"] == "start_next_day" and nxt is not None and "choose a time" not in (nxt.note or ""):
            next_report = fmt(nxt.planned_start - _lead(s.course))
        text = breakdown_text(a["action"], a.get("new_report"), a["report"],
                              nxt.date.isoformat() if nxt else None, next_report)
        out.append(draft(s.course, "breakdown", text, day, user, session=s, action=a["action"]))
    return out


# ---------------------------------------------------------------- translate
def translate_now(ids) -> None:
    for m in Message.objects.filter(id__in=list(ids), local_status="pending"):
        local, status, note = sarvam.translate(m.text, m.language)
        m.local_text, m.local_status, m.local_note = local or "", status, note
        m.save(update_fields=["local_text", "local_status", "local_note", "modified_date"])


def translate_later(messages) -> None:
    """Translate after the transaction commits, off the request thread."""
    ids = [m.id for m in messages if m is not None and m.local_status == "pending"]
    if not ids:
        return

    def run():
        try:
            translate_now(ids)
        except Exception:      # a failed translation leaves the English text to send
            log.exception("translating patient messages")
        finally:
            close_old_connections()

    transaction.on_commit(lambda: threading.Thread(target=run, daemon=True).start())


def full_text(m: Message, link: str) -> str:
    """What the patient receives: their language first, then English for a
    caregiver, then their page link."""
    parts = [m.local_text] if m.local_text else []
    parts.append(m.text)
    parts.append(link)
    return "\n\n".join(parts)


def row(m: Message, request=None) -> dict:
    from care_radsmart import telegram      # telegram uses this module
    link = page_url(m.course, request)
    return {
        "id": str(m.external_id), "course": str(m.course.external_id), "patient_name": m.course.patient.name,
        "hospital_number": m.course.hospital_number, "date": m.date.isoformat(), "kind": m.kind,
        "action": m.action, "language": m.language, "text": m.text, "local_text": m.local_text,
        "local_status": m.local_status, "local_note": m.local_note, "status": m.status,
        "sent_by": m.sent_by.username if m.sent_by else None, "sent_at": m.sent_at,
        "voice": bool(sarvam.enabled() and sarvam.voice_language(m.language)),
        "link": link, "whatsapp": whatsapp_url(m.course, full_text(m, link)), "created_date": m.created_date,
        "channel": m.channel, "telegram": bool(m.course.telegram_chat) and telegram.enabled(),
    }
