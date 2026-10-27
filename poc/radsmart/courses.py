"""Treatment courses, calendars and standing slots.

The department's rule (24 Oct 2026): a patient keeps the slot they are given
until the course ends, unless they ask to change it, and the slot is freed when
the course ends. New starts are treated before 17:00; later fractions may take
evening slots so that, every day, enough time before 17:00 stays free for the
next new starts.

So when the oncologist approves a course, RAD-SMART allocates:
  * the new-start slot on day 1, before 17:00, in a gap in that day's plan;
  * one standing slot (two for twice-daily courses) for every later fraction:
    a time that is free on every treatment date of the course, chosen with the
    daily optimiser's hard rules and soft goals, which never eats into the
    new-start reserve before 17:00.
A day's plan is then the standing slots of everyone due that day plus the day's
new starts, checked by the same independent rule checker (scheduler.check_plan).
Daily re-optimisation (urgent starts, faults) changes times for that day only:
the next day everyone is back in their standing slot.

Times are minutes after midnight on the optimiser's 2-minute grid; a slot is
reserved for the predicted (expected) minutes of a routine fraction.
"""

from __future__ import annotations

import bisect
import datetime as dt
import math
from collections import defaultdict
from dataclasses import dataclass, field, replace

import numpy as np

from .config import DEPARTMENT, PATTERNS, fmt
from .scheduler import (DayScheduler, Schedule, Assignment, band_reason, check_plan, outside_band,
                        planning_minutes)

WEEKDAYS = {"daily": {0, 1, 2, 3, 4}, "bid": {0, 1, 2, 3, 4}, "alternate": {0, 2, 4},
            "twice_weekly": {0, 3}}


# ------------------------------------------------------------------ calendar
def working_days(start: dt.date, holidays=frozenset()):
    d = start
    while True:
        if d.weekday() < 5 and d not in holidays:
            yield d
        d += dt.timedelta(days=1)


def treatment_dates(start: dt.date, fractions: int, pattern: str = "daily",
                    holidays=frozenset()) -> list[dt.date]:
    """Treatment days of a course: day 1 is the approved start date, then the
    pattern's weekdays. Twice-daily courses need half as many days."""
    if pattern not in PATTERNS:
        raise ValueError(f"unknown treatment pattern {pattern!r}")
    days = math.ceil(fractions / 2) if pattern == "bid" else fractions
    allowed = WEEKDAYS.get(pattern, {start.weekday()})
    out = []
    for d in working_days(start, holidays):
        if not out or d.weekday() in allowed:
            out.append(d)
        if len(out) == days:
            return out
    return out


def next_treatment_date(after: dt.date, pattern: str, weekday: int, holidays=frozenset()) -> dt.date:
    allowed = WEEKDAYS.get(pattern, {weekday})
    for d in working_days(after + dt.timedelta(days=1), holidays):
        if d.weekday() in allowed:
            return d


# ------------------------------------------------------------------- courses
@dataclass
class Course:
    """One patient's course and the machine time promised to it."""
    patient: object                    # synth.Patient: the engine's view of the patient
    start_date: dt.date
    fractions: int
    pattern: str = "daily"
    dates: list = field(default_factory=list)       # treatment days
    first: tuple | None = None         # (machine, start): new-start slot on day 1
    first_minutes: float = 0.0
    slots: list = field(default_factory=list)       # [(from_date, machine, start, start2)]
    minutes: float = 0.0               # reserved minutes of a routine fraction
    exceptions: dict = field(default_factory=dict)  # date -> [(machine, start)] one-day moves

    @property
    def pid(self) -> str:
        return self.patient.pid

    @property
    def end_date(self) -> dt.date:
        return self.dates[-1]

    def slot_on(self, date):
        """(machine, start, start2) of the standing slot that applies on date."""
        chosen = None
        for row in self.slots:
            if row[0] <= date:
                chosen = row
        return None if chosen is None else chosen[1:]

    def sessions_on(self, date) -> list[dict]:
        """Fractions due on date: fraction number, kind, machine, start, minutes."""
        if date not in self.dates:
            return []
        i = self.dates.index(date)
        bid = self.pattern == "bid"
        nos = [n for n in ([2 * i + 1, 2 * i + 2] if bid else [i + 1]) if n <= self.fractions]
        slot = self.slot_on(date)
        moved = self.exceptions.get(date, [])
        out = []
        for k, n in enumerate(nos):
            if n == 1:
                m, s, mins, kind = self.first[0], self.first[1], self.first_minutes, "new_start"
            elif slot is None:
                continue
            else:
                m, s, mins, kind = slot[0], slot[2] if (bid and k == 1) else slot[1], self.minutes, "routine"
            if k < len(moved) and moved[k] is not None:
                m, s = moved[k]
                kind = "moved" if kind == "routine" else kind
            out.append(dict(fraction=n, kind=kind, machine=m, start=float(s), minutes=float(mins),
                            sid=self.pid if k == 0 else f"{self.pid}/2"))
        return out


# ----------------------------------------------------------------- slot book
class SlotBook:
    """Machine and accessory time already promised, per date, on the 2-minute grid.

    Accessories (one ABC unit, one breast board) are shared by every machine
    and by the CT simulator, so they are booked per date like a machine, with
    the CT simulator's bookings (plus transfer time) always taken.
    """

    def __init__(self, machines=None, dept=None):
        self.d = dept or DEPARTMENT
        self.g = self.d["grid_min"]
        self.t0 = self.d["day_start"]
        self.T = int((self.d["hard_end"] - self.t0) // self.g)
        self.machines = list(machines or self.d["machines"])
        self.occ = {}                                   # (machine or accessory, date) -> int array
        self.owner = defaultdict(set)                   # pid -> {(resource, date, step, steps)}
        self._fixed = {}

    # grid helpers
    def idx(self, minute):
        return int(round((minute - self.t0) / self.g))

    def steps(self, minutes):
        return max(1, math.floor(minutes / self.g + 0.5))

    def fixed(self, machine, standby):
        """Steps that are never free: blocks (blood irradiation) and, unless the
        patient can wait on standby, the urgent-start holds."""
        key = (machine, standby)
        if key not in self._fixed:
            a = np.zeros(self.T, dtype=bool)
            for b in self.d["machines"][machine]["blocks"]:
                a[self.idx(b["start"]):self.idx(b["end"])] = True
            if not standby:
                for h in self.d.get("urgent_holds", []):
                    if h["machine"] == machine:
                        a[self.idx(h["start"]):self.idx(h["start"] + h["minutes"])] = True
            self._fixed[key] = a
        return self._fixed[key]

    def accessory_blocked(self, accessory):
        """Steps an accessory can never be used on the linac: the CT simulator's
        bookings plus transfer time (one unit: any overlap blocks it)."""
        key = ("ct", accessory)
        if key not in self._fixed:
            spec = self.d["accessories"][accessory]
            ct = np.zeros(self.T, dtype=np.int32)
            pad = spec["transfer_min"]
            for b in self.d["ct_sim_bookings"]:
                if b["accessory"] == accessory:
                    lo = max(0, int((b["start"] - pad - self.t0) // self.g))
                    hi = min(self.T, math.ceil((b["end"] + pad - self.t0) / self.g))
                    ct[lo:hi] += 1
            self._fixed[key] = ct
        return self._fixed[key]

    def day(self, resource, date):
        key = (resource, date)
        if key not in self.occ:
            self.occ[key] = np.zeros(self.T, dtype=np.int32)    # 0 free, else count of holders
        return self.occ[key]

    def accessory_full(self, accessory, date):
        """Steps where every unit of the accessory is already in use."""
        units = self.d["accessories"][accessory]["units"]
        return (self.day(accessory, date) + self.accessory_blocked(accessory)) >= units

    def hold(self, pid, machine, date, start, minutes, accessories=()):
        s, n = self.idx(start), self.steps(minutes)
        for resource in [machine, *accessories]:
            self.day(resource, date)[s:s + n] += 1
            self.owner[pid].add((resource, date, s, n))

    def release(self, pid, from_date=None):
        keep = set()
        for resource, date, s, n in self.owner.pop(pid, set()):
            if from_date is not None and date < from_date:
                keep.add((resource, date, s, n))
                continue
            self.occ[(resource, date)][s:s + n] -= 1
        if keep:
            self.owner[pid] = keep

    def add_course(self, c: Course, from_date=None):
        for date in c.dates:
            if from_date is None or date >= from_date:
                for s in c.sessions_on(date):
                    self.hold(c.pid, s["machine"], date, s["start"], s["minutes"], c.patient.accessories)

    def busy_minutes(self, machine, date):
        return float(np.count_nonzero(self.day(machine, date))) * self.g

    def new_start_room(self, machine, date) -> float:
        """Free minutes before the new-start cut-off, in gaps long enough for a new start."""
        d = self.d
        hi = self.idx(d["new_start_latest_end"] - d.get("deadline_buffer_min", 0))
        free = ~(self.day(machine, date)[:hi].astype(bool) | self.fixed(machine, False)[:hi])
        return _usable(free, self.steps(d["new_start_gap_min"])) * self.g


def _runs(free):
    """(start, length) of each run of True in a boolean array."""
    if not free.any():
        return []
    padded = np.concatenate([[False], free, [False]])
    edges = np.flatnonzero(padded[1:] != padded[:-1])
    return [(int(a), int(b - a)) for a, b in zip(edges[::2], edges[1::2])]


def _usable(free, min_len):
    return sum(n for _, n in _runs(free) if n >= min_len)


# ---------------------------------------------------------------- allocation
@dataclass
class Allocation:
    pid: str
    first: tuple | None = None          # (machine, date, start, minutes)
    standing: tuple | None = None       # (machine, start, minutes)
    standing2: tuple | None = None      # twice daily: (machine, start, minutes)
    first_second: float | None = None   # twice daily: day 1 second fraction start
    reasons: list = field(default_factory=list)
    alternatives: list = field(default_factory=list)   # [(machine, start, cost)]
    problem: str | None = None

    @property
    def ok(self):
        return self.problem is None


class SlotAllocator:
    """Allocates new-start and standing slots for newly approved courses."""

    def __init__(self, book: SlotBook, predictor, dept=None):
        self.book = book
        self.d = dept or DEPARTMENT
        self.pred = predictor
        self.sch = DayScheduler(self.d)

    def predict(self, p):
        """Predicted minutes of the first and of a routine fraction."""
        first = replace(p, fraction_no=1, new_start=True)
        later = replace(p, pid=p.pid + "#later", fraction_no=2, new_start=False)
        m = planning_minutes([first, later], self.pred)
        return m[first.pid], m[later.pid]

    # candidate starts for patient p on machine m whose steps are free on every date
    def _candidates(self, p, machine, dates, minutes, reserve, ignore_pid=None, relax=False):
        b, d = self.book, self.d
        n = b.steps(minutes)
        lo, hi, why = self.sch._window(p, {})
        busy = b.fixed(machine, DayScheduler.standby(p)).copy()
        units = {a: d["accessories"][a]["units"] for a in p.accessories}
        for date in dates:
            busy |= self._without(machine, date, ignore_pid).astype(bool)
            for a, u in units.items():
                busy |= (self._without(a, date, ignore_pid) + b.accessory_blocked(a)) >= u
        csum = np.concatenate([[0], np.cumsum(busy)])
        starts = []
        for s in range(max(0, b.idx(lo)), b.T - n + 1):
            st = b.t0 + s * b.g
            if st + minutes > hi + 1e-9:
                break
            if csum[s + n] - csum[s] == 0:
                starts.append(s)
        # the reserve only binds patients who could be treated after 17:00;
        # one whose hard window ends before it (MHRC, complex) is placed anyway
        if reserve and starts and hi > d["new_start_latest_end"]:
            starts = self._keep_reserve(machine, dates, starts, n, ignore_pid, relax)
        return starts, why

    def _fragments(self, machine, dates, starts, n, ignore_pid):
        """Mean minutes per date that a slot at each start would strand in
        slivers too short for any session (best fit: keeps the day packed, so
        later courses still find a slot and the evening ends earlier)."""
        b = self.book
        small = b.steps(self.d.get("sliver_min", 8))
        waste = np.zeros(len(starts))
        s_arr = np.array(starts)
        for date in dates:
            free = ~(self._without(machine, date, ignore_pid).astype(bool) | b.fixed(machine, False))
            before = np.zeros(b.T + 1, dtype=int)     # free steps ending just before i
            after = np.zeros(b.T + 1, dtype=int)      # free steps starting at i
            for i in range(b.T):
                before[i + 1] = before[i] + 1 if free[i] else 0
            for i in range(b.T - 1, -1, -1):
                after[i] = after[i + 1] + 1 if free[i] else 0
            left, right = before[s_arr], after[np.minimum(s_arr + n, b.T)]
            waste += np.where((left > 0) & (left < small), left, 0) + np.where((right > 0) & (right < small), right, 0)
        return dict(zip(starts, waste * b.g / max(1, len(dates))))

    def _without(self, resource, date, pid):
        """Occupancy of a machine or accessory on date, leaving out pid's own holds."""
        a = self.book.day(resource, date)
        if pid is None or pid not in self.book.owner:
            return a
        a = a.copy()
        for r, dd, s, n in self.book.owner[pid]:
            if r == resource and dd == date:
                a[s:s + n] -= 1
        return a

    def _keep_reserve(self, machine, dates, starts, n, ignore_pid, relax=False):
        """Drop starts that would leave less than the new-start reserve before
        17:00 on any of the dates. relax (a move of a booked slot): where the
        reserve is already short, the move may use time no new start could
        use, but must not make it any shorter."""
        b, d = self.book, self.d
        cut = b.idx(d["new_start_latest_end"] - d.get("deadline_buffer_min", 0))
        gap = b.steps(d["new_start_gap_min"])
        need = d["new_start_reserve_min"] / b.g
        early = [s for s in starts if s < cut]
        if not early:
            return starts
        bad = set()
        for date in dates:
            occ = b.day(machine, date) if ignore_pid is None else self._without(machine, date, ignore_pid)
            free = ~(occ[:cut].astype(bool) | b.fixed(machine, False)[:cut])
            runs = _runs(free)
            total = sum(r for _, r in runs if r >= gap)
            floor = need
            if relax:
                now = ~(b.day(machine, date)[:cut].astype(bool) | b.fixed(machine, False)[:cut])
                floor = min(need, sum(r for _, r in _runs(now) if r >= gap))
            run_starts = [a for a, _ in runs]
            for s in early:
                if s in bad:
                    continue
                e, after = s + n, total
                k = max(0, bisect.bisect_right(run_starts, s) - 1)
                while k < len(runs) and runs[k][0] < e:      # every gap the slot cuts into
                    a, r = runs[k]
                    if a + r > s:
                        left, right = max(a, s) - a, a + r - min(a + r, e)
                        after += (-(r if r >= gap else 0) + (left if left >= gap else 0)
                                  + (right if right >= gap else 0))
                    k += 1
                if after < floor:
                    bad.add(s)
        return [s for s in starts if s not in bad]

    def _cost(self, p, start, minutes):
        return self.sch._soft_cost(p, start, start + minutes, None, standing=True)

    def allocate(self, c: Course, machines=None, ignore_pid=None, from_date=None,
                 keep_first=False) -> Allocation:
        """Choose the new-start slot (day 1) and the standing slot for course c.

        from_date: re-allocate only the standing slot from this date (a slot
        change request); keep_first leaves the new-start slot as it is.
        """
        p, b, d = c.patient, self.book, self.d
        if any(a not in d["accessories"] for a in p.accessories):
            raise ValueError(f"unknown accessory in {p.accessories}")
        alloc = Allocation(c.pid)
        first_min, later_min = self.predict(p)
        machines = [m for m in (machines or p.eligible or [p.machine]) if m in b.machines]
        if not machines:
            alloc.problem = "no eligible machine"
            return alloc
        later_dates = [x for x in c.dates[1:] if from_date is None or x >= from_date]

        # 1. new-start slot, day 1, before 17:00
        if not keep_first and from_date is None:
            ns = replace(p, fraction_no=1, new_start=True)
            best = None
            for m in machines:
                starts, why = self._candidates(ns, m, [c.dates[0]], first_min, reserve=False,
                                               ignore_pid=ignore_pid)
                for s in starts:
                    st = b.t0 + s * b.g
                    cost = self._cost(ns, st, first_min) + 0.002 * b.busy_minutes(m, c.dates[0])
                    if best is None or cost < best[0]:
                        best = (cost, m, st, why)
            if best is None:
                alloc.problem = (f"no gap of {first_min:.0f} min before "
                                 f"{fmt(d['new_start_latest_end'])} on {c.dates[0]:%d %b}: "
                                 "choose a later start date")
                return alloc
            _, m1, st1, why = best
            alloc.first = (m1, c.dates[0], st1, first_min)
            alloc.reasons += [f"new start on {c.dates[0]:%a %d %b} at {fmt(st1)}: finishes before "
                              f"{fmt(d['new_start_latest_end'])}"] + [w for w in why if "new start" not in w]
        if not later_dates:
            return alloc

        # 2. standing slot(s) for every later fraction
        rp = replace(p, fraction_no=2, new_start=False)
        pref = machines if alloc.first is None else [alloc.first[0]] + [m for m in machines
                                                                     if m != alloc.first[0]]
        options = self._standing_options(rp, pref, later_dates, later_min, ignore_pid, alloc, True)
        into_reserve = not options
        if into_reserve:            # only the new-start reserve is left: use it, and say so
            options = self._standing_options(rp, pref, later_dates, later_min, ignore_pid, alloc, False)
        if not options:
            alloc.problem = ("no time is free on every treatment date of the course: "
                             "choose a later start date or another machine")
            return alloc
        if c.pattern == "bid":
            return self._bid(c, alloc, options, later_min, rp)
        cost, m, st, why = options[0]
        alloc.standing = (m, st, later_min)
        alloc.reasons += self._explain(rp, m, st, later_min, why, len(later_dates), into_reserve)
        alloc.alternatives = _spread(options[1:], st)
        if from_date is not None and not into_reserve and self._off(p, st, later_min) > 15:
            # a change request: also show the nearest time inside the new-start
            # reserve, for the approver to weigh against the next new starts
            near = self._standing_options(rp, pref, later_dates, later_min, ignore_pid, alloc, False)
            near = [o for o in near if self._off(p, o[2], later_min) < self._off(p, st, later_min)]
            if near:
                o = min(near, key=lambda o: (self._off(p, o[2], later_min), o[0]))
                alloc.alternatives.insert(0, (o[1], o[2], round(o[0], 2), "uses time kept for new starts"))
        return alloc

    def _off(self, p, start, minutes) -> float:
        """Minutes away from what the patient asked for: an exact time, or a band."""
        if p.requested is not None:
            return abs(start - p.requested)
        band = self.d.get("time_bands", {}).get(p.band) if p.band else None
        return outside_band(band, start, start + minutes) if band else 0.0

    def _standing_options(self, rp, machines, dates, minutes, ignore_pid, alloc, reserve):
        b = self.book
        options = []
        w = self.d["weights"].get("fragment", 0.0)
        for m in machines:
            starts, why = self._candidates(rp, m, dates, minutes, reserve=reserve, ignore_pid=ignore_pid)
            load = sum(b.busy_minutes(m, x) for x in dates) / max(1, len(dates))
            waste = self._fragments(m, dates, starts, b.steps(minutes), ignore_pid) if (w and starts) else {}
            for s in starts:
                st = b.t0 + s * b.g
                options.append((self._cost(rp, st, minutes) + 0.002 * load + w * waste.get(s, 0.0) / 10
                                + (0.05 if alloc.first and m != alloc.first[0] else 0.0), m, st, why))
        options.sort(key=lambda o: (o[0], o[2]))
        return options

    def free_steps(self, p, machine, date, minutes):
        """Start steps on one date where p's session fits (machine and accessories)."""
        b = self.book
        n = b.steps(minutes)
        busy = b.day(machine, date).astype(bool) | b.fixed(machine, DayScheduler.standby(p))
        for a in p.accessories:
            busy |= b.accessory_full(a, date)
        csum = np.concatenate([[0], np.cumsum(busy)])
        return [s for s in range(b.T - n + 1) if csum[s + n] == csum[s]]

    def _bid(self, c, alloc, options, minutes, rp):
        gap = self.d["bid_min_gap_min"]
        best = None
        by_machine = defaultdict(list)
        for o in options:
            by_machine[o[1]].append(o)
        for m, opts in by_machine.items():
            opts = sorted(opts, key=lambda o: o[2])
            starts = [o[2] for o in opts]
            # cheapest second slot at or after each time
            suffix = [None] * (len(opts) + 1)
            for k in range(len(opts) - 1, -1, -1):
                suffix[k] = opts[k] if suffix[k + 1] is None or opts[k][0] <= suffix[k + 1][0] else suffix[k + 1]
            for o in opts:
                k = bisect.bisect_left(starts, o[2] + gap)
                if suffix[k] is not None:
                    total = o[0] + suffix[k][0]
                    if best is None or total < best[0]:
                        best = (total, o, suffix[k])
        if best is None:
            alloc.problem = "no pair of slots at least 6 hours apart is free on every treatment date"
            return alloc
        _, a, b2 = best
        alloc.standing, alloc.standing2 = (a[1], a[2], minutes), (b2[1], b2[2], minutes)
        if alloc.first is not None:
            alloc.first_second = b2[2] if b2[2] >= alloc.first[2] + self.d["bid_min_gap_min"] else None
        alloc.reasons += self._explain(rp, a[1], a[2], minutes, a[3], len(c.dates) - 1)
        alloc.reasons.append(f"second daily fraction at {fmt(b2[2])}, at least 6 hours later")
        return alloc

    def _explain(self, p, machine, start, minutes, why, n_dates, into_reserve=False):
        d = self.d
        out = [f"standing slot {fmt(start)} on {d['machines'][machine]['label']} for "
               f"{n_dates} later fraction{'s' if n_dates != 1 else ''}, free on every date",
               f"report at {fmt(start - p.report_lead)} ({p.report_lead} min before"
               + (": drink 500 mL of water on arrival)" if p.pelvic else ")")]
        out += [w for w in why]
        if into_reserve:
            out.append(f"no other time fits this patient's rules: uses some of the time kept "
                       f"before {fmt(d['new_start_latest_end'])} for new starts")
        elif start + minutes <= d["new_start_latest_end"]:
            out.append(f"keeps at least {d['new_start_reserve_min']} min free before "
                       f"{fmt(d['new_start_latest_end'])} for new starts")
        elif p.flexible:
            kind = "inpatient" if p.inpatient else "dormitory" if p.dormitory else "lives nearby"
            out.append(f"{kind}: evening slot, leaving the day to patients who need it")
        else:
            out.append(f"after {fmt(d['new_start_latest_end'])}: earlier time is kept for new starts")
        if p.requested is not None:
            delta = start - p.requested
            out.append("at the preferred time" if abs(delta) <= 15 else
                       f"{abs(delta):.0f} min {'later' if delta > 0 else 'earlier'} than the preferred "
                       f"time {fmt(p.requested)}")
        out += band_reason(d, p, start, start + minutes, standing=True)
        if p.elderly and not p.band and start <= d["elderly_pref_before"]:
            out.append("older patient: earlier in the day")
        return out

    def commit(self, c: Course, a: Allocation, from_date=None):
        """Write an approved allocation into the course and the slot book."""
        if not a.ok:
            raise ValueError(a.problem)
        if from_date is None:
            c.first = (a.first[0], a.first[2])
            c.first_minutes = a.first[3]
            c.slots = []
        else:
            self.book.release(c.pid, from_date)
            c.slots = [s for s in c.slots if s[0] < from_date]
        if a.standing:
            c.minutes = a.standing[2]
            start2 = a.standing2[1] if a.standing2 else None
            # twice daily: the standing pair already applies on day 1 (second fraction)
            when = from_date or (c.dates[1] if len(c.dates) > 1 and c.pattern != "bid" else c.dates[0])
            c.slots.append((when, a.standing[0], a.standing[1], start2))
        if from_date is None and c.pattern == "bid" and a.standing2 and a.first:
            self._day1_second(c, a)
        self.book.add_course(c, from_date)

    def _nearest_free(self, p, machine, date, minutes, near, earliest=None):
        steps = self.free_steps(p, machine, date, minutes)
        if earliest is not None:
            steps = [s for s in steps if s >= self.book.idx(earliest)]
        if not steps:
            return None
        s0 = self.book.idx(near)
        return self.book.t0 + min(steps, key=lambda s: (abs(s - s0), s)) * self.book.g

    def _day1_second(self, c: Course, a: Allocation):
        """Twice daily, day 1: the second fraction must be at least 6 hours
        after the new start; if its standing time is too early or taken that
        day, use the nearest free time after the gap, for day 1 only."""
        m, st, minutes = a.standing2
        earliest = a.first[2] + self.d["bid_min_gap_min"]
        t = self._nearest_free(c.patient, m, c.dates[0], minutes, max(st, earliest), earliest)
        if t is not None and t != st:
            c.exceptions[c.dates[0]] = [None, (m, t)]

    def earliest_start(self, c: Course, holidays=frozenset(), max_days=15):
        """Try c's start date, then the following working days, until both a
        new-start gap and a standing slot fit. Returns (course, allocation) for
        the first date that works (the course's dates are updated), or the last
        failed allocation."""
        a = None
        for k, day in enumerate(working_days(c.start_date, holidays)):
            if k >= max_days:
                break
            c.start_date = day
            c.dates = treatment_dates(day, c.fractions, c.pattern, holidays)
            a = self.allocate(c)
            if a.ok:
                if k:
                    a.reasons.insert(0, f"first date with a free new-start gap and a standing slot: {day:%a %d %b}")
                return c, a
        return c, a

    def change_slot(self, c: Course, from_date, wanted: int | None = None, band: str | None = None) -> Allocation:
        """A patient asks for another time from from_date: the best free standing
        slot near the wanted time, or inside the wanted morning, afternoon or
        evening, for the rest of the course (for approval)."""
        if band is not None:
            p = replace(c.patient, requested=None, band=band, paying=True)
        else:
            p = replace(c.patient, requested=wanted, paying=True)    # honour the request firmly
        return self.allocate(replace(c, patient=p), ignore_pid=c.pid, from_date=from_date)

    # ------------------------------------------------------------ better time
    def better_time(self, c: Course, from_date):
        """A standing slot inside the patient's time band, on the same machine,
        free on every remaining date and keeping the new-start reserve: the
        offer RAD-SMART makes when slots free up. (machine, start, why) or None.

        Not offered for twice-daily courses, for the last few fractions, or
        when the current slot is already inside the band."""
        p, b, d = c.patient, self.book, self.d
        band = d.get("time_bands", {}).get(p.band) if p.band else None
        if band is None or c.pattern == "bid" or not c.slots:
            return None
        dates = [x for x in c.dates if x >= from_date]
        if len(dates) < d.get("better_time_min_left", 4):
            return None
        m, now, _ = c.slot_on(dates[0])
        if outside_band(band, now, now + c.minutes) < 1:
            return None
        rp = replace(p, fraction_no=2, new_start=False)
        starts, why = self._candidates(rp, m, dates, c.minutes, reserve=True, ignore_pid=c.pid, relax=True)
        inside = [s for s in starts if outside_band(band, b.t0 + s * b.g, b.t0 + s * b.g + c.minutes) < 1]
        if not inside:
            return None
        w = d["weights"].get("fragment", 0.0)
        waste = self._fragments(m, dates, inside, b.steps(c.minutes), c.pid) if w else {}
        s = min(inside, key=lambda s: (self._cost(rp, b.t0 + s * b.g, c.minutes) + w * waste.get(s, 0.0) / 10,
                                       abs(b.t0 + s * b.g - now)))
        return m, b.t0 + s * b.g, why

    def better_times(self, courses, from_date_of):
        """The "better time" pass over every course outside its band. Offers go
        first to whoever gains most (preference weight x fractions left x
        minutes outside the band), and each offered slot is held before the
        next patient is considered, so no two offers share a slot. Current
        slots stay held too: nothing moves until staff approve an offer.
        Returns [(course, machine, start, score, why)]."""
        w, bands = self.d["weights"], self.d.get("time_bands", {})
        ranked = []
        for c in courses:
            band = bands.get(c.patient.band) if c.patient.band else None
            if band is None or not c.slots:
                continue
            f = from_date_of(c)
            left = sum(1 for x in c.dates if x >= f)
            slot = c.slot_on(f) if left else None
            if slot is None:
                continue
            off = outside_band(band, slot[1], slot[1] + c.minutes)
            if off < 1:
                continue
            p = c.patient
            weight = (w["pref_complex"] if p.complex else w["pref_paying"] if p.paying
                      else w["pref_flexible"] if p.flexible else w.get("pref_band", w["pref_general"]))
            ranked.append((weight * left * off, c, f))
        out = []
        for score, c, f in sorted(ranked, key=lambda r: -r[0]):
            found = self.better_time(c, f)
            if found is None:
                continue
            m, st, why = found
            for x in c.dates:
                if x >= f:
                    self.book.hold(c.pid + "#offer", m, x, st, c.minutes, c.patient.accessories)
            out.append((c, m, st, round(score, 1), why))
        return out

    def add_missed_fraction(self, c: Course, holidays=frozenset()):
        """A fraction missed today (breakdown, sent home) is added at the end of
        the course, in the standing slot if it is free that day, else in the
        nearest free time that day."""
        new = next_treatment_date(c.dates[-1], c.pattern, c.start_date.weekday(), holidays)
        c.dates.append(new)
        m, st, _ = c.slot_on(new)
        t = self._nearest_free(c.patient, m, new, c.minutes, st)
        if t is not None and t != st:
            c.exceptions[new] = [(m, t)]
        for s in c.sessions_on(new):
            self.book.hold(c.pid, s["machine"], new, s["start"], s["minutes"], c.patient.accessories)
        return new


def _spread(options, chosen, k=3, apart=30):
    """Up to k alternative times at least `apart` minutes from each other."""
    out, taken = [], [chosen]
    for cost, m, st, *_ in options:
        if all(abs(st - t) >= apart for t in taken):
            out.append((m, st, round(cost, 2)))
            taken.append(st)
        if len(out) == k:
            break
    return out


# ------------------------------------------------------------- daily plan
def day_plan(date, courses, dept=None):
    """The day's sessions from standing slots and new starts.

    Returns (patients, schedule, standing): engine patients for the day (one
    per session; a twice-daily second fraction gets pid 'P001/2'), a Schedule
    the rule checker and the twin can read, and the standing slots that must be
    kept (continuing patients without a one-day move).
    """
    patients, rows, standing = [], {}, {}
    for c in courses:
        for s in c.sessions_on(date):
            p = replace(c.patient, pid=s["sid"], fraction_no=s["fraction"],
                        new_start=s["kind"] == "new_start", machine=s["machine"])
            patients.append(p)
            rows[p.pid] = Assignment(p.pid, s["machine"], s["start"], s["minutes"],
                                     [f"{s['kind'].replace('_', ' ')} slot {fmt(s['start'])}"])
            if s["kind"] == "routine":
                standing[p.pid] = (s["machine"], s["start"])
    return patients, Schedule(rows, "standing slots", 0.0, 0.0, 0, 0, None), standing


def check_day(date, courses, dept=None) -> dict:
    patients, sched, standing = day_plan(date, courses, dept)
    return check_plan(patients, sched, dept, standing=standing)
