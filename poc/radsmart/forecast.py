"""Machine-occupancy forecast and new-start recommendations.

Every patient on treatment has a known number of remaining fractions, so the
department's committed machine-minutes for the coming weeks are already known.
This module projects that load per machine per working day and recommends how
many new patients can start on each day (decided about two days ahead, as the
problem statement asks) without pushing any future day over capacity.

New patients are allocated to the eligible machine with the most free minutes
over their course: balancing predicted minutes, not head-counts. Machine
eligibility itself is a physics/clinical input and is never changed here.

Total body irradiation (TBI) is known about a month ahead and takes two long
fractions a day for a few days. Its minutes are taken off those days'
capacity, so new starts whose courses would overlap the TBI days are held back
by exactly as much as needed, instead of a rule-of-thumb taper.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .config import DEPARTMENT, TECHNIQUES, TBI_PLAN
from .synth import ROUTINE_MIX, available_minutes, make_patient, _pick


@dataclass
class Candidate:
    pid: str
    technique: str
    ready_day: int          # first working day the plan is approved
    total_fx: int
    first_min: float        # predicted minutes, first fraction
    routine_min: float      # predicted minutes, later fractions
    eligible: list


def committed_load(patients, predictor, horizon, machines):
    """Minutes already committed per machine per future day (day 0 = tomorrow)."""
    later = [replace(p, fraction_no=max(2, p.fraction_no), new_start=False) for p in patients]
    minutes = predictor.predict_many(later, "mean")
    load = {m: np.zeros(horizon) for m in machines}
    completing = {m: np.zeros(horizon, dtype=int) for m in machines}
    for p, mins in zip(patients, minutes):
        rem = p.total_fx - p.fraction_no
        for k in range(min(rem, horizon)):
            load[p.machine][k] += mins
        if 0 < rem <= horizon:
            completing[p.machine][rem - 1] += 1
    return load, completing


def make_pipeline(predictor, days, seed=5, rate=5.0, machines=("VERSA",)):
    """Patients whose plans will be approved over the coming days (synthetic)."""
    rng = np.random.default_rng(seed)
    mix = dict(ROUTINE_MIX)
    mix.update({"SBRT": 0.03, "CSI": 0.02})
    out = []
    for day in range(days):
        for _ in range(rng.poisson(rate)):
            tech = _pick(rng, mix)
            eligible = [m for m in TECHNIQUES[tech]["machines"] if m in machines]
            p1 = make_patient(rng, f"N{len(out) + 1:03d}", tech, eligible[0], new_start=True)
            p2 = replace(p1, fraction_no=2, new_start=False)
            f, r = predictor.predict_many([p1, p2], "mean")
            out.append(Candidate(p1.pid, tech, day, p1.total_fx, float(f), float(r), eligible))
    return out


def daily_capacity(machine):
    d = DEPARTMENT
    reserve = sum(h["minutes"] for h in d["urgent_holds"] if h["machine"] == machine)
    return available_minutes(machine) * d["target_utilisation"] - reserve


def capacity_profile(machine, horizon, tbi_days=()):
    """Capacity per working day, less the TBI slots on TBI days."""
    cap = np.full(horizon, daily_capacity(machine))
    if machine == TBI_PLAN["machine"]:
        for k in tbi_days:
            if 0 <= k < horizon:
                cap[k] -= len(TBI_PLAN["slots"]) * TBI_PLAN["fraction_min"]
    return cap


def recommend(load, candidates, horizon, machines, lookahead=15, decide_from=2, cap=None):
    """Greedy rolling-horizon admission: start each ready patient on the first
    day (>= decide_from) on which an eligible machine keeps every day of the
    next `lookahead` days under capacity. Returns plan and resulting load.
    cap: machine -> capacity per day (defaults to the flat daily capacity)."""
    load = {m: v.copy() for m, v in load.items()}
    cap = cap or {m: np.full(horizon, daily_capacity(m)) for m in machines}
    starts = {m: np.zeros(horizon, dtype=int) for m in machines}
    plan = {}
    queue = sorted(candidates, key=lambda c: c.ready_day)
    for day in range(decide_from, horizon):
        for c in list(queue):
            if c.ready_day > day:
                continue
            best, best_free = None, None
            for m in c.eligible:
                span = range(day, min(horizon, day + min(c.total_fx, lookahead)))
                add = [c.first_min if k == day else c.routine_min for k in span]
                free = min(cap[m][k] - load[m][k] - a for k, a in zip(span, add))
                if free >= 0 and (best_free is None or free > best_free):
                    best, best_free = m, free
            if best is None:
                continue
            for i, k in enumerate(range(day, min(horizon, day + c.total_fx))):
                load[best][k] += c.first_min if i == 0 else c.routine_min
            starts[best][day] += 1
            plan[c.pid] = (best, day)
            queue.remove(c)
    waiting = {c.pid: horizon - c.ready_day for c in queue}
    by_id = {c.pid: c for c in candidates}
    delay = [d - max(by_id[pid].ready_day, decide_from) for pid, (_, d) in plan.items()]
    return plan, starts, load, waiting, delay


def naive(load, candidates, horizon, machines, headcount=None, taper=None, taper_max=2):
    """Current practice: start every patient as soon as the plan is ready, and
    share new patients between machines by head-count (equal numbers), which
    the problem statement warns against. taper = (first, last) working day in
    which at most `taper_max` new patients start per day (the manual cut-back
    before TBI); the others wait for the next day with room."""
    load = {m: v.copy() for m, v in load.items()}
    starts = {m: np.zeros(horizon, dtype=int) for m in machines}
    count = dict(headcount or {m: 0 for m in machines})
    queue = sorted(candidates, key=lambda c: c.ready_day)
    delay = []
    for day in range(2, horizon):
        today = [c for c in queue if c.ready_day <= day]
        if taper and taper[0] <= day <= taper[1]:
            today = today[:taper_max]
        for c in today:
            m = min(c.eligible, key=lambda mm: count[mm])
            count[m] += 1
            for i, k in enumerate(range(day, min(horizon, day + c.total_fx))):
                load[m][k] += c.first_min if i == 0 else c.routine_min
            starts[m][day] += 1
            delay.append(day - max(c.ready_day, 2))
            queue.remove(c)
    return starts, load, delay


def occupancy_label(pct):
    return "High" if pct >= 95 else "Moderate" if pct >= 80 else "Low"
