"""Synthetic demonstration data (only when RADSMART_DEMO is on).

Fake patients start courses day by day over the past seven weeks, each
allocated and approved through the same engine calls as a real course. Past
days and today up to `now` are then played out in the digital twin, so the
boards show arrivals, room-in and room-out times, and Insights shows measured
waits. Every patient is flagged as demonstration data.

Today's twin is kept on the sessions, and `catch_up` fills in whatever it says
has happened by now, so a demonstration server's board keeps moving through
the day (and draws the next day's twin when it comes).

A public demonstration can also start the day again at a working hour at any
time (tryout.py): the demonstration clock then runs `shift()` apart from the
real one, until the next reseed. Times are still kept as real moments; the
played-out ones are written that far back, and the app shows them shifted.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from radsmart.config import TECHNIQUES
from radsmart.scheduler import planning_minutes
from radsmart.simulate import draw_day, simulate
from radsmart.synth import _pick, make_patient
from radsmart.weeks import MIX, mean_course_days

from care.emr.models import Patient

from care_radsmart import engine
from care_radsmart.models import Course, DayPlan, DemoClock, Machine, Session, Triage
from care_radsmart.settings import plugin_settings

DIAGNOSES = {
    "HN": ["Carcinoma oropharynx", "Carcinoma larynx", "Carcinoma oral cavity"],
    "PELVIS": ["Carcinoma cervix", "Carcinoma rectum", "Carcinoma prostate", "Carcinoma endometrium"],
    "BREAST": ["Carcinoma breast"],
    "THORAX": ["Carcinoma lung", "Carcinoma oesophagus"],
    "BRAIN": ["Glioma", "Brain metastases"],
    "BONE": ["Bone metastases"],
    "ABDOMEN": ["Carcinoma pancreas", "Liver metastases"],
    "WHOLE_BODY": ["Conditioning before transplant"],
}
DOSE_PER_FX = {"PALL": 3.0, "SBRT": 10.0, "SRT": 6.0, "TBI": 2.0}


SHIFT_KEY = "care_radsmart:demo_shift"


def shift() -> dt.timedelta:
    """How far the demonstration clock runs from the real one: zero unless a visitor
    started the day again at a working hour."""
    if not plugin_settings.RADSMART_DEMO:
        return dt.timedelta(0)
    seconds = cache.get(SHIFT_KEY)
    if seconds is None:
        seconds = DemoClock.objects.values_list("shift", flat=True).first() or 0
        cache.set(SHIFT_KEY, seconds, timeout=60)
    return dt.timedelta(seconds=seconds)


def set_shift(delta: dt.timedelta) -> None:
    seconds = round(delta.total_seconds())
    DemoClock.objects.update_or_create(pk=1, defaults={"shift": seconds})
    cache.set(SHIFT_KEY, seconds, timeout=60)


def _local(day, minutes):
    """The real moment at which the demonstration clock reads `minutes` on `day`."""
    base = timezone.make_aware(dt.datetime.combine(day, dt.time()))
    return base + dt.timedelta(minutes=float(minutes)) - shift()


def _working_days_back(today, n):
    out, d = [], today
    while len(out) < n:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            out.append(d)
    return sorted(out)


def clear(facility):
    """Remove earlier demonstration courses and patients (hard delete), the
    day's breakdown proposals and approvals, and bring the machines back online."""
    Course.objects.filter(facility=facility, demo=True).delete()
    Patient.objects.filter(meta__radsmart_demo=True, radsmart_courses__isnull=True).delete()
    Triage.objects.filter(facility=facility).delete()
    DayPlan.objects.filter(facility=facility).delete()
    Machine.objects.filter(facility=facility).update(status="online", expected_back=None, status_note="")


def seed(facility, user, census=60, today=None, now=None, seed=7, weeks=7) -> dict:
    today = today or timezone.localdate()
    now = now if now is not None else 11 * 60
    rng = np.random.default_rng(seed)
    machine = engine.ensure_machines(facility)[0].code
    clear(facility)
    lam = census / mean_course_days()
    days = _working_days_back(today, weeks * 5) + [today]
    nxt = today
    while len(days) < weeks * 5 + 3:                 # two working days ahead: approved new starts
        nxt += dt.timedelta(days=1)
        if nxt.weekday() < 5:
            days.append(nxt)
    made, failed, k = 0, 0, 0
    for day in days:
        for _ in range(int(rng.poisson(lam))):
            k += 1
            tech = _pick(rng, MIX)
            if machine not in TECHNIQUES[tech]["machines"]:
                continue
            p = make_patient(rng, f"D{k:04d}", tech, machine, new_start=True)
            with transaction.atomic():
                patient = Patient.objects.create(
                    name=f"Demo patient {k:03d}", gender=str(rng.choice(["male", "female"])),
                    year_of_birth=today.year - p.age, blood_group="unknown",
                    meta={"radsmart_demo": True}, created_by=user, updated_by=user)
                course = Course.objects.create(
                    facility=facility, patient=patient, hospital_number=f"DEMO-{k:04d}",
                    diagnosis=str(rng.choice(DIAGNOSES[p.site])),
                    total_dose_gy=round(DOSE_PER_FX.get(tech, 2.67 if tech.startswith("BREAST") and p.total_fx <= 16
                                                        else 2.0) * p.total_fx, 2),
                    fractions=p.total_fx, pattern="daily", technique=tech, site=p.site,
                    mobility=p.mobility, imaging=p.imaging, machines=[machine],
                    checklist={key: True for key, on in (
                        ("mhrc", p.mhrc), ("transport", p.transport), ("inpatient", p.inpatient),
                        ("dormitory", p.dormitory), ("nearby", p.nearby), ("paying", p.paying),
                        ("preferred", p.requested is not None), ("gap_sensitive", p.gap_category == 1)) if on},
                    preferred_time=p.requested, gap_category=p.gap_category, language=p.language,
                    start_date=day, demo=True, created_by=user, updated_by=user)
                proposal = engine.propose(course, day, earliest=True)
                if not proposal["ok"]:
                    course.delete()
                    failed += 1
                    continue
                engine.approve(course, user, proposal)
                made += 1
    played = _play_out(facility, [d for d in days if d <= today], today, now, rng, user)
    return {"courses": made, "not_placed": failed, "days_played": played,
            "today": today.isoformat(), "sessions_today": Session.objects.filter(
                facility=facility, date=today, status__in=engine.ACTIVE).count()}


def _play_out(facility, days, today, now, rng, user) -> int:
    """Fill in what happened on past days, and today up to `now`, from the
    twin. Today's twin is kept on each session for `catch_up`."""
    for day in days:
        sessions = list(Session.objects.filter(facility=facility, date=day, status="scheduled")
                        .select_related("course", "course__patient"))
        twins = _draw(sessions, rng)
        cutoff = now if day == today else 10 ** 6
        for s in sessions:
            twin = twins.get(str(s.external_id))
            if twin is None:
                continue
            if day == today:
                s.meta = {**s.meta, "twin": twin}
            _apply(s, twin, day, cutoff, user)
            if day == today and s.status == "scheduled":
                s.save(update_fields=["meta"])
    _complete(facility)
    return len(days)


def catch_up(facility, today, now) -> int:
    """Fill in today's demonstration sessions up to `now` from the kept twin,
    drawing it first if today has none (the same draw for every caller).
    Sessions staff moved for today are left to staff. Returns how many changed."""
    with transaction.atomic():         # two boards opened at once must not both fill in a session
        sessions = list(Session.objects.select_for_update(of=("self",))
                        .filter(facility=facility, date=today, course__demo=True)
                        .select_related("course", "course__patient", "course__approved_by"))
        return _catch_up(facility, sessions, today, now)


def _catch_up(facility, sessions, today, now) -> int:
    if not sessions:
        return 0
    if not any("twin" in s.meta for s in sessions):
        todo = [s for s in sessions if s.status == "scheduled"]
        twins = _draw(todo, np.random.default_rng(today.toordinal()))
        for s in todo:
            if str(s.external_id) in twins:
                s.meta = {**s.meta, "twin": twins[str(s.external_id)]}
                s.save(update_fields=["meta"])
    changed = 0
    for s in sessions:
        twin = s.meta.get("twin")
        if twin and s.today_start is None and s.status in ("scheduled", "arrived", "in_room"):
            changed += _apply(s, twin, today, now, s.course.approved_by)
    if changed:
        _complete(facility)
    return changed


def _draw(sessions, rng) -> dict:
    """One day in the twin: {session id: {"arrival", "start", "end"}} in minutes,
    or {"noshow": True, "appt": minutes} for a patient who does not come."""
    if not sessions:
        return {}
    patients, sched, _ = engine._engine_day(sessions)
    appt = {pid: (a.machine, a.start) for pid, a in sched.assignments.items()}
    est = planning_minutes(patients, engine.predictor())
    draw = draw_day(patients, rng)
    _, rec = simulate(patients, appt, "appointment", est, draw, arrivals="reliable")
    out = {}
    for pid in appt:
        r = rec.get(pid)
        if r is not None:
            out[pid] = {"arrival": float(r["arrival"]), "start": float(r["start"]), "end": float(r["end"])}
        elif pid in draw.noshow:
            out[pid] = {"noshow": True, "appt": float(appt[pid][1])}
    return out


def _apply(s, twin, day, cutoff, user) -> bool:
    """Move one session on to what the twin says has happened by `cutoff`."""
    if twin.get("noshow"):
        if s.status == "scheduled" and twin["appt"] < cutoff - 60:
            engine.miss(s, user, "missed", "did not come")
            return True
        return False
    before = s.status
    if s.status == "scheduled" and twin["arrival"] <= cutoff:
        s.arrived_at, s.status = _local(day, twin["arrival"]), "arrived"
    if s.status == "arrived" and twin["start"] <= cutoff:
        s.in_room_at, s.status = _local(day, twin["start"]), "in_room"
    if s.status == "in_room" and twin["end"] <= cutoff:
        s.out_at, s.status = _local(day, twin["end"]), "done"
    if s.status == before:
        return False
    s.save()
    return True


def _complete(facility):
    for c in Course.objects.filter(facility=facility, demo=True, status="approved"):
        if not c.sessions.filter(status__in=("scheduled", "arrived", "in_room")).exists():
            c.status = "completed"
            c.save(update_fields=["status"])
