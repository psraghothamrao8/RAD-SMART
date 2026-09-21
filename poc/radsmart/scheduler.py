"""RAD-SMART daily scheduling engine (proof of concept).

Two-stage ("coarse-to-fine") mixed-integer optimisation, solved with the
open-source HiGHS solver bundled with SciPy.

Stage 1 - load levelling. Each patient is assigned to a 15-minute bucket so
that the predicted machine-minutes in every bucket fit its capacity (the
problem statement's "allocate machine minutes rather than counting patients").

Stage 2 - exact timetable. Time-indexed model at 2-minute resolution, each
patient's candidate starts restricted to a window around their stage-1 bucket:

    x[p, m, s] = 1  if patient p starts on machine m at grid slot s

Hard constraints - satisfied by construction, never traded off:
  * every patient gets exactly one start, or is explicitly flagged for a human
  * a machine treats one patient at a time; fixed blocks (blood irradiation,
    same-day urgent holds, downtime) stay free
  * shared accessories: simultaneous use across machines and the CT simulator
    never exceeds the units owned (CT bookings padded with transfer time)
  * complex procedures inside the senior-staff window (10:00-17:00), at most
    N at once across all machines
  * new starts finish before 17:00; same-day urgent starts before 18:00;
    public-transport patients before 21:00; MHRC patients inside their
    16:00-17:00 slots, in time for the 17:00 bus; nothing past the hard end
Soft goals (weighted objective; weights are department configuration):
  * paying patients at their preferred time wherever possible; everyone else
    near their usual time
  * older patients earlier in the day
  * flexible patients (inpatients, dormitory, nearby) take the late evening;
    others finish by 21:00 where possible; the day ends as early as it can
  * complex procedures in the 12:00-13:30 protected block, which is released
    to other patients when no complex case needs it
  * minimise overtime
  * in re-optimisation mode, minimise changes to already-published times and,
    above all, the extra waiting of patients who are already in the department

Production recommendation: the same model maps one-to-one onto OR-Tools CP-SAT
interval variables (NoOverlap + Cumulative), which removes the need for the
two-stage split at larger scale. HiGHS is used here because it ships with SciPy.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from .config import DEPARTMENT, fmt


@dataclass
class Assignment:
    pid: str
    machine: str | None
    start: float | None          # minutes after midnight (appointment time)
    planned_minutes: float
    reasons: list = field(default_factory=list)


@dataclass
class Schedule:
    assignments: dict            # pid -> Assignment
    status: str
    objective: float
    solve_seconds: float
    n_variables: int
    n_constraints: int
    mip_gap: float | None

    def unscheduled(self):
        return [a.pid for a in self.assignments.values() if a.start is None]


def planning_minutes(patients, predictor, policy: dict | None = None) -> dict:
    """Minutes to reserve per patient (pid -> minutes), from a duration predictor.

    policy maps patient class -> 'mean' | 'p80'. Reserving the expected
    (mean) minutes keeps the day's total right; P80 for long or variable
    sessions limits delay spill-over.
    """
    policy = policy or {"routine": "mean", "new_start": "mean", "complex": "mean"}
    if hasattr(predictor, "predict_many"):
        p50 = predictor.predict_many(patients, "mean")
        p80 = predictor.predict_many(patients, 0.8)
    else:                               # lookup table: its "p50" is the average
        p50 = [predictor.p50(p) for p in patients]
        p80 = [predictor.p80(p) for p in patients]
    out = {}
    for p, a, b in zip(patients, p50, p80):
        cls = "complex" if p.complex else ("new_start" if p.new_start else "routine")
        out[p.pid] = float(b if policy[cls] == "p80" else a)
    return out


def _solve_milp(c, rows, cols, vals, lb, ub, n_int, n, time_limit, gap):
    """n_int: number of leading integer variables, or an explicit 0/1 mask."""
    A = coo_matrix((vals, (rows, cols)), shape=(len(lb), n)).tocsr()
    if np.ndim(n_int):
        integrality = np.asarray(n_int, dtype=float)
    else:
        integrality = np.concatenate([np.ones(n_int), np.zeros(n - n_int)])
    tic = time.perf_counter()
    res = milp(np.asarray(c, dtype=float), integrality=integrality,
               bounds=Bounds(np.zeros(n), np.ones(n)),
               constraints=LinearConstraint(A, np.array(lb), np.array(ub)),
               options={"time_limit": time_limit, "mip_rel_gap": gap, "disp": False})
    if res.x is None:
        raise RuntimeError(f"solver failed: {res.message}")
    return res, time.perf_counter() - tic


class DayScheduler:
    BUCKET = 15          # stage-1 bucket length (minutes)
    WINDOW = 50          # stage-2 search window around the bucket (minutes)

    def __init__(self, dept: dict | None = None):
        self.d = dept or DEPARTMENT
        self.g = self.d["grid_min"]
        self.t0 = self.d["day_start"]
        self.T = int((self.d["hard_end"] - self.t0) // self.g)
        self._present = frozenset()

    # ---------------------------------------------------------------- helpers
    def slot_time(self, s: int) -> int:
        return self.t0 + s * self.g

    @staticmethod
    def standby(p):
        """Inpatients and dormitory residents are in the building, so they can
        be booked into the urgent holds on standby: if an urgent patient comes,
        they are simply treated a little later. Held capacity is never wasted."""
        return (p.inpatient or p.dormitory) and not (p.new_start or p.complex or p.mhrc or p.urgent)

    def _blocks(self, machine, extra_blocks, holds=True):
        blocks = [(b["start"], b["end"], b["label"]) for b in self.d["machines"][machine]["blocks"]]
        for h in self.d.get("urgent_holds", []) if holds else []:
            if h["machine"] == machine:
                blocks.append((h["start"], h["start"] + h["minutes"], "Urgent hold"))
        blocks += list(extra_blocks.get(machine, []))
        return blocks

    def _window(self, p, earliest):
        """Hard earliest start / latest end for patient p (minutes)."""
        d = self.d
        lo, hi = self.t0, d["hard_end"]
        why = []
        buf = d.get("deadline_buffer_min", 0)
        if p.complex:
            lo = max(lo, d["senior_staff_window"][0])
            hi = min(hi, d["senior_staff_window"][1] - buf)
            why.append(f"complex procedure: senior staff {fmt(d['senior_staff_window'][0])}-"
                       f"{fmt(d['senior_staff_window'][1])}")
        if p.new_start:
            hi = min(hi, d["new_start_latest_end"] - buf)
            why.append(f"new start: finish by {fmt(d['new_start_latest_end'])}")
        if p.transport and p.latest_end:
            hi = min(hi, p.latest_end - buf)
            why.append(f"public transport: finish by {fmt(p.latest_end)}")
        if p.mhrc:
            mlo, mhi = d["mhrc_window"]
            lo, hi = max(lo, mlo), min(hi, mhi - d["mhrc_buffer_min"])
            why.append(f"MHRC: protected slot {fmt(mlo)}-17:00, back on the 17:00 bus")
        if p.urgent:
            hi = min(hi, d["urgent_latest_end"])
            why.append(f"urgent start: treat by {fmt(d['urgent_latest_end'])}")
        if p.ready_time:
            lo = max(lo, p.ready_time)
            why.append(f"ready at {fmt(p.ready_time)}")
        if p.pid in earliest:
            lo = max(lo, earliest[p.pid])
            why.append(f"cannot arrive before {fmt(earliest[p.pid])}")
        return lo, hi, why

    def _soft_cost(self, p, start, end, prev_time):
        d, w = self.d, self.d["weights"]
        c = 0.0
        target = p.requested if p.requested is not None else p.usual_time
        paying = p.requested is not None
        weight = (w["pref_complex"] if p.complex
                  else w["pref_paying"] if paying
                  else w["pref_flexible"] if p.flexible else w["pref_general"])
        tol = w["pref_tolerance_paying"] if paying else w["pref_tolerance"]
        c += weight * max(0.0, abs(start - target) - tol) / 10
        if p.elderly:
            c += w["elderly_after_1pm"] * max(0, start - d["elderly_pref_before"]) / 10
        if not p.flexible:
            c += w["late_evening"] * max(0, end - d["late_evening_after"]) / 10
        c += w["night"] * max(0, end - d["night_after"]) / 10
        if p.mhrc:
            c += w["mhrc_wait"] * max(0, start - d["mhrc_window"][0]) / 10
        if p.complex:
            blo, bhi = d["protected_block"]
            overlap = max(0, min(end, bhi) - max(start, blo))
            c += w["complex_outside_block"] * ((end - start) - overlap) / 10
        c += w["overtime"] * max(0, end - d["regular_end"]) / 10
        if prev_time is not None and p.pid in prev_time:
            if p.pid in self._present:
                # already in the department (or on the way): every minute is a
                # minute in the waiting room, and long waits are penalised steeply
                late = max(0.0, start - prev_time[p.pid])
                scale = 0.25 if p.flexible else 1.0   # ward, dormitory or home nearby
                c += scale * (w["present_wait"] * late + w["present_long_wait"] * max(0.0, late - 60)) / 10
            else:
                shift = abs(start - prev_time[p.pid])
                scale = 0.25 if p.flexible else 1.0
                c += (w["move"] * shift + scale * w["move_long"] * max(0.0, shift - 60)) / 10
        c += 1e-4 * (start - self.t0)   # tie-break: earlier
        return c

    def _ct_busy(self, accessory, a_start, a_end):
        """Minutes of [a_start, a_end) during which the CT simulator holds units."""
        pad = self.d["accessories"][accessory]["transfer_min"]
        busy = 0.0
        for b in self.d["ct_sim_bookings"]:
            if b["accessory"] == accessory:
                busy += max(0, min(a_end, b["end"] + pad) - max(a_start, b["start"] - pad))
        return busy

    # ------------------------------------------------------------------ solve
    def solve(self, patients, predictor, policy=None, locked=None, earliest=None,
              prev_time=None, extra_blocks=None, time_limit=20.0, gap=0.01,
              machines_of=None, defer_cost=None, present=None):
        """Plan the day. Returns a Schedule with an Assignment per patient.

        locked:       pid -> (machine, start_minute)   human-fixed or in progress
        earliest:     pid -> minute                    cannot start before
        prev_time:    pid -> minute                    published time (re-opt)
        extra_blocks: machine -> [(start, end, label)] downtime, faults
        machines_of:  pid -> [machines]                beam-matched pools
        defer_cost:   pid -> cost of leaving p unplanned (a deferral proposal);
                      lower = proposed first when not everyone fits
        present:      pids already in the department or on the way (re-opt):
                      their waiting is costed, instead of a move they can be told about
        """
        self._present = frozenset(present or ())
        ctx = dict(locked=locked or {}, earliest=earliest or {}, prev_time=prev_time,
                   extra_blocks=extra_blocks or {}, machines_of=machines_of or {},
                   defer_cost=defer_cost or {})
        dur = planning_minutes(patients, predictor, policy)
        tic = time.perf_counter()
        centre = self._stage1(patients, dur, ctx, time_limit)
        # Stage 2a - "big rocks" (complex procedures, new starts) and the
        # tightly-windowed MHRC patients are placed exactly, near the bucket
        # stage 1 reserved for them, then locked: the protected-slot idea.
        rocks = [p for p in patients if (p.complex or p.new_start or p.mhrc)
                 and p.pid not in ctx["locked"]]
        if rocks:
            fixed = [p for p in patients if p.pid in ctx["locked"]]
            s_rocks = self._stage2(rocks + fixed, dur, ctx, centre, time_limit, gap, self.WINDOW)
            if s_rocks.unscheduled():
                s_rocks = self._stage2(rocks + fixed, dur, ctx, {}, time_limit, gap, self.WINDOW)
            ctx["locked"] = dict(ctx["locked"])
            for p in rocks:
                a = s_rocks.assignments[p.pid]
                if a.start is not None:
                    ctx["locked"][p.pid] = (a.machine, a.start)
        # Stage 2b - everyone else, searched around their stage-1 bucket.
        sched = self._stage2(patients, dur, ctx, centre, time_limit, gap, self.WINDOW)
        if sched.unscheduled():   # a window was too tight: open it for those patients only
            for pid in sched.unscheduled():
                centre[pid] = None
            sched = self._stage2(patients, dur, ctx, centre, time_limit, gap, self.WINDOW)
        sched.solve_seconds = time.perf_counter() - tic
        return sched

    # -------------------------------------------------------- stage 1: buckets
    def _stage1(self, patients, dur, ctx, time_limit):
        d, L = self.d, self.BUCKET
        nb = math.ceil((d["hard_end"] - self.t0) / L)
        bstart = [self.t0 + b * L for b in range(nb)]
        var, costs = [], []
        for pi, p in enumerate(patients):
            lo, hi, _ = self._window(p, ctx["earliest"])
            for m in ctx["machines_of"].get(p.pid, [p.machine]):
                blocks = self._blocks(m, ctx["extra_blocks"], holds=not self.standby(p))
                if p.pid in ctx["locked"]:
                    lm, ls = ctx["locked"][p.pid]
                    if lm == m:
                        var.append((pi, m, ls))
                        costs.append(0.0)
                    continue
                for b in range(nb):
                    st = max(bstart[b], lo)
                    if st >= bstart[b] + L or st + dur[p.pid] > hi:
                        continue
                    if any(bs <= st and st + dur[p.pid] <= be for bs, be, _ in blocks):
                        continue
                    var.append((pi, m, st))
                    costs.append(self._soft_cost(p, st, st + dur[p.pid], ctx["prev_time"]))
        nx, n_pat = len(var), len(patients)
        n = nx + n_pat
        c = costs + [d["weights"]["unscheduled"]] * n_pat
        rows, cols, vals, lb, ub = [], [], [], [], []
        for j, (pi, _, _) in enumerate(var):
            rows.append(pi); cols.append(j); vals.append(1.0)
        for pi in range(n_pat):
            rows.append(pi); cols.append(nx + pi); vals.append(1.0)
        lb += [1.0] * n_pat; ub += [1.0] * n_pat
        r = n_pat

        def add_capacity(select, cap_of_bucket):
            nonlocal r
            for j, (pi, m, st) in enumerate(var):
                if not select(patients[pi], m):
                    continue
                en = st + dur[patients[pi].pid]
                for b in range(int((st - self.t0) // L), min(nb, int((en - self.t0 - 1e-9) // L) + 1)):
                    ov = min(en, bstart[b] + L) - max(st, bstart[b])
                    if ov > 0:
                        rows.append(r + b); cols.append(j); vals.append(ov)
            for b in range(nb):
                lb.append(-np.inf); ub.append(max(0.0, cap_of_bucket(b)))
            r += nb

        machines = sorted({m for _, m, _ in var})
        for m in machines:
            blocks = self._blocks(m, ctx["extra_blocks"])
            add_capacity(lambda p, mm, m=m: mm == m,
                         lambda b, blocks=blocks: L - sum(
                             max(0, min(be, bstart[b] + L) - max(bs, bstart[b])) for bs, be, _ in blocks))
        for a, spec in d["accessories"].items():
            if any(a in p.accessories for p in patients):
                add_capacity(lambda p, mm, a=a: a in p.accessories,
                             lambda b, a=a, spec=spec: L * spec["units"] - self._ct_busy(a, bstart[b], bstart[b] + L))
        if len(machines) > 1:
            add_capacity(lambda p, mm: p.complex,
                         lambda b: L * d["senior_staff_concurrent"])
        # "Big rocks" (complex procedures, new starts) get integer buckets so a
        # contiguous block of capacity is really reserved for them; routine
        # patients stay continuous (stage 1 only centres their search window,
        # stage 2 enforces every rule exactly).
        rock = [1.0 if (patients[pi].complex or patients[pi].new_start) else 0.0
                for pi, _, _ in var]
        res, _ = _solve_milp(c, rows, cols, vals, lb, ub, rock + [0.0] * n_pat, n,
                             time_limit, 0.02)
        centre = {p.pid: None for p in patients}
        best = {}
        for j in np.flatnonzero(res.x[:nx] > 1e-6):
            pi, m, st = var[j]
            if res.x[j] > best.get(pi, (0.0, None))[0]:
                best[pi] = (res.x[j], st)
        for pi, (_, st) in best.items():
            centre[patients[pi].pid] = st
        return centre

    # --------------------------------------------------- stage 2: exact times
    def _stage2(self, patients, dur, ctx, centre, time_limit, gap, window):
        d, g = self.d, self.g
        var_p, var_m, var_s, var_len, costs, why_window = [], [], [], [], [], {}
        for pi, p in enumerate(patients):
            dslots = max(1, math.floor(dur[p.pid] / g + 0.5))    # nearest grid step
            lo, hi, why = self._window(p, ctx["earliest"])
            why_window[p.pid] = why
            if centre.get(p.pid) is not None:
                lo = max(lo, centre[p.pid] - window)
                hi = min(hi, centre[p.pid] + self.BUCKET + window + dur[p.pid])
            for m in ctx["machines_of"].get(p.pid, [p.machine]):
                blocks = self._blocks(m, ctx["extra_blocks"], holds=not self.standby(p))
                if p.pid in ctx["locked"]:
                    lm, ls = ctx["locked"][p.pid]
                    if lm != m:
                        continue
                    starts = [int(round((ls - self.t0) / g))]
                else:
                    starts = range(max(0, int((lo - self.t0) // g)), self.T - dslots + 1)
                for s in starts:
                    st, en = self.slot_time(s), self.slot_time(s + dslots)
                    if p.pid not in ctx["locked"]:
                        if st < lo:
                            continue
                        if en > hi:
                            break
                        if any(st < be and en > bs for bs, be, _ in blocks):
                            continue
                    var_p.append(pi); var_m.append(m); var_s.append(s); var_len.append(dslots)
                    costs.append(self._soft_cost(p, st, en, ctx["prev_time"]))

        nx, n_pat = len(var_p), len(patients)
        n = nx + n_pat
        c = costs + [ctx["defer_cost"].get(p.pid, d["weights"]["unscheduled"]
                                           * (5 if (p.complex or p.new_start) else 1))
                     for p in patients]
        rows, cols, vals, lb, ub = [], [], [], [], []
        for j, pi in enumerate(var_p):
            rows.append(pi); cols.append(j); vals.append(1.0)
        for pi in range(n_pat):
            rows.append(pi); cols.append(nx + pi); vals.append(1.0)
        lb += [1.0] * n_pat; ub += [1.0] * n_pat
        r = n_pat

        machines = sorted(set(var_m))
        for m in machines:                                 # machine no-overlap
            for j in range(nx):
                if var_m[j] == m:
                    for t in range(var_s[j], var_s[j] + var_len[j]):
                        rows.append(r + t); cols.append(j); vals.append(1.0)
            lb += [-np.inf] * self.T; ub += [1.0] * self.T
            r += self.T
        for a, spec in d["accessories"].items():           # shared accessories
            users = [j for j in range(nx) if a in patients[var_p[j]].accessories]
            if not users:
                continue
            for j in users:
                for t in range(var_s[j], var_s[j] + var_len[j]):
                    rows.append(r + t); cols.append(j); vals.append(1.0)
            pad = spec["transfer_min"]
            for t in range(self.T):
                st, en = self.slot_time(t), self.slot_time(t + 1)
                at_ct = sum(1 for b in d["ct_sim_bookings"] if b["accessory"] == a
                            and st < b["end"] + pad and en > b["start"] - pad)
                lb.append(-np.inf); ub.append(float(max(spec["units"] - at_ct, 0)))
            r += self.T
        if len(machines) > 1:                              # senior staff
            for j in range(nx):
                if patients[var_p[j]].complex:
                    for t in range(var_s[j], var_s[j] + var_len[j]):
                        rows.append(r + t); cols.append(j); vals.append(1.0)
            lb += [-np.inf] * self.T; ub += [float(d["senior_staff_concurrent"])] * self.T
            r += self.T

        res, secs = _solve_milp(c, rows, cols, vals, lb, ub, nx, n, time_limit, gap)
        out = {p.pid: Assignment(p.pid, None, None, dur[p.pid],
                                 ["NOT SCHEDULED - needs a human decision (overtime or defer)"])
               for p in patients}
        for j in np.flatnonzero(res.x[:nx] > 0.5):
            p = patients[var_p[j]]
            st = self.slot_time(var_s[j])
            out[p.pid] = Assignment(p.pid, var_m[j], st, dur[p.pid],
                                    self._explain(p, st, st + var_len[j] * g,
                                                  why_window[p.pid], ctx["prev_time"]))
        status = "optimal" if res.status == 0 else "time limit (best found)"
        return Schedule(out, status, float(res.fun), secs, n, r, getattr(res, "mip_gap", None))

    # ------------------------------------------------------------ explanation
    def _explain(self, p, start, end, window_reasons, prev_time):
        """Plain reason codes for every placement (fed to the LLM copilot)."""
        d = self.d
        out = list(window_reasons)
        target = p.requested if p.requested is not None else p.usual_time
        label = "preferred" if p.requested is not None else "usual"
        tol = d["weights"]["pref_tolerance_paying" if p.requested is not None else "pref_tolerance"]
        delta = start - target
        if abs(delta) > tol:
            out.append(f"{abs(delta):.0f} min {'later' if delta > 0 else 'earlier'} than "
                       f"{label} time {fmt(target)}")
        else:
            out.append(f"within {tol} min of {label} time {fmt(target)}")
        if p.accessories:
            names = {"BREAST_BOARD": "breast board", "ABC": "ABC"}
            out.append("accessory check: " + " and ".join(names.get(a, a) for a in p.accessories)
                       + " free (CT-simulator bookings and reservations respected)")
        if p.flexible and end > d["late_evening_after"]:
            kind = "inpatient" if p.inpatient else "dormitory" if p.dormitory else "lives nearby"
            out.append(f"{kind}: late-evening slot, keeps earlier slots for stricter constraints")
        if p.elderly and start <= d["elderly_pref_before"]:
            out.append("older patient: earlier slot")
        lead = p.report_lead
        out.append(f"report at {fmt(start - lead)} ({lead} min before"
                   + (": drink 500 mL of water on arrival)" if p.pelvic else ")"))
        for h in d.get("urgent_holds", []):
            if start < h["start"] + h["minutes"] and end > h["start"]:
                out.append("on standby in the urgent-start hold: treated a little later if an "
                           "urgent patient arrives")
        if end > d["regular_end"]:
            out.append(f"runs {end - d['regular_end']:.0f} min into overtime")
        if prev_time and p.pid in prev_time and abs(start - prev_time[p.pid]) >= 1:
            out.append(f"moved {start - prev_time[p.pid]:+.0f} min from published time "
                       f"{fmt(prev_time[p.pid])}")
        return out


def check_plan(patients, schedule, dept: dict | None = None) -> dict:
    """Independent check of every hard rule in a published plan.

    Written separately from the optimiser (the "rule checker" in the design):
    a plan is only offered for approval if this finds no violation.
    """
    d = dept or DEPARTMENT
    g = d["grid_min"]
    rows, problems = [], []
    for p in patients:
        a = schedule.assignments[p.pid]
        if a.start is None:
            continue
        end = a.start + max(1, math.floor(a.planned_minutes / g + 0.5)) * g
        rows.append((p, a.machine, a.start, end))
    rules = {
        "new starts finish by 17:00": [p.pid for p, _, _, e in rows if p.new_start and not p.urgent
                                       and e > d["new_start_latest_end"]],
        "complex cases inside 10:00-17:00": [p.pid for p, _, s, e in rows if p.complex and
                                             (s < d["senior_staff_window"][0] or e > d["senior_staff_window"][1])],
        "MHRC patients inside 16:00-16:55": [p.pid for p, _, s, e in rows if p.mhrc and
                                             (s < d["mhrc_window"][0] or e > d["mhrc_window"][1])],
        "public transport finish by 21:00": [p.pid for p, _, _, e in rows if p.transport
                                             and e > d["public_transport_latest_end"]],
        "blood irradiation 13:30-14:00 kept free": [
            p.pid for p, m, s, e in rows for b in d["machines"][m]["blocks"] if s < b["end"] and e > b["start"]],
        "one patient at a time on each machine": [],
        "accessories never double-booked with the CT simulator": [],
    }
    for i, (p, m, s, e) in enumerate(rows):
        for q, m2, s2, e2 in rows[i + 1:]:
            if m == m2 and s < e2 and s2 < e:
                rules["one patient at a time on each machine"].append(f"{p.pid}/{q.pid}")
        for acc in p.accessories:
            spec = d["accessories"][acc]
            for b in d["ct_sim_bookings"]:
                if b["accessory"] == acc and spec["units"] == 1 and                         s < b["end"] + spec["transfer_min"] and e > b["start"] - spec["transfer_min"]:
                    rules["accessories never double-booked with the CT simulator"].append(p.pid)
    for name, bad in rules.items():
        if bad:
            problems.append(f"{name}: {', '.join(bad)}")
    return {"rules_checked": len(rules), "violations": problems,
            "sessions_checked": len(rows), "unplanned": schedule.unscheduled()}
