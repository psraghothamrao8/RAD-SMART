"""The patient's page: a private link, no login, no app to install.

It shows the patient's times (live, so a breakdown shows at once), the
department's messages in their language with a voice note, and a QR code to
check in at reception. The patient can say they are on the way, running late,
cannot come today, or need another time; staff see it on the board and decide.
Only the first name is shown, and the link opens nothing else.
"""

from __future__ import annotations

import datetime as dt

from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from radsmart.config import fmt

from care_radsmart import engine, sarvam
from care_radsmart.messages import _lead
from care_radsmart.models import Course, Machine, Message, PatientReply, SlotRequest
from care_radsmart.serializers import to_minutes
from care_radsmart.settings import plugin_settings

REPLIES_PER_DAY = 6
LABELS = {
    "title": "Your radiotherapy",
    "today": "Today",
    "come_at": "Please come at",
    "treatment_about": "Treatment at about",
    "new_time": "New time today",
    "no_treatment": "No treatment today",
    "treated": "Treated today. Thank you.",
    "waiting": "You are checked in. Please wait to be called.",
    "in_room": "You are being treated now.",
    "fault": "The treatment machine has a fault. We will send you a message with your time. Please do not leave home until then.",
    "next": "Your next treatments. Please come at these times.",
    "fraction": "Treatment",
    "of": "of",
    "messages": "Messages from the department",
    "listen": "Listen",
    "checkin": "Show this code at reception when you arrive",
    "tell_us": "Tell the department",
    "on_way": "I am on my way",
    "late": "I will be late",
    "min": "minutes",
    "not_today": "I cannot come today",
    "other_time": "I want a different daily treatment time",
    "time": "Time",
    "reason": "Reason (for example, bus time)",
    "send": "Send",
    "thanks": "Thank you. The department has your message. A staff member will decide and tell you.",
    "too_many": "You have sent several messages today. Please call the department.",
    "course_over": "Your course is finished. This page is no longer in use.",
    "english": "English",
    "staff_decide": "Staff decide every change. Nothing changes until they approve it.",
}


def _course(token: str) -> Course:
    if not token or len(token) < 16:
        raise Http404
    c = (Course.objects.select_related("facility", "patient").filter(patient_token=token)
         .exclude(status__in=("draft",)).first())
    if c is None:
        raise Http404
    return c


def _today():
    from care_radsmart.viewsets import clock
    return clock()


def _first_name(name: str) -> str:
    return (name or "").split()[0] if name else ""


@method_decorator(csrf_exempt, name="dispatch")     # the link's token is the only credential
class PatientPage(View):
    def get(self, request, token):
        c = _course(token)
        day, now = _today()
        lang = c.language if request.GET.get("lang") != "en" else "English"
        labels = sarvam.translate_many(list(LABELS.values()), lang)
        t = {k: labels.get(v, v) for k, v in LABELS.items()}
        lead = _lead(c)
        sessions = list(c.sessions.filter(date__gte=day).exclude(status="cancelled").order_by("date", "fraction_no")[:7])
        today = next((s for s in sessions if s.date == day), None)
        machine = Machine.objects.filter(facility=c.facility, code=today.machine).first() if today else None
        upcoming = [{"date": _date(s.date), "time": fmt(s.start - lead), "fraction": s.fraction_no}
                    for s in sessions if s.date > day and s.status in engine.ACTIVE][:5]
        msgs = []
        for m in c.messages.exclude(status="cancelled").order_by("-created_date")[:4]:
            local = m.local_text if lang != "English" and m.local_text else ""
            msgs.append({"id": m.external_id, "text": local or m.text, "english": m.text if local else "",
                         "when": m.created_date, "voice": bool(sarvam.enabled() and sarvam.voice_language(lang))})
        ctx = {
            "t": t, "token": token, "dept": plugin_settings.RADSMART_DEPARTMENT, "name": _first_name(c.patient.name),
            "lang": lang, "html_lang": sarvam.LANGUAGES.get(lang, ("en-IN",))[0].split("-")[0], "own_language": c.language, "show_toggle": c.language != "English",
            "today": None if today is None else {
                "status": today.status, "come": fmt(today.start - lead), "treat": fmt(today.start),
                "moved": today.today_start is not None, "was": fmt(today.planned_start - lead),
                "fraction": today.fraction_no, "fractions": c.fractions,
                "fault": machine is not None and machine.status == "offline" and today.status == "scheduled",
            },
            "upcoming": upcoming, "fractions": c.fractions, "messages": msgs,
            "code": c.checkin_code, "qr": _qr(c.checkin_code), "done": request.GET.get("done"),
            "finished": c.status in ("completed", "cancelled"), "late_choices": (15, 30, 45, 60),
            "demo": c.demo, "query": "?lang=en" if lang == "English" and c.language != "English" else "",
        }
        return render(request, "care_radsmart/patient.html", ctx)

    def post(self, request, token):
        c = _course(token)
        day, _ = _today()
        back = request.path + ("?lang=en&" if request.POST.get("lang") == "en" else "?")
        kind = request.POST.get("kind")
        if c.status != "approved" or kind not in dict(PatientReply.KIND):
            return HttpResponseRedirect(back)
        if PatientReply.objects.filter(course=c, date=day).count() >= REPLIES_PER_DAY:
            return HttpResponseRedirect(back + "done=too_many")
        session = c.sessions.filter(date=day, status__in=engine.ACTIVE).first()
        reply = PatientReply(facility=c.facility, course=c, session=session, date=day, kind=kind,
                             reason=str(request.POST.get("reason") or "")[:300])
        if kind == "late":
            reply.minutes = max(5, min(240, int(request.POST.get("minutes") or 30)))
        if kind == "other_time":
            try:
                reply.wanted = to_minutes(request.POST.get("wanted"))
            except Exception:
                reply.wanted = None
            if reply.wanted is None:
                return HttpResponseRedirect(back)
            from_date = engine.next_treatment_date(day, c.pattern, c.start_date.weekday(), engine.holidays())
            proposal = engine.propose_change(c, from_date, reply.wanted)
            reply.slot_request = SlotRequest.objects.create(
                course=c, from_date=from_date, wanted=reply.wanted, proposal=proposal,
                reason=("Asked by the patient on their page. " + reply.reason)[:500])
        reply.save()
        return HttpResponseRedirect(back + "done=1")


class PatientAudio(View):
    def get(self, request, token, message):
        c = _course(token)
        m = Message.objects.filter(course=c, external_id=message).first()
        if m is None:
            raise Http404
        english = request.GET.get("lang") == "en" or not m.local_text
        audio = sarvam.speak(m.text if english else m.local_text, "English" if english else m.language)
        if audio is None:
            raise Http404
        return HttpResponse(audio, content_type="audio/mpeg", headers={"Cache-Control": "private, max-age=86400"})


def _date(d: dt.date) -> str:
    return d.strftime("%a %d %b").replace(" 0", " ")


def _qr(code: str) -> str:
    if not code:
        return ""
    import segno
    return segno.make(f"RADSMART:{code}", error="m").svg_inline(scale=7, border=2, dark="#0e1a2b")
