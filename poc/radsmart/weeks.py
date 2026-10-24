"""Weeks of treatment with standing slots: today's booking against RAD-SMART.

The department keeps each patient's slot for the whole course (24 Oct 2026),
so a fair test follows courses over weeks, not single days. Starting from an
empty machine, new patients arrive every working day (a Poisson stream sized
so that about `census` patients are on treatment once courses overlap). Each
arrival is booked twice, on the same start date:

  * today's booking: a time drawn from the department's recorded spread of
    appointment times, inside the patient's own window, kept for the course;
    nothing checks that the machine is free (department.book_one);
  * RAD-SMART: a new-start slot before 17:00 and a standing slot that is free
    on every treatment date and leaves the new-start reserve
    (courses.SlotAllocator). When no new-start gap is left that day, the start
    moves to the next working day with one, and both policies use that date.

Once courses overlap fully (after about seven weeks), every evaluation day is
played out in the digital twin under both policies with the same patients and
the same random events (common random numbers).
"""

from __future__ import annotations

import datetime as dt

import numpy as np

from .config import DEPARTMENT, hm
from .courses import Course, SlotAllocator, SlotBook, check_day, day_plan, treatment_dates, working_days
from .department import book_one
from .scheduler import planning_minutes
from .simulate import monte_carlo, summarise
from .synth import ROUTINE_MIX, _pick, make_patient

START = dt.date(2027, 1, 4)          # a Monday; any date works
MIX = {**ROUTINE_MIX, "SBRT": 0.02, "SRT": 0.015, "CSI": 0.01}


def mean_course_days(seed=1, n=3000):
    rng = np.random.default_rng(seed)
    return float(np.mean([make_patient(rng, "X", _pick(rng, MIX), "VERSA", True).total_fx
                          for _ in range(n)]))


def simulate_weeks(predictor, lookup, census=87, n_days=60, eval_from=40, n_rep=15, seed=2026,
                   machine="VERSA"):
    rng = np.random.default_rng(seed)
    book_rng = np.random.default_rng(seed + 1)
    days = [d for _, d in zip(range(n_days), working_days(START))]
    lam = census / mean_course_days()
    book = SlotBook(machines=[machine])
    alloc = SlotAllocator(book, predictor)
    courses, today_time, delays, unplaced = [], {}, [], 0
    k = 0
    for day in days:
        for _ in range(int(rng.poisson(lam))):
            k += 1
            tech = _pick(rng, MIX)
            p = make_patient(rng, f"C{k:04d}", tech, machine, new_start=True)
            p.eligible = [machine]
            c = Course(p, day, p.total_fx, "daily")
            c, a = alloc.earliest_start(c)
            if not a.ok:
                unplaced += 1                 # no start within 15 working days
                continue
            alloc.commit(c, a)
            courses.append(c)
            delays.append((c.start_date - day).days)
            n_day = census
            first = book_one(p, n_day, book_rng)                     # new start (10:00-16:00 today)
            later = book_one(_routine(p), n_day, book_rng)
            today_time[c.pid] = (first, later)

    rows, per_day = [], []
    policies_runs = {"Today's booking": [], "RAD-SMART": []}
    for i, day in enumerate(days[eval_from:]):
        patients, sched, standing = day_plan(day, courses)
        if not patients:
            continue
        check = check_day(day, courses)
        appt_rs = {p.pid: (sched.assignments[p.pid].machine, sched.assignments[p.pid].start) for p in patients}
        appt_today = {p.pid: (machine, today_time[p.pid][0] if p.new_start else today_time[p.pid][1])
                      for p in patients}
        pols = {
            "Today's booking": dict(appt=appt_today, rule="fcfs", estimate=planning_minutes(patients, lookup),
                                    lead=False, arrivals="today"),
            "RAD-SMART": dict(appt=appt_rs, rule="appointment", estimate=planning_minutes(patients, predictor)),
        }
        res, _, _, _ = monte_carlo(patients, pols, n_rep=n_rep, seed=seed + 100 + i)
        for name in pols:
            policies_runs[name] += res[name]
        ends = [a.start + a.planned_minutes for a in sched.assignments.values()]
        per_day.append({"date": day.isoformat(), "patients": len(patients),
                        "new_starts": sum(p.new_start for p in patients),
                        "after_17": sum(a.start >= hm("17:00") for a in sched.assignments.values()),
                        "planned_last_end": max(ends),
                        "new_start_room_min": book.new_start_room(machine, day),
                        "violations": check["violations"],
                        **{f"{n}_{key}": float(np.mean([r[key] for r in res[n]]))
                           for n in pols for key in ("wait_median", "wait_p90", "within_15_pct", "late_60_pct")}})
    summary = summarise(policies_runs)
    return {
        "census_target": census, "arrivals_per_day": round(lam, 2), "days_simulated": n_days,
        "evaluation_days": len(per_day), "replications_per_day": n_rep,
        "courses": len(courses), "arrivals_not_placed": unplaced,
        "start_delay_days_mean": round(float(np.mean(delays)), 2) if delays else 0.0,
        "starts_delayed_pct": round(100 * float(np.mean([x > 0 for x in delays])), 1) if delays else 0.0,
        "patients_per_day_mean": round(float(np.mean([r["patients"] for r in per_day])), 1),
        "patients_per_day_range": [min(r["patients"] for r in per_day), max(r["patients"] for r in per_day)],
        "rule_violations": sum(len(r["violations"]) for r in per_day),
        "summary": summary, "per_day": per_day,
    }


def _routine(p):
    from dataclasses import replace
    return replace(p, fraction_no=2, new_start=False)
