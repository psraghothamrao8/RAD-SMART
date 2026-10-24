"""Bridge between CARE's records and the RAD-SMART engine (the radsmart package).

Everything clinical stays with people: the oncologist enters and approves the
course, and a technologist or oncologist approves every breakdown response.
The engine only proposes times, and an independent checker re-verifies every
hard rule in the day's plan.
"""

from __future__ import annotations

import datetime as dt
import threading
from dataclasses import replace

import numpy as np
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from radsmart.config import DEPARTMENT, GAP_CATEGORIES, PATTERNS, TECHNIQUES, fmt
from radsmart.courses import Course as EngineCourse
from radsmart.courses import SlotAllocator, SlotBook, next_treatment_date, treatment_dates
from radsmart.downtime import ACTION_LABELS
from radsmart.downtime import triage as engine_triage
from radsmart.scheduler import Assignment, Schedule, check_plan
from radsmart.synth import Patient as EnginePatient

from care_radsmart.models import Course, Machine, Session
from care_radsmart.settings import plugin_settings

SITES = {"HN": "Head and neck", "BRAIN": "Brain", "THORAX": "Thorax", "BREAST": "Breast",
         "PELVIS": "Pelvis", "ABDOMEN": "Abdomen", "BONE": "Bone", "WHOLE_BODY": "Whole body"}
MOBILITY = {"walking": "Walking", "wheelchair": "Wheelchair", "stretcher": "Stretcher"}
IMAGING = {"none": "No imaging", "kv": "kV images", "cbct": "Cone-beam CT"}
LANGUAGES = ["Kannada", "Tulu", "Malayalam", "Konkani", "Hindi", "English"]
ACTIVE = ("scheduled", "arrived", "in_room", "done")

# The doctor's priority checklist: every hard rule and soft goal the engine knows.
CHECKLIST = {
    "hard": [
        {"key": "complex", "label": "Complex procedure: senior staff, 10:00-17:00",
         "auto": "Ticked for SBRT, SRT, CSI and TBI"},
        {"key": "mhrc", "label": "Hospice (MHRC) patient: 16:00-17:00 slot, back on the 17:00 bus"},
        {"key": "transport", "label": "Travels by public transport: finish by 21:00"},
        {"key": "abc", "label": "Needs the ABC breath-hold unit (shared with the CT simulator)",
         "auto": "Ticked for breast DIBH"},
        {"key": "breast_board", "label": "Needs the breast board (shared with the CT simulator)",
         "auto": "Ticked for breast techniques"},
        {"key": "time_window", "label": "Must be treated inside a time window (e.g. sedation, chemotherapy)",
         "fields": ["earliest_start", "latest_end"]},
        {"key": "gap_sensitive", "label": "Gap-sensitive radical course (category 1): never proposed "
                                          "for sending back during a breakdown",
         "fields": ["gap_category"]},
    ],
    "soft": [
        {"key": "preferred", "label": "Has a preferred time", "fields": ["preferred_time"]},
        {"key": "paying", "label": "Paying patient: keep the preferred time where possible"},
        {"key": "older", "label": "Older patient (70+): earlier in the day", "auto": "From the patient's age"},
        {"key": "inpatient", "label": "Inpatient: can take a late-evening slot"},
        {"key": "dormitory", "label": "Stays in the hospital dormitory: flexible"},
        {"key": "nearby", "label": "Lives nearby: flexible, can be called in early"},
    ],
    "always": [
        "New starts finish by 17:00",
        "Pelvic patients report 45 min early to drink 500 mL of water",
        "Blood irradiation 13:30-14:00 is kept free",
        "One patient at a time on each machine",
        "The standing slot is kept for the whole course",
    ],
}

_pred, _lock = None, threading.Lock()


def predictor():
    """Duration model (expected, P50, P80 minutes). Trained on the engine's
    synthetic session history until the department's own room-in and room-out
    times (recorded in this plugin) are enough to retrain it."""
    global _pred
    with _lock:
        if _pred is None:
            from radsmart.duration_model import QuantileGBMPredictor
            from radsmart.synth import make_history
            _pred = QuantileGBMPredictor().fit(make_history(n_sessions=12000))
    return _pred


def holidays() -> frozenset:
    out = set()
    for x in str(plugin_settings.RADSMART_HOLIDAYS or "").split(","):
        if x.strip():
            out.add(dt.date.fromisoformat(x.strip()))
    return frozenset(out)


def ensure_machines(facility):
    if not Machine.objects.filter(facility=facility).exists():
        for pair in str(plugin_settings.RADSMART_MACHINES).split(","):
            code, _, name = pair.partition(":")
            code = code.strip().upper()
            if code in DEPARTMENT["machines"]:
                Machine.objects.create(facility=facility, code=code, name=name.strip() or code,
                                       status_since=timezone.now())
    return list(Machine.objects.filter(facility=facility).order_by("code"))


def options(facility=None) -> dict:
    """Everything the intake form and the boards need to know."""
    d = DEPARTMENT
    return {
        "techniques": [{"code": k, "label": v["label"], "complex": v["complex"],
                        "accessories": v["accessories"], "machines": v["machines"],
                        "fractions": v["course"]} for k, v in TECHNIQUES.items()],
        "sites": [{"code": k, "label": v} for k, v in SITES.items()],
        "patterns": [{"code": k, "label": v} for k, v in PATTERNS.items()],
        "mobility": [{"code": k, "label": v} for k, v in MOBILITY.items()],
        "imaging": [{"code": k, "label": v} for k, v in IMAGING.items()],
        "gap_categories": [{"code": k, "label": v} for k, v in GAP_CATEGORIES.items()],
        "languages": LANGUAGES,
        "checklist": CHECKLIST,
        "actions": ACTION_LABELS,
        "day": {"start": d["day_start"], "regular_end": d["regular_end"], "hard_end": d["hard_end"],
                "new_start_latest_end": d["new_start_latest_end"],
                "new_start_reserve_min": d["new_start_reserve_min"],
                "downtime_short_max_min": d["downtime_short_max_min"],
                "blocks": d["machines"]["VERSA"]["blocks"], "urgent_holds": d["urgent_holds"]},
        "machines": [{"id": str(m.external_id), "code": m.code, "name": m.name, "status": m.status}
                     for m in (ensure_machines(facility) if facility else [])],
        "demo": bool(plugin_settings.RADSMART_DEMO),
    }


# ----------------------------------------------------------------- patients
def _age(patient) -> int:
    try:
        return int(patient.age)
    except (TypeError, ValueError):
        return 50


def engine_patient(course: Course, pid=None, fraction_no=1, new_start=True, machine=None) -> EnginePatient:
    ck = course.checklist or {}
    tech = TECHNIQUES[course.technique]
    acc = list(tech["accessories"])
    for key, name in (("abc", "ABC"), ("breast_board", "BREAST_BOARD")):
        if ck.get(key) and name not in acc:
            acc.append(name)
    transport = bool(ck.get("transport"))
    latest = course.latest_end if ck.get("time_window") else None
    if transport:
        latest = min(latest or 10 ** 6, DEPARTMENT["public_transport_latest_end"])
    eligible = [m for m in (course.machines or tech["machines"]) if m in DEPARTMENT["machines"]]
    return EnginePatient(
        pid=pid or str(course.external_id), technique=course.technique, site=course.site,
        machine=machine or (eligible[0] if eligible else "VERSA"), fraction_no=fraction_no,
        total_fx=course.fractions, new_start=new_start,
        complex=tech["complex"] or bool(ck.get("complex")), accessories=acc,
        mobility=course.mobility, imaging=course.imaging, age=_age(course.patient),
        inpatient=bool(ck.get("inpatient")), mhrc=bool(ck.get("mhrc")),
        dormitory=bool(ck.get("dormitory")), nearby=bool(ck.get("nearby")), transport=transport,
        latest_end=latest if latest and latest < 10 ** 6 else None,
        earliest_start=course.earliest_start if ck.get("time_window") else None,
        paying=bool(ck.get("paying")), requested=course.preferred_time,
        usual_time=course.preferred_time or 0, language=course.language,
        gap_category=course.gap_category, eligible=eligible or ["VERSA"],
    )


def flags(course: Course) -> list[str]:
    ck, p = course.checklist or {}, engine_patient(course)
    out = [label for key, label in (("mhrc", "MHRC"), ("transport", "public transport"),
                                    ("inpatient", "inpatient"), ("dormitory", "dormitory"),
                                    ("nearby", "lives nearby"), ("paying", "paying")) if ck.get(key)]
    if p.complex:
        out.append("complex")
    if p.elderly:
        out.append("older")
    if p.pelvic:
        out.append("full bladder")
    out += [{"ABC": "ABC", "BREAST_BOARD": "breast board"}[a] for a in p.accessories]
    if course.gap_category == 1:
        out.append("gap-sensitive")
    return out


# --------------------------------------------------------------- slot book
def build_book(facility, from_date, exclude_course=None) -> SlotBook:
    machines = [m.code for m in ensure_machines(facility)]
    book = SlotBook(machines=machines)
    qs = (Session.objects.filter(facility=facility, date__gte=from_date, status__in=ACTIVE)
          .select_related("course", "course__patient"))
    if exclude_course is not None:
        qs = qs.exclude(course=exclude_course)
    acc = {}
    for s in qs:
        if s.machine not in machines:
            continue
        if s.course_id not in acc:
            acc[s.course_id] = engine_patient(s.course).accessories
        book.hold(str(s.course.external_id), s.machine, s.date, s.start, s.planned_minutes, acc[s.course_id])
    return book


def _slot(machine, start, minutes):
    return {"machine": machine, "machine_name": DEPARTMENT["machines"][machine]["label"],
            "start": int(round(start)), "time": fmt(start), "minutes": round(float(minutes), 1)}


def _allocate(course: Course, start_date, earliest=True, wanted=None):
    book = build_book(course.facility, start_date, exclude_course=course)
    alloc = SlotAllocator(book, predictor())
    p = engine_patient(course)
    if wanted is not None:
        p = replace(p, requested=int(wanted), paying=True)
    c = EngineCourse(p, start_date, course.fractions, course.pattern)
    c.dates = treatment_dates(start_date, course.fractions, course.pattern, holidays())
    if earliest:
        c, a = alloc.earliest_start(c, holidays())
    else:
        a = alloc.allocate(c)
    return c, a, alloc, p


def proposal_json(c, a, p) -> dict:
    out = {"ok": a.ok, "problem": a.problem, "start_date": c.start_date.isoformat(),
           "end_date": c.dates[-1].isoformat() if c.dates else None, "treatment_days": len(c.dates),
           "report_lead_min": p.report_lead, "reasons": list(dict.fromkeys(a.reasons)), "first": None, "standing": None,
           "standing2": None, "alternatives": []}
    if a.first:
        m, day, st, mins = a.first
        out["first"] = {**_slot(m, st, mins), "date": day.isoformat(), "report": fmt(st - p.report_lead)}
    if a.standing:
        out["standing"] = {**_slot(*a.standing), "report": fmt(a.standing[1] - p.report_lead)}
    if a.standing2:
        out["standing2"] = {**_slot(*a.standing2), "report": fmt(a.standing2[1] - p.report_lead)}
    for alt in a.alternatives:
        m, st = alt[0], alt[1]
        out["alternatives"].append({**_slot(m, st, a.standing[2] if a.standing else 0),
                                    "note": alt[3] if len(alt) > 3 else ""})
    return out


def propose(course: Course, start_date=None, earliest=True) -> dict:
    c, a, _, p = _allocate(course, start_date or course.start_date, earliest)
    return proposal_json(c, a, p)


def _lock_facility(facility):
    from care.facility.models import Facility
    Facility.objects.select_for_update().get(pk=facility.pk)     # one allocation at a time


@transaction.atomic
def approve(course: Course, user, proposal: dict, chosen_start=None) -> dict:
    """Commit the proposal the doctor saw. If the timetable changed meanwhile
    (another course was approved), nothing is written and the new proposal is
    returned for another look."""
    _lock_facility(course.facility)
    start = dt.date.fromisoformat(proposal["start_date"])
    c, a, alloc, p = _allocate(course, start, earliest=False, wanted=chosen_start)
    fresh = proposal_json(c, a, p)
    if not a.ok:
        raise ValidationError({"detail": a.problem, "proposal": fresh})
    standing = (fresh["standing"] or {}).get("start")
    if chosen_start is not None:          # the doctor picked one of the alternatives
        same = standing == int(chosen_start)
    else:
        same = fresh["first"] == proposal.get("first") and standing == (proposal.get("standing") or {}).get("start")
    if not same:
        raise ValidationError({"detail": "The timetable changed while this was open. Please review the updated "
                                         "proposal.", "proposal": fresh})
    alloc.commit(c, a)
    course.first = {**fresh["first"]} if fresh["first"] else {}
    course.first_minutes = c.first_minutes
    course.minutes = c.minutes
    course.slots = [{"from": f.isoformat(), "machine": m, "start": int(s), "start2": int(s2) if s2 else None}
                    for f, m, s, s2 in c.slots]
    course.dates = [x.isoformat() for x in c.dates]
    course.start_date = c.start_date
    course.proposal = fresh
    course.status = "approved"
    course.approved_by, course.approved_at = user, timezone.now()
    course.updated_by = user
    course.save()
    Session.objects.filter(course=course).update(deleted=True)
    for day in c.dates:
        for s in c.sessions_on(day):
            Session.objects.create(course=course, facility=course.facility, date=day,
                                   fraction_no=s["fraction"], kind="new_start" if s["kind"] == "new_start"
                                   else "routine", machine=s["machine"], planned_start=int(round(s["start"])),
                                   planned_minutes=s["minutes"], created_by=user, updated_by=user)
    return fresh


# -------------------------------------------------------------- slot change
def propose_change(course: Course, from_date, wanted: int) -> dict:
    book = build_book(course.facility, from_date)
    alloc = SlotAllocator(book, predictor())
    c = _engine_course(course)
    a = alloc.change_slot(c, from_date, wanted)
    out = proposal_json(c, a, replace(c.patient, requested=wanted))
    out["first"] = None
    out["from_date"] = from_date.isoformat()
    out["wanted"] = fmt(wanted)
    return out


@transaction.atomic
def apply_change(course: Course, from_date, start: int, user):
    """Move every scheduled fraction from from_date to the approved standing time."""
    _lock_facility(course.facility)
    book = build_book(course.facility, from_date, exclude_course=course)
    alloc = SlotAllocator(book, predictor())
    p = engine_patient(course)
    later = [s for s in course.sessions.filter(date__gte=from_date, status="scheduled") if s.kind != "new_start"]
    if not later:
        raise ValidationError("No scheduled fractions from that date.")
    machine = later[0].machine
    steps = {d: set(alloc.free_steps(p, machine, d, course.minutes)) for d in {s.date for s in later}}
    k = book.idx(start)
    if any(k not in free for free in steps.values()):
        raise ValidationError("That time is no longer free on every remaining date. Ask for a new proposal.")
    for s in later:
        s.planned_start, s.today_start, s.kind = start, None, "routine"
        s.note = f"standing slot changed to {fmt(start)} at the patient's request"
        s.updated_by = user
        s.save()
    course.slots = [x for x in course.slots if x["from"] < from_date.isoformat()] + [
        {"from": from_date.isoformat(), "machine": machine, "start": int(start), "start2": None}]
    course.save(update_fields=["slots", "modified_date"])


def _engine_course(course: Course) -> EngineCourse:
    c = EngineCourse(engine_patient(course), course.start_date, course.fractions, course.pattern)
    c.dates = [dt.date.fromisoformat(x) for x in course.dates] or treatment_dates(
        course.start_date, course.fractions, course.pattern, holidays())
    if course.first:
        c.first = (course.first["machine"], course.first["start"])
        c.first_minutes = course.first_minutes
    c.slots = [(dt.date.fromisoformat(s["from"]), s["machine"], s["start"], s.get("start2"))
               for s in course.slots]
    c.minutes = course.minutes
    return c


# ---------------------------------------------------------------- day view
def _engine_day(sessions):
    """Engine patients and a Schedule for the checker, one per session."""
    patients, rows, standing = [], {}, {}
    for s in sessions:
        pid = str(s.external_id)
        p = engine_patient(s.course, pid=pid, fraction_no=s.fraction_no,
                           new_start=s.kind == "new_start", machine=s.machine)
        patients.append(p)
        rows[pid] = Assignment(pid, s.machine, float(s.start), s.planned_minutes, [])
        if s.kind == "routine" and s.today_start is None:
            standing[pid] = (s.machine, float(s.planned_start))
    return patients, Schedule(rows, "published", 0.0, 0.0, 0, 0, None), standing


def check_day(facility, day) -> dict:
    """The hard rules on the plan for patients still to be treated (to come or
    waiting). Treated and in-room sessions are what happened: a day running
    late is not a broken plan."""
    sessions = list(Session.objects.filter(facility=facility, date=day, status__in=("scheduled", "arrived"))
                    .select_related("course", "course__patient"))
    if not sessions:
        return {"rules_checked": 0, "violations": [], "sessions_checked": 0, "unplanned": []}
    patients, sched, standing = _engine_day(sessions)
    return check_plan(patients, sched, DEPARTMENT, standing=standing)


def session_row(s: Session) -> dict:
    c, p = s.course, s.course.patient
    lead = DEPARTMENT["report_lead_pelvic_min"] if c.site == "PELVIS" else DEPARTMENT["report_lead_min"]
    return {
        "id": str(s.external_id), "course": str(c.external_id), "patient": str(p.external_id),
        "patient_name": p.name, "hospital_number": c.hospital_number, "age": _age(p),
        "diagnosis": c.diagnosis, "technique": TECHNIQUES[c.technique]["label"],
        "fraction": s.fraction_no, "fractions": c.fractions, "kind": s.kind, "machine": s.machine,
        "start": s.start, "time": fmt(s.start), "planned_start": s.planned_start,
        "planned_time": fmt(s.planned_start), "moved_today": s.today_start is not None,
        "report": fmt(s.start - lead), "minutes": round(s.planned_minutes, 1), "status": s.status,
        "arrived_at": s.arrived_at, "in_room_at": s.in_room_at, "out_at": s.out_at,
        "flags": flags(c), "language": c.language, "gap_category": c.gap_category, "note": s.note,
        "demo": c.demo,
    }


def day_view(facility, day) -> dict:
    sessions = list(Session.objects.filter(facility=facility, date=day)
                    .exclude(status="cancelled").select_related("course", "course__patient")
                    .order_by("machine", "today_start", "planned_start"))
    sessions.sort(key=lambda s: (s.machine, s.start))
    machines = ensure_machines(facility)
    active = [s for s in sessions if s.status in ACTIVE]
    book = build_book(facility, day)
    per_machine = {}
    for m in machines:
        mine = [s for s in active if s.machine == m.code]
        per_machine[m.code] = {
            "sessions": len(mine), "new_starts": sum(s.kind == "new_start" for s in mine),
            "after_17": sum(s.start >= DEPARTMENT["new_start_latest_end"] for s in mine),
            "last_end": fmt(max((s.start + s.planned_minutes for s in mine), default=DEPARTMENT["day_start"])),
            "booked_min": round(sum(s.planned_minutes for s in mine)),
            "new_start_room_min": round(book.new_start_room(m.code, day)),
        }
    return {"date": day.isoformat(), "sessions": [session_row(s) for s in sessions],
            "machines": [{"id": str(m.external_id), "code": m.code, "name": m.name, "status": m.status,
                          "status_since": m.status_since, "expected_back": m.expected_back,
                          "note": m.status_note, **per_machine.get(m.code, {})} for m in machines],
            "check": check_day(facility, day),
            "counts": {k: sum(s.status == k for s in sessions) for k, _ in Session.STATUS}}


# ------------------------------------------------------------- breakdowns
def _status_for_triage(s: Session) -> str:
    return {"done": "done", "in_room": "in_room", "arrived": "waiting"}.get(s.status, "not_arrived")


def propose_triage(facility, machine: Machine, day, fault_start: int, expected: int) -> dict:
    sessions = list(Session.objects.filter(facility=facility, date=day, machine=machine.code,
                                           status__in=ACTIVE).select_related("course", "course__patient"))
    if not sessions:
        raise ValidationError("Nobody is booked on this machine that day.")
    patients, sched, _ = _engine_day(sessions)
    plan = {pid: (a.machine, a.start, a.planned_minutes) for pid, a in sched.assignments.items()}
    status = {str(s.external_id): _status_for_triage(s) for s in sessions}
    tr = engine_triage(patients, plan, status, (machine.code, fault_start, expected))
    by_id = {str(s.external_id): s for s in sessions}
    actions = []
    for a in sorted(tr.actions, key=lambda x: (x["new_start"] is None, x["new_start"] or x["planned"])):
        s = by_id[a["pid"]]
        row = session_row(s)
        new = a["new_start"]
        actions.append({**{k: row[k] for k in ("id", "patient_name", "hospital_number", "fraction",
                                                 "fractions", "time", "report", "flags", "language",
                                                 "gap_category", "kind")},
                        "action": a["action"], "label": ACTION_LABELS[a["action"]],
                        "new_start": int(round(new)) if new is not None else None,
                        "new_time": fmt(new) if new is not None else None,
                        "new_report": fmt(new - _report_minutes(row)) if new is not None else None,
                        "present": a["present"], "why": a["why"],
                        "message": _message(a["action"], row, new, s, day)})
    done = [s for s in sessions if s.status in ("done", "in_room")]
    return {
        "machine": machine.code, "machine_name": machine.name, "date": day.isoformat(),
        "fault_start": fault_start, "fault_time": fmt(fault_start), "expected_minutes": expected,
        "restart": fmt(tr.restart) if tr.restart is not None else None,
        "back_today": tr.restart is not None, "rule": tr.rule,
        "allowed_end": fmt(tr.allowed_end), "minutes_to_free": tr.minutes_to_free,
        "overtime_min": tr.overtime_min, "counts": tr.counts(), "already_treated": len(done),
        "actions": actions, "check": tr.check, "solve_seconds": round(tr.solve_seconds, 1),
    }


def _report_minutes(row) -> int:
    h, m = row["time"].split(":")
    rh, rm = row["report"].split(":")
    return ((int(h) * 60 + int(m)) - (int(rh) * 60 + int(rm))) % 1440


def _message(action, row, new, s, day) -> str | None:
    """Draft text for the patient (sent only after approval; translated into the
    patient's language by the Sarvam copilot when it is connected)."""
    if action == "new_time":
        later = new > row["start"]
        return (f"Radiotherapy: today's timetable has changed after a machine fault. Please report at "
                f"{fmt(new - _report_minutes(row))} today instead of {row['report']}."
                + (" Please do not set out before then." if later else ""))
    if action == "do_not_travel":
        return ("Radiotherapy: the treatment machine is being repaired. Please do not travel today. "
                f"Your next treatment is on the next working day at your usual time, {row['report']}. "
                "Today's treatment is added at the end of your course.")
    if action == "send_home":
        return ("The machine is being repaired, so today's treatment cannot be given. Please come at your "
                f"usual time, {row['report']}, on the next working day. Today's treatment is added at the end "
                "of your course.")
    if action == "start_next_day":
        return "Radiotherapy: your first treatment moves to the next working day. We will confirm the time."
    return None


@transaction.atomic
def apply_triage(proposal: dict, user, day):
    for a in proposal["actions"]:
        s = Session.objects.select_related("course").get(external_id=a["id"])
        if s.status not in ACTIVE:
            continue
        s.updated_by = user
        if a["action"] in ("treat_later", "new_time") and a["new_start"] is not None:
            s.today_start = a["new_start"]
            s.note = f"breakdown: moved to {a['new_time']} for today"
            s.save()
        elif a["action"] == "treat" and a["new_start"] is not None and a["new_start"] != s.start:
            s.today_start = a["new_start"]                # a shift under 5 min: nobody is told
            s.save()
        elif a["action"] in ("send_home", "do_not_travel"):
            miss(s, user, "sent_home", "breakdown: sent back; fraction added at the end of the course")
        elif a["action"] == "start_next_day":
            postpone_new_start(s, user)
        elif a["action"] == "doctor_decides":
            s.note = "breakdown: flagged for the oncologist (gap-sensitive or hospice patient)"
            s.save()


def _renumber_after(s: Session):
    """Fractions after a missed one move up by one (delivered in order)."""
    later = (Session.objects.filter(course=s.course, status__in=ACTIVE)
             .filter(date__gt=s.date) | Session.objects.filter(course=s.course, status__in=ACTIVE,
                                                                date=s.date, fraction_no__gt=s.fraction_no))
    for x in later.distinct():
        x.fraction_no -= 1
        x.save(update_fields=["fraction_no", "modified_date"])


def append_fraction(course: Course, user, note="") -> Session:
    """Add one fraction after the last treatment date, in the standing slot if
    it is free that day, else at the nearest free time that day."""
    last = course.sessions.filter(status__in=ACTIVE).order_by("-date", "-fraction_no").first()
    after = last.date if last else course.start_date
    day = next_treatment_date(after, course.pattern, course.start_date.weekday(), holidays())
    slot = course.slots[-1] if course.slots else {"machine": course.first.get("machine", "VERSA"),
                                                   "start": course.first.get("start", DEPARTMENT["day_start"])}
    book = build_book(course.facility, day, exclude_course=course)
    alloc = SlotAllocator(book, predictor())
    start = alloc._nearest_free(engine_patient(course), slot["machine"], day, course.minutes, slot["start"])
    if start is None:
        start = slot["start"]
    s = Session.objects.create(course=course, facility=course.facility, date=day, fraction_no=course.fractions,
                               kind="added" if start == slot["start"] else "moved", machine=slot["machine"],
                               planned_start=int(start), planned_minutes=course.minutes or 10.0,
                               note=note, created_by=user, updated_by=user)
    course.dates = sorted(set(course.dates) | {day.isoformat()})
    course.save(update_fields=["dates", "modified_date"])
    return s


def miss(s: Session, user, status="sent_home", note=""):
    s.status, s.note, s.updated_by = status, note, user
    s.save()
    _renumber_after(s)
    append_fraction(s.course, user, note="added after a missed fraction")


def postpone_new_start(s: Session, user):
    """The first fraction moves to the next treatment day, before 17:00; the
    course gains one day at the end."""
    s.status, s.note, s.updated_by = "postponed", "breakdown: new start moved to the next working day", user
    s.save()
    nxt = (Session.objects.filter(course=s.course, status="scheduled", date__gt=s.date)
           .order_by("date", "fraction_no").first())
    _renumber_after(s)
    if nxt is not None:
        nxt.refresh_from_db()
        course = s.course
        book = build_book(course.facility, nxt.date, exclude_course=course)
        alloc = SlotAllocator(book, predictor())
        p = engine_patient(course)
        ns = replace(p, fraction_no=1, new_start=True)
        starts, _ = alloc._candidates(ns, nxt.machine, [nxt.date], course.first_minutes, reserve=False)
        if starts:
            cost = [(alloc._cost(ns, book.t0 + k * book.g, course.first_minutes), k) for k in starts]
            nxt.planned_start = int(book.t0 + min(cost)[1] * book.g)
            nxt.note = "new start (moved after a breakdown)"
        else:
            nxt.note = "new start moved here: no gap before 17:00, choose a time"
        nxt.kind, nxt.planned_minutes, nxt.fraction_no = "new_start", course.first_minutes, 1
        nxt.updated_by = user
        nxt.save()
        course.first = {**course.first, "date": nxt.date.isoformat(), "start": nxt.planned_start,
                        "time": fmt(nxt.planned_start)}
        course.save(update_fields=["first", "modified_date"])
    append_fraction(s.course, user, note="added after a postponed new start")


# ---------------------------------------------------------------- insights
def _minutes_of(when, day) -> float:
    local = timezone.localtime(when)
    m = local.hour * 60 + local.minute + local.second / 60
    if local.date() > day:
        m += 1440 * (local.date() - day).days
    return m


def insights(facility, date_from, date_to) -> dict:
    """Waits and punctuality measured from the times technologists record:
    the pilot's own evidence, replacing every simulated number."""
    qs = Session.objects.filter(facility=facility, date__gte=date_from, date__lte=date_to)
    timed = [s for s in qs.filter(arrived_at__isnull=False, in_room_at__isnull=False)]
    waits = np.array([(s.in_room_at - s.arrived_at).total_seconds() / 60 for s in timed])
    late = np.array([_minutes_of(s.in_room_at, s.date) - s.start for s in timed])
    by_day = {}
    for s, w, l in zip(timed, waits, late):
        by_day.setdefault(s.date.isoformat(), []).append((w, l))
    series = [{"date": k, "n": len(v), "wait_median": round(float(np.median([x[0] for x in v])), 1),
               "wait_p90": round(float(np.percentile([x[0] for x in v], 90)), 1),
               "within_15_pct": round(100 * float(np.mean([abs(x[1]) <= 15 for x in v])), 1)}
              for k, v in sorted(by_day.items())]
    stat = (lambda f: round(float(f), 1)) if len(timed) else (lambda f: None)
    dur = [(s.out_at - s.in_room_at).total_seconds() / 60 for s in timed if s.out_at]
    return {
        "from": date_from.isoformat(), "to": date_to.isoformat(), "sessions_timed": len(timed),
        "wait_median": stat(np.median(waits)) if len(timed) else None,
        "wait_p90": stat(np.percentile(waits, 90)) if len(timed) else None,
        "within_15_pct": stat(100 * np.mean(np.abs(late) <= 15)) if len(timed) else None,
        "late_60_pct": stat(100 * np.mean(late > 60)) if len(timed) else None,
        "session_minutes_median": round(float(np.median(dur)), 1) if dur else None,
        "sent_home": qs.filter(status="sent_home").count(),
        "postponed": qs.filter(status="postponed").count(),
        "added": qs.filter(kind__in=["added"]).count(),
        "by_day": series,
        "kpi": {"name": "90th-percentile wait, arrival to treatment room",
                "baseline_min": 108.6, "target_min": round(108.6 * 0.75, 1),
                "baseline_source": "the department's records, Oct-Dec 2024"},
    }
