"""RAD-SMART API, mounted by CARE at /api/care_radsmart/.

Every request names a facility (query parameter or body) and is checked
against the caller's role in that facility: view, operate (technologists and
doctors) or approve courses (doctors).
"""

import datetime as dt

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from radsmart.config import fmt

from care.emr.models import Patient
from care.facility.models import Facility
from care.security.authorization import AuthorizationController

from care_radsmart import engine, messages, sarvam, telegram
from care_radsmart.models import (Course, DayPlan, Machine, MachineEvent, Message, PatientReply, Session, SlotRequest,
                                  Triage)
from care_radsmart.serializers import (CourseSerializer, MachineSerializer, SlotRequestSerializer,
                                       TriageSerializer, parse_date, to_minutes)
from care_radsmart.settings import plugin_settings

DENIED = {
    "can_view_radsmart": "You do not have access to RAD-SMART in this facility.",
    "can_operate_radsmart": "Only technologists and doctors of this facility can do this.",
    "can_approve_radsmart_course": "Only doctors of this facility can enter or approve a course.",
}


def get_facility(request, value=None) -> Facility:
    fid = value or request.query_params.get("facility") or request.data.get("facility")
    if not fid:
        raise ValidationError({"facility": "This field is required."})
    try:
        return Facility.objects.get(external_id=fid)
    except (Facility.DoesNotExist, ValueError, DjangoValidationError) as exc:
        raise NotFound("Facility not found.") from exc


def require(request, perm, facility):
    if not AuthorizationController.call(perm, request.user, facility):
        raise PermissionDenied(DENIED[perm])


def can(request, perm, facility) -> bool:
    return bool(AuthorizationController.call(perm, request.user, facility))


def clock(request=None):
    """(treatment day, minutes after midnight) now. The day runs past
    midnight, so 00:00-05:59 belongs to the previous day. A demonstration may
    pass `date` and `time` to act as if it were another moment."""
    now = timezone.localtime()
    day, minutes = now.date(), now.hour * 60 + now.minute
    if minutes < 6 * 60:
        day, minutes = day - dt.timedelta(days=1), minutes + 1440
    if plugin_settings.RADSMART_DEMO:
        while day.weekday() >= 5 or day in engine.holidays():   # a demonstration always shows a working day
            day += dt.timedelta(days=1)
    if request is not None:
        day = parse_date(request.data.get("date") or request.query_params.get("date"), day)
        t = request.data.get("time") or request.query_params.get("time")
        if t:
            minutes = to_minutes(t)
    return day, minutes


class ConfigView(APIView):
    """Options for the forms and boards, and what the caller may do."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = None
        if request.query_params.get("facility"):
            facility = get_facility(request)
            require(request, "can_view_radsmart", facility)
        out = engine.options(facility)
        out["enabled"] = bool(plugin_settings.RADSMART_ENABLED)
        out["sarvam"] = sarvam.enabled()
        out["telegram"] = telegram.enabled()
        if facility:
            out["permissions"] = {k: can(request, k, facility) for k in DENIED}
        day, minutes = clock()
        out["today"], out["now"] = day.isoformat(), minutes
        return Response(out)


class MachineViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "external_id"
    queryset = Machine.objects.all()

    def list(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        return Response(MachineSerializer(engine.ensure_machines(facility), many=True).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, external_id=None):
        """Online or offline. Going offline with an expected length today returns
        RAD-SMART's proposed response for approval."""
        machine = self.get_object()
        require(request, "can_operate_radsmart", machine.facility)
        new = request.data.get("status")
        if new not in ("online", "offline"):
            raise ValidationError({"status": "online or offline"})
        expected = int(request.data.get("expected_minutes") or 0)
        if new == "offline" and not 0 < expected <= 48 * 60:
            raise ValidationError({"expected_minutes": "Between 1 minute and 48 hours"})
        note = str(request.data.get("note") or "")[:500]
        day, minutes = clock(request)
        now = timezone.now()
        with transaction.atomic():
            event = MachineEvent.objects.create(machine=machine, status=new, at=now,
                                                expected_minutes=expected or None, note=note,
                                                created_by=request.user, updated_by=request.user)
            machine.status, machine.status_since, machine.status_note = new, now, note
            machine.expected_back = now + dt.timedelta(minutes=expected) if new == "offline" else None
            machine.updated_by = request.user
            machine.save()
            triage = None
            if new == "offline" and Session.objects.filter(facility=machine.facility, date=day,
                                                           machine=machine.code, status__in=engine.ACTIVE).exists():
                Triage.objects.filter(machine=machine, date=day, status="proposed").update(status="superseded")
                proposal = engine.propose_triage(machine.facility, machine, day, minutes, expected)
                triage = Triage.objects.create(facility=machine.facility, machine=machine, event=event, date=day,
                                               fault_start=minutes, expected_minutes=expected, proposal=proposal,
                                               created_by=request.user, updated_by=request.user)
        return Response({"machine": MachineSerializer(machine).data,
                         "triage": TriageSerializer(triage).data if triage else None})


class CourseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    pagination_class = None                  # one facility's list; the boards need all of it
    permission_classes = [IsAuthenticated]
    serializer_class = CourseSerializer
    lookup_field = "external_id"

    def get_queryset(self):
        facility = get_facility(self.request)
        require(self.request, "can_view_radsmart", facility)
        qs = Course.objects.filter(facility=facility).select_related("patient", "approved_by").order_by(
            "-modified_date")
        p = self.request.query_params
        if p.get("status"):
            qs = qs.filter(status__in=p["status"].split(","))
        if p.get("patient"):
            qs = qs.filter(patient__external_id=p["patient"])
        if p.get("q"):
            qs = qs.filter(Q(patient__name__icontains=p["q"]) | Q(hospital_number__icontains=p["q"])
                           | Q(diagnosis__icontains=p["q"]))
        return qs

    def get_object(self):
        try:
            course = Course.objects.select_related("facility", "patient").get(external_id=self.kwargs["external_id"])
        except (Course.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Course not found.") from exc
        require(self.request, "can_view_radsmart", course.facility)
        return course

    def create(self, request):
        facility = get_facility(request)
        require(request, "can_approve_radsmart_course", facility)
        try:
            patient = Patient.objects.get(external_id=request.data.get("patient"))
        except (Patient.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise ValidationError({"patient": "Choose a patient."}) from exc
        known = (patient.encounter_set.filter(facility=facility).exists()
                 or Course.objects.filter(patient=patient, facility=facility).exists()
                 or AuthorizationController.call("can_view_patient_obj", request.user, patient))
        if not known:
            raise PermissionDenied("This patient is not under this facility's care.")
        ser = CourseSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        course = ser.save(facility=facility, patient=patient, created_by=request.user, updated_by=request.user)
        return Response(CourseSerializer(course).data, status=201)

    def partial_update(self, request, external_id=None):
        course = self.get_object()
        require(request, "can_approve_radsmart_course", course.facility)
        if course.status != "draft":
            raise ValidationError("An approved course cannot be edited. Cancel it, or ask for a slot change.")
        ser = CourseSerializer(course, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        ser.save(updated_by=request.user, proposal={})
        return Response(ser.data)

    @action(detail=True, methods=["post"])
    def propose(self, request, external_id=None):
        """New-start and standing slots for the doctor to review (nothing is booked)."""
        course = self.get_object()
        require(request, "can_approve_radsmart_course", course.facility)
        if course.status != "draft":
            raise ValidationError("This course is already approved.")
        start = parse_date(request.data.get("start_date"), course.start_date)
        proposal = engine.propose(course, start, earliest=bool(request.data.get("earliest", True)))
        course.proposal = proposal
        course.save(update_fields=["proposal", "modified_date"])
        return Response(proposal)

    @action(detail=True, methods=["post"])
    def approve(self, request, external_id=None):
        """The doctor approves the course details, constraints and slots."""
        course = self.get_object()
        require(request, "can_approve_radsmart_course", course.facility)
        if course.status != "draft":
            raise ValidationError("This course is already approved.")
        proposal = request.data.get("proposal") or course.proposal
        if not proposal or not proposal.get("ok"):
            raise ValidationError("Ask for a proposal first.")
        chosen = to_minutes(request.data.get("chosen_time")) if request.data.get("chosen_time") else None
        with transaction.atomic():
            engine.approve(course, request.user, proposal, chosen)
            course.refresh_from_db()
            messages.translate_later([messages.for_course(course, request.user, clock()[0])])
        return Response(CourseSerializer(course).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, external_id=None):
        course = self.get_object()
        require(request, "can_approve_radsmart_course", course.facility)
        day, _ = clock()
        with transaction.atomic():
            course.sessions.filter(date__gte=day, status="scheduled").update(status="cancelled")
            course.status, course.updated_by = "cancelled", request.user
            course.save()
        return Response(CourseSerializer(course).data)

    @action(detail=True, methods=["get"])
    def sessions(self, request, external_id=None):
        course = self.get_object()
        rows = course.sessions.exclude(status="cancelled").order_by("date", "fraction_no")
        return Response([{**engine.session_row(s), "date": s.date.isoformat()} for s in rows])

    @action(detail=True, methods=["post"], url_path="slot-request")
    def slot_request(self, request, external_id=None):
        """A patient asks for another standing time from a date: RAD-SMART proposes."""
        course = self.get_object()
        require(request, "can_operate_radsmart", course.facility)
        if course.status != "approved":
            raise ValidationError("Only an approved course has a standing slot.")
        day, _ = clock()
        from_date = parse_date(request.data.get("from_date"), day + dt.timedelta(days=1))
        wanted = to_minutes(request.data.get("wanted"))
        if wanted is None:
            raise ValidationError({"wanted": "Give the time the patient asked for."})
        proposal = engine.propose_change(course, from_date, wanted)
        req = SlotRequest.objects.create(course=course, from_date=from_date, wanted=wanted,
                                         reason=str(request.data.get("reason") or "")[:500], proposal=proposal,
                                         created_by=request.user, updated_by=request.user)
        return Response(SlotRequestSerializer(req).data, status=201)


    @action(detail=True, methods=["get"], url_path="patient-link")
    def patient_link(self, request, external_id=None):
        """The patient's page link and check-in code, to give the patient."""
        course = self.get_object()
        require(request, "can_operate_radsmart", course.facility)
        if course.status == "draft":
            raise ValidationError("The link is made when the course is approved.")
        url = messages.page_url(course, request)
        text = (f"{plugin_settings.RADSMART_DEPARTMENT}: your radiotherapy times, live, and messages from the "
                f"department: {url}")
        from care_radsmart.patient import _qr, qr_svg
        tg = telegram.deep_link(course)
        return Response({"url": url, "code": course.checkin_code, "qr": _qr(course.checkin_code),
                         "whatsapp": messages.whatsapp_url(course, text),
                         "telegram": tg, "telegram_qr": qr_svg(tg) if tg else "",
                         "telegram_linked": bool(course.telegram_chat)})

    @action(detail=True, methods=["post"])
    def explain(self, request, external_id=None):
        """RAD-SMART's reasons for a proposed time in plain words (Sarvam-105B), and
        optionally in the patient's language. Falls back to the engine's reasons."""
        course = self.get_object()
        p = request.data.get("proposal") or course.proposal or {}
        if not p.get("ok"):
            raise ValidationError("Ask for a proposal first.")
        first, standing = p.get("first") or {}, p.get("standing") or {}
        chosen = request.data.get("chosen_time") or standing.get("time")
        if not request.data.get("proposal") and course.status != "draft" and course.slots:
            # An approved course: explain the slot in force, which a doctor may have
            # chosen at approval or changed since on an approved request.
            today = clock()[0].isoformat()
            chosen = fmt(([s for s in course.slots if s["from"] <= today] or course.slots[:1])[-1]["start"])
        lead = int(p.get("report_lead_min") or 20)
        # Clear sentences, no names or numbers that identify the patient.
        facts = {
            "Treatment": f"{engine.TECHNIQUES[course.technique]['label']}, {course.fractions} fractions",
            "Patient needs": ", ".join(engine.flags(course)) or "none recorded",
            "First treatment (new start)": (f"{first.get('date')}, treatment at {first.get('time')}, come at "
                                            f"{first.get('report')}. Department rule: every new start must "
                                            "finish by 17:00") if first else "",
            "Every later treatment": (f"at {chosen} on the {standing.get('machine_name', 'machine')}, come at "
                                      f"{fmt(to_minutes(chosen) - lead)} ({lead} minutes early)") if chosen else "",
            "Engine's reasons": "; ".join(r for r in (p.get("reasons") or []) if not r.startswith("report at")),
        }
        if chosen and standing.get("time") and chosen != standing.get("time"):
            facts["Note"] = (f"the engine recommended {standing.get('time')}; a doctor or technologist chose "
                             f"{chosen} instead")
        text, why_not = sarvam.explain(facts)
        source = sarvam.CHAT_MODEL if text else "engine"
        if not text:
            reasons = "; ".join(p.get("reasons") or [])
            text = reasons[:1].upper() + reasons[1:] + "."
        out = {"text": text, "source": source, "note": why_not, "language": "English", "local_text": None,
               "local_note": ""}
        lang = request.data.get("language")
        if lang and lang != "English":
            local, status, note = sarvam.translate(text, lang)
            out.update(language=lang, local_text=local, local_note=note)
        return Response(out)


class SlotRequestViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    pagination_class = None                  # one facility's list; the boards need all of it
    permission_classes = [IsAuthenticated]
    serializer_class = SlotRequestSerializer
    lookup_field = "external_id"

    def get_queryset(self):
        facility = get_facility(self.request)
        require(self.request, "can_view_radsmart", facility)
        qs = SlotRequest.objects.filter(course__facility=facility).select_related(
            "course", "course__patient").order_by("-created_date")
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def _get(self, request, external_id):
        try:
            req = SlotRequest.objects.select_related("course", "course__facility").get(external_id=external_id)
        except (SlotRequest.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Request not found.") from exc
        require(request, "can_operate_radsmart", req.course.facility)
        if req.status != "proposed":
            raise ValidationError("This request was already decided.")
        return req

    @action(detail=True, methods=["post"])
    def approve(self, request, external_id=None):
        req = self._get(request, external_id)
        start = to_minutes(request.data.get("time")) if request.data.get("time") else \
            (req.proposal.get("standing") or {}).get("start")
        if start is None:
            raise ValidationError("No time to approve.")
        with transaction.atomic():
            engine.apply_change(req.course, req.from_date, start, request.user)
            req.status, req.decided_by, req.decided_at = "approved", request.user, timezone.now()
            req.save()
            messages.translate_later([messages.for_slot_change(req.course, req.from_date, start, request.user,
                                                               clock()[0])])
            PatientReply.objects.filter(slot_request=req, status="open").update(
                status="done", handled_by=request.user, handled_at=timezone.now())
        return Response(SlotRequestSerializer(req).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, external_id=None):
        req = self._get(request, external_id)
        req.status, req.decided_by, req.decided_at = "rejected", request.user, timezone.now()
        req.save()
        PatientReply.objects.filter(slot_request=req, status="open").update(
            status="done", handled_by=request.user, handled_at=timezone.now())
        return Response(SlotRequestSerializer(req).data)


class DayView(APIView):
    """The day's plan for every machine, with the rule checker's result."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        today, now = clock()
        day = parse_date(request.query_params.get("date"), today)
        if plugin_settings.RADSMART_DEMO and day == today:
            from care_radsmart.demo import catch_up
            catch_up(facility, today, now)      # the demonstration patients' day moves on
        out = engine.day_view(facility, day)
        plan = DayPlan.objects.filter(facility=facility, date=day).order_by("-modified_date").first()
        out["approval"] = None if plan is None else {
            "status": plan.status, "by": plan.approved_by.username if plan.approved_by else None,
            "at": plan.approved_at}
        return Response(out)

    def post(self, request):
        """Approve the day's plan (it must pass the checker)."""
        facility = get_facility(request)
        require(request, "can_operate_radsmart", facility)
        day = parse_date(request.data.get("date"), clock()[0])
        check = engine.check_day(facility, day)
        if check["violations"]:
            raise ValidationError({"detail": "The plan breaks a hard rule; it cannot be approved.", "check": check})
        plan, _ = DayPlan.objects.update_or_create(
            facility=facility, date=day, deleted=False,
            defaults={"status": "approved", "check_result": check, "approved_by": request.user,
                      "approved_at": timezone.now(), "updated_by": request.user})
        return Response({"status": plan.status, "check": check})


class SessionViewSet(viewsets.GenericViewSet):
    """What the technologist records at the machine."""

    permission_classes = [IsAuthenticated]
    lookup_field = "external_id"
    queryset = Session.objects.all()
    NEXT = {"arrive": ("scheduled", "arrived", "arrived_at"),
            "room": ("arrived", "in_room", "in_room_at"),
            "done": ("in_room", "done", "out_at")}

    def _session(self, request, external_id):
        try:
            s = Session.objects.select_related("course", "course__patient", "facility").get(external_id=external_id)
        except (Session.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Session not found.") from exc
        require(request, "can_operate_radsmart", s.facility)
        return s

    def _step(self, request, external_id, step):
        s = self._session(request, external_id)
        before, after, field = self.NEXT[step]
        if step == "room" and s.status == "scheduled":   # walked straight in
            s.arrived_at = s.arrived_at or timezone.now()
        elif s.status != before:
            raise ValidationError(f"This session is {s.get_status_display().lower()}.")
        setattr(s, field, timezone.now())
        s.status, s.updated_by = after, request.user
        s.save()
        if after == "done" and not s.course.sessions.filter(status__in=("scheduled", "arrived", "in_room")).exists():
            s.course.status = "completed"
            s.course.save(update_fields=["status", "modified_date"])
        return Response(engine.session_row(s))

    @action(detail=True, methods=["post"])
    def arrive(self, request, external_id=None):
        return self._step(request, external_id, "arrive")

    @action(detail=True, methods=["post"])
    def room(self, request, external_id=None):
        return self._step(request, external_id, "room")

    @action(detail=True, methods=["post"])
    def done(self, request, external_id=None):
        return self._step(request, external_id, "done")

    @action(detail=True, methods=["post"])
    def undo(self, request, external_id=None):
        s = self._session(request, external_id)
        back = {"arrived": ("scheduled", "arrived_at"), "in_room": ("arrived", "in_room_at"),
                "done": ("in_room", "out_at")}
        if s.status not in back:
            raise ValidationError("Nothing to undo.")
        s.status, field = back[s.status]
        setattr(s, field, None)
        s.updated_by = request.user
        s.save()
        return Response(engine.session_row(s))

    @action(detail=True, methods=["post"], url_path="send-home")
    def send_home(self, request, external_id=None):
        """Not treated today (e.g. the oncologist decided after a breakdown): the
        fraction is added at the end of the course, in the standing slot."""
        s = self._session(request, external_id)
        if s.status not in ("scheduled", "arrived"):
            raise ValidationError("Only a patient who has not been treated can be sent home.")
        with transaction.atomic():
            engine.miss(s, request.user, "sent_home", str(request.data.get("note") or "not treated today")[:500])
        s.refresh_from_db()
        return Response(engine.session_row(s))


class TriageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    pagination_class = None                  # one facility's list; the boards need all of it
    permission_classes = [IsAuthenticated]
    serializer_class = TriageSerializer
    lookup_field = "external_id"

    def get_queryset(self):
        facility = get_facility(self.request)
        require(self.request, "can_view_radsmart", facility)
        qs = Triage.objects.filter(facility=facility).select_related("machine").order_by("-created_date")
        if self.request.query_params.get("date"):
            qs = qs.filter(date=parse_date(self.request.query_params["date"]))
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def create(self, request):
        """Re-run the proposal (e.g. the engineer revised the expected length)."""
        facility = get_facility(request)
        require(request, "can_operate_radsmart", facility)
        try:
            machine = Machine.objects.get(facility=facility, external_id=request.data.get("machine"))
        except (Machine.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise ValidationError({"machine": "Choose a machine."}) from exc
        expected = int(request.data.get("expected_minutes") or 0)
        if not 0 < expected <= 48 * 60:
            raise ValidationError({"expected_minutes": "Between 1 minute and 48 hours"})
        day, minutes = clock(request)
        proposal = engine.propose_triage(facility, machine, day, minutes, expected)
        Triage.objects.filter(machine=machine, date=day, status="proposed").update(status="superseded")
        t = Triage.objects.create(facility=facility, machine=machine, date=day, fault_start=minutes,
                                  expected_minutes=expected, proposal=proposal, created_by=request.user,
                                  updated_by=request.user)
        return Response(TriageSerializer(t).data, status=201)

    def _get(self, request, external_id):
        try:
            t = Triage.objects.select_related("facility", "machine").get(external_id=external_id)
        except (Triage.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Proposal not found.") from exc
        require(request, "can_operate_radsmart", t.facility)
        if t.status != "proposed":
            raise ValidationError(f"This proposal is {t.status}.")
        return t

    @action(detail=True, methods=["post"])
    def approve(self, request, external_id=None):
        """Apply the proposal: today's new times, patients sent back (their
        fraction added at the end of the course), new starts moved."""
        t = self._get(request, external_id)
        with transaction.atomic():
            engine.apply_triage(t.proposal, request.user, t.date)
            t.status, t.decided_by, t.decided_at = "approved", request.user, timezone.now()
            t.note = str(request.data.get("note") or "")[:500]
            t.save()
            messages.translate_later(messages.for_triage(t.proposal, request.user, t.date))
        return Response(TriageSerializer(t).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, external_id=None):
        t = self._get(request, external_id)
        t.status, t.decided_by, t.decided_at = "rejected", request.user, timezone.now()
        t.note = str(request.data.get("note") or "")[:500]
        t.save()
        return Response(TriageSerializer(t).data)


class InsightsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        today = clock()[0]
        to = parse_date(request.query_params.get("to"), today)
        frm = parse_date(request.query_params.get("from"), to - dt.timedelta(days=27))
        return Response(engine.insights(facility, frm, to))


class PatientSearchView(APIView):
    """Patients under this facility's care, for the intake form."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        q = request.query_params.get("q", "").strip()
        qs = Patient.objects.filter(Q(encounter__facility=facility) | Q(radsmart_courses__facility=facility)).distinct()
        if request.query_params.get("id"):
            qs = qs.filter(external_id=request.query_params["id"])
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(phone_number__icontains=q))
        return Response([{"id": str(p.external_id), "name": p.name, "gender": p.gender,
                          "age": engine._age(p)} for p in qs.order_by("name")[:20]])


class DemoSeedView(APIView):
    """Fill a demonstration facility with synthetic patients and courses
    (only when RADSMART_DEMO is on)."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not plugin_settings.RADSMART_DEMO:
            raise PermissionDenied("Demonstration data is switched off on this server.")
        facility = get_facility(request)
        require(request, "can_approve_radsmart_course", facility)
        from care_radsmart.demo import seed
        day, minutes = clock(request)
        out = seed(facility, request.user, census=int(request.data.get("census") or 60), today=day, now=minutes)
        out["now"] = fmt(minutes)
        return Response(out, status=201)


class MessageViewSet(viewsets.GenericViewSet):
    """Messages to patients, drafted after a person approved the change. Staff
    send each one (WhatsApp click-to-chat) and mark it sent, or, where the
    patient linked Telegram, the server sends it there."""

    permission_classes = [IsAuthenticated]
    lookup_field = "external_id"
    queryset = Message.objects.all()

    def list(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        qs = (Message.objects.filter(facility=facility).select_related("course", "course__patient", "sent_by")
              .order_by("-created_date"))
        p = request.query_params
        if p.get("course"):
            qs = qs.filter(course__external_id=p["course"])
        elif p.get("date") != "all":
            qs = qs.filter(date=parse_date(p.get("date"), clock()[0]))
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        return Response([messages.row(m, request) for m in qs[:300]])

    def _get(self, request, external_id) -> Message:
        try:
            m = Message.objects.select_related("course", "course__patient", "facility").get(external_id=external_id)
        except (Message.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Message not found.") from exc
        require(request, "can_operate_radsmart", m.facility)
        return m

    @action(detail=True, methods=["post"])
    def sent(self, request, external_id=None):
        m = self._get(request, external_id)
        m.status, m.sent_by, m.sent_at, m.updated_by = "sent", request.user, timezone.now(), request.user
        m.save()
        return Response(messages.row(m, request))

    @action(detail=True, methods=["post"], url_path="send-telegram")
    def send_telegram(self, request, external_id=None):
        """Send to the patient's Telegram chat, with the voice note; the message is then sent."""
        m = self._get(request, external_id)
        if m.status == "cancelled":
            raise ValidationError("This message was cancelled.")
        if not telegram.enabled():
            raise ValidationError("Telegram is not set up on this server.")
        try:
            telegram.send(m, messages.page_url(m.course, request))
        except telegram.TelegramError as exc:
            raise ValidationError(str(exc)) from exc
        m.status, m.sent_by, m.sent_at, m.channel, m.updated_by = (
            "sent", request.user, timezone.now(), "telegram", request.user)
        m.save()
        return Response(messages.row(m, request))

    @action(detail=True, methods=["post"])
    def cancel(self, request, external_id=None):
        m = self._get(request, external_id)
        if m.status == "sent":
            raise ValidationError("This message was already sent.")
        m.status, m.updated_by = "cancelled", request.user
        m.save()
        return Response(messages.row(m, request))

    @action(detail=True, methods=["post"])
    def translate(self, request, external_id=None):
        """Translate again (e.g. Sarvam was unreachable)."""
        m = self._get(request, external_id)
        m.local_status = "pending"
        m.save(update_fields=["local_status", "modified_date"])
        messages.translate_now([m.id])
        m.refresh_from_db()
        return Response(messages.row(m, request))

    @action(detail=True, methods=["get"])
    def audio(self, request, external_id=None):
        """The voice note (Bulbul), for staff to check before sending."""
        m = self._get(request, external_id)
        english = request.query_params.get("lang") == "en" or not m.local_text
        audio = sarvam.speak(m.text if english else m.local_text, "English" if english else m.language)
        if audio is None:
            raise NotFound("No voice note for this language.")
        return HttpResponse(audio, content_type="audio/mpeg")


class ReplyViewSet(viewsets.GenericViewSet):
    """What patients said on their page: on the way, late, cannot come, another time."""

    permission_classes = [IsAuthenticated]
    lookup_field = "external_id"
    queryset = PatientReply.objects.all()

    def list(self, request):
        facility = get_facility(request)
        require(request, "can_view_radsmart", facility)
        day = parse_date(request.query_params.get("date"), clock()[0])
        qs = (PatientReply.objects.filter(facility=facility, date=day)
              .select_related("course", "course__patient", "session", "slot_request", "handled_by")
              .order_by("-created_date"))
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        return Response([reply_row(r) for r in qs])

    @action(detail=True, methods=["post"])
    def done(self, request, external_id=None):
        try:
            r = PatientReply.objects.select_related("facility", "course", "course__patient", "session",
                                                    "slot_request").get(external_id=external_id)
        except (PatientReply.DoesNotExist, ValueError, DjangoValidationError) as exc:
            raise NotFound("Reply not found.") from exc
        require(request, "can_operate_radsmart", r.facility)
        r.status, r.handled_by, r.handled_at, r.updated_by = "done", request.user, timezone.now(), request.user
        r.save()
        return Response(reply_row(r))


def reply_row(r: PatientReply) -> dict:
    return {"id": str(r.external_id), "course": str(r.course.external_id), "patient_name": r.course.patient.name,
            "hospital_number": r.course.hospital_number,
            "session": str(r.session.external_id) if r.session else None,
            "time": fmt(r.session.start) if r.session else None, "kind": r.kind, "label": r.get_kind_display(),
            "minutes": r.minutes, "wanted": fmt(r.wanted) if r.wanted is not None else None, "reason": r.reason,
            "slot_request": str(r.slot_request.external_id) if r.slot_request else None,
            "slot_request_status": r.slot_request.status if r.slot_request else None,
            "status": r.status, "handled_by": r.handled_by.username if r.handled_by else None,
            "channel": r.channel, "created_date": r.created_date}


class CheckInView(APIView):
    """Reception scans the patient's QR code (or types its six letters): the
    patient's session today is marked arrived."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        facility = get_facility(request)
        require(request, "can_operate_radsmart", facility)
        code = str(request.data.get("code") or "").strip().upper().removeprefix("RADSMART:")
        if len(code) != 6:
            raise ValidationError({"code": "The code has six letters."})
        course = (Course.objects.select_related("patient")
                  .filter(facility=facility, checkin_code=code, status="approved").first())
        if course is None:
            raise NotFound("No current course has this code.")
        day, _ = clock()
        s = (Session.objects.select_related("course", "course__patient")
             .filter(course=course, date=day, status__in=engine.ACTIVE).first())
        if s is None:
            raise ValidationError(f"{course.patient.name} has no treatment today.")
        already = s.status != "scheduled"
        if not already:
            s.status, s.arrived_at, s.updated_by = "arrived", timezone.now(), request.user
            s.save()
        PatientReply.objects.filter(course=course, date=day, kind__in=("on_way", "late"), status="open").update(
            status="done", handled_by=request.user, handled_at=timezone.now())
        return Response({**engine.session_row(s), "already": already})
