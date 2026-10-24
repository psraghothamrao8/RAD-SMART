"""Machine breakdown triage: who is treated today, when, and who is sent back.

The department's rules (24 Oct 2026). A breakdown lasts anywhere from 15
minutes to 48 hours (the problem, the engineer, spare parts). The technologist
enters the expected length, or the exact one when the engineer knows it, and
RAD-SMART proposes:

  * up to 60 minutes: nobody is sent home; everyone is treated today, working
    up to 60 minutes of overtime;
  * over 60 minutes: enough patients are sent back to free the machine-minutes
    that 60 minutes of overtime and the gaps in today's plan cannot absorb;
  * either way the day's new starts wait until the machine works again, and
    move to the next working day if they can no longer finish by 17:00;
  * patients who have not left home are asked to postpone travel until they
    are given a new time.

Who is sent back first (lowest burden and clinical cost first):
  1. patients who have not set out yet, palliative (gap category 3) before
     other radical courses (category 2);
  2. then patients already in the department, in the same order;
  3. never a gap-sensitive radical course (category 1, e.g. head and neck or
     cervix) or a hospice (MHRC) patient on the bus: if one cannot be treated
     today, the oncologist is asked to decide (another machine, a longer day,
     or compensation later: twice daily or a Saturday).
A missed fraction is added at the end of the course, in the standing slot.

The proposal is shown to the technologist or oncologist, who approves it before
any patient is told. This module only proposes.
"""

from __future__ import annotations

import math

from dataclasses import dataclass, field

from .config import DEPARTMENT, fmt
from .scheduler import DayScheduler, check_plan

TRAVEL_NOTICE_MIN = 45        # a patient told now can be here this much later
KEEP = 1e5                    # cost of sending back a patient who must stay


@dataclass
class Triage:
    rule: str
    machine: str
    fault_start: float
    expected_min: float
    restart: float | None            # None: not back today
    allowed_end: float
    minutes_to_free: float
    overtime_min: float = 0.0                     # beyond the planned end of the day
    actions: list = field(default_factory=list)   # one dict per patient
    new_appt: dict = field(default_factory=dict)  # pid -> new start today
    sent_back: set = field(default_factory=set)
    postponed: set = field(default_factory=set)   # new starts moved to the next working day
    notified: set = field(default_factory=set)    # told a new time, or not to travel
    flagged: set = field(default_factory=set)     # category 1 / MHRC who cannot be treated today
    schedule: object = None
    check: dict | None = None
    solve_seconds: float = 0.0

    def counts(self):
        out = {}
        for a in self.actions:
            out[a["action"]] = out.get(a["action"], 0) + 1
        return out


def _priority_cost(p, present, long):
    """What sending p back costs; the optimiser sends back the cheapest first."""
    if not long:
        return KEEP                                   # up to 60 min: nobody is sent home
    if p.gap_category == 1 or p.mhrc or p.urgent:
        return KEEP
    if p.new_start or p.complex:
        return 4000.0                                 # start today if it still fits before 17:00
    if present or p.inpatient:
        return 2500.0 if p.gap_category == 3 else 3000.0
    return 700.0 if p.gap_category == 3 else 1000.0


class _Published:
    """The published minutes as the duration estimate, so the re-plan and the
    checker agree on how long each session is."""

    def __init__(self, plan):
        self.plan = plan

    def predict_many(self, patients, q):
        return [self.plan[p.pid][2] for p in patients]


def triage(patients, plan, status, fault, dept=None, time_limit=10.0, sch=None) -> Triage:
    """Propose today's response to a breakdown.

    patients: today's engine patients (synth.Patient)
    plan:     pid -> (machine, start, minutes) as published
    status:   pid -> "done" | "in_room" | "waiting" (arrived) | "not_arrived"
    fault:    (machine, start, expected minutes)
    """
    d = dept or DEPARTMENT
    sch = sch or DayScheduler(d)
    m, f0, flen = fault
    long = flen > d["downtime_short_max_min"]
    on_m = [p for p in patients if plan[p.pid][0] == m]
    planned_end = max(plan[p.pid][1] + plan[p.pid][2] for p in on_m)
    todo = [p for p in on_m if status.get(p.pid) not in ("done", "in_room")]
    present = {p.pid for p in todo if status.get(p.pid) == "waiting"}
    restart = f0 + flen
    budget = d["downtime_overtime_budget_min"]
    allowed_end = d["hard_end"] if not long else min(d["hard_end"], max(planned_end, f0) + budget)
    rule = ("up to 60 min: nobody is sent home; everyone is treated today with up to 60 min of overtime"
            if not long else
            "over 60 min: patients are sent back to free what 60 min of overtime and today's gaps cannot "
            "absorb; patients not yet travelling are asked to wait for a new time")
    out = Triage(rule, m, f0, flen, restart if restart < allowed_end else None, allowed_end, 0.0)

    if restart >= allowed_end:                         # not back today
        out.minutes_to_free = sum(plan[p.pid][2] for p in todo)
        for p in todo:
            _send_back(out, p, p.pid in present, plan, "the machine is not expected back today")
        return out

    blocked = sum(max(0, min(allowed_end, b["end"]) - max(restart, b["start"]))
                  for b in d["machines"][m]["blocks"])
    out.minutes_to_free = round(max(0.0, sum(plan[p.pid][2] for p in todo)
                                    - (allowed_end - restart - blocked)), 1)
    prev = {p.pid: plan[p.pid][1] for p in todo}
    earliest = {p.pid: max(restart, f0 + (0 if p.pid in present else TRAVEL_NOTICE_MIN)) for p in todo}
    blocks = [(d["day_start"], restart, "Breakdown")]
    if allowed_end < d["hard_end"]:
        blocks.append((allowed_end, d["hard_end"], "End of overtime"))
    s = sch.solve(todo, _Published(plan), earliest=earliest, prev_time=prev, present=present,
                  defer_cost={p.pid: _priority_cost(p, p.pid in present, long) for p in todo},
                  extra_blocks={m: blocks}, time_limit=time_limit)
    _waiting_first(s, todo, present, restart, d, m)
    out.schedule, out.solve_seconds = s, s.solve_seconds
    out.check = check_plan(todo, s, d)
    for p in todo:
        a = s.assignments[p.pid]
        here = p.pid in present
        if a.start is None:
            if p.new_start and not p.urgent:
                out.postponed.add(p.pid)
                out.actions.append(_row(p, "start_next_day", None, plan, here,
                                        "new start cannot finish before "
                                        f"{fmt(d['new_start_latest_end'])} today: starts the next working day"))
                if not here:
                    out.notified.add(p.pid)
            else:
                _send_back(out, p, here, plan, "today's remaining time cannot hold everyone")
            continue
        out.new_appt[p.pid] = a.start
        moved = abs(a.start - prev[p.pid]) >= 5
        if p.new_start and not p.urgent:
            why = f"new start waits for the machine: starts at {fmt(a.start)}, before {fmt(d['new_start_latest_end'])}"
            action = "treat_later" if moved else "treat"
        elif here:
            why = f"already here: treated at {fmt(a.start)}" + (f", {a.start - prev[p.pid]:+.0f} min" if moved else "")
            action = "treat_later" if moved else "treat"
        else:
            report = fmt(a.start - p.report_lead)
            why = ("no change" if not moved else
                   f"asked to postpone travel; new reporting time {report}" if a.start > prev[p.pid] else
                   f"called in earlier to fill the time; new reporting time {report}")
            action = "new_time" if moved else "treat"
        if moved and not here:
            out.notified.add(p.pid)
        out.actions.append(_row(p, action, a.start, plan, here, why))
    ends = [x["new_start"] + plan[x["pid"]][2] for x in out.actions if x["new_start"] is not None]
    out.overtime_min = round(max(0.0, max(ends, default=0.0) - planned_end), 1)
    return out


def _waiting_first(s, todo, present, restart, d, machine):
    """Patients already waiting are treated first: each moves into the earliest
    idle time on the machine after the restart, before their planned time.
    Nobody else moves, and a move that would break a hard rule is undone."""
    by_pid = {p.pid: p for p in todo}
    blocks = [(b["start"], b["end"]) for b in d["machines"][machine]["blocks"]]
    for pid in sorted(present, key=lambda q: s.assignments[q].start if s.assignments[q].start is not None else 1e9):
        a, p = s.assignments[pid], by_pid[pid]
        if a.start is None or p.mhrc:                  # the hospice window stays as planned
            continue
        busy = sorted([(x.start, x.start + x.planned_minutes) for q, x in s.assignments.items()
                       if q != pid and x.start is not None] + blocks)
        t = math.ceil(max(restart, p.earliest_start or 0))
        for x0, x1 in busy:
            if t + a.planned_minutes <= x0:
                break
            if x1 > t:
                t = math.ceil(x1)
        if t >= a.start - 1:
            continue
        before = a.start
        a.start = float(t)
        if check_plan(todo, s, d)["violations"]:
            a.start = before


def _send_back(out, p, here, plan, why):
    if p.gap_category == 1 or p.mhrc:
        out.flagged.add(p.pid)
        out.actions.append(_row(p, "doctor_decides", None, plan, here,
                                f"{why}; {'gap-sensitive course (category 1)' if p.gap_category == 1 else 'hospice patient'}: "
                                "oncologist to decide (another machine, a longer day, or compensation)"))
        return
    out.sent_back.add(p.pid)
    action = "send_home" if here else "do_not_travel"
    tail = ("missed fraction added at the end of the course, in the usual slot"
            if not p.new_start else "the course starts the next working day")
    out.actions.append(_row(p, action, None, plan, here, f"{why}; {tail}"))
    if not here:
        out.notified.add(p.pid)


def _row(p, action, new_start, plan, here, why):
    return {"pid": p.pid, "action": action, "planned": plan[p.pid][1], "new_start": new_start,
            "present": here, "gap_category": p.gap_category, "new_start_patient": p.new_start,
            "why": why}


ACTION_LABELS = {
    "treat": "Treat as planned",
    "treat_later": "Treat today, later",
    "new_time": "New time today (patient told)",
    "start_next_day": "New start moves to the next working day",
    "send_home": "Send home: next fraction tomorrow",
    "do_not_travel": "Do not travel today",
    "doctor_decides": "Oncologist decides",
}
