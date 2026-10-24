"""Synthetic demonstration data (only when RADSMART_DEMO is on).

Fake patients start courses day by day over the past seven weeks, each
allocated and approved through the same engine calls as a real course. Past
days and today up to `now` are then played out in the digital twin, so the
boards show arrivals, room-in and room-out times, and Insights shows measured
waits. Every patient is flagged as demonstration data.
"""

from __future__ import annotations

import datetime as dt

import numpy as np
from django.db import transaction
from django.utils import timezone

from radsmart.config import TECHNIQUES
from radsmart.scheduler import planning_minutes
from radsmart.simulate import draw_day, simulate
from radsmart.synth import _pick, make_patient
from radsmart.weeks import MIX, mean_course_days

from care.emr.models import Patient

from care_radsmart import engine
from care_radsmart.models import Course, DayPlan, Machine, Session, Triage

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


def _local(day, minutes):
    base = timezone.make_aware(dt.datetime.combine(day, dt.time()))
    return base + dt.timedelta(minutes=float(minutes))


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
    """Fill in what happened on past days, and today up to `now`, from the twin."""
    pred = engine.predictor()
    for day in days:
        sessions = list(Session.objects.filter(facility=facility, date=day, status="scheduled")
                        .select_related("course", "course__patient"))
        if not sessions:
            continue
        patients, sched, _ = engine._engine_day(sessions)
        appt = {pid: (a.machine, a.start) for pid, a in sched.assignments.items()}
        est = planning_minutes(patients, pred)
        draw = draw_day(patients, rng)
        _, rec = simulate(patients, appt, "appointment", est, draw, arrivals="reliable")
        by_id = {str(s.external_id): s for s in sessions}
        for pid, s in by_id.items():
            r = rec.get(pid)
            cutoff = now if day == today else 10 ** 6
            if r is None:
                if pid in draw.noshow and (day < today or appt[pid][1] < now - 60):
                    engine.miss(s, user, "missed", "did not come")
                continue
            if r["arrival"] > cutoff:
                continue
            s.arrived_at = _local(day, r["arrival"])
            s.status = "arrived"
            if r["start"] <= cutoff:
                s.in_room_at, s.status = _local(day, r["start"]), "in_room"
            if r["end"] <= cutoff:
                s.out_at, s.status = _local(day, r["end"]), "done"
            s.save()
    for c in Course.objects.filter(facility=facility, demo=True, status="approved"):
        if not c.sessions.filter(status__in=("scheduled", "arrived", "in_room")).exists():
            c.status = "completed"
            c.save(update_fields=["status"])
    return len(days)
