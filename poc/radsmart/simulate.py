"""Discrete-event 'digital twin' of a treatment day (Monte Carlo).

A set of appointment times is played out many times under uncertainty:
actual session lengths, patient punctuality, no-shows, same-day urgent
palliative starts, shared-accessory availability, the blood-irradiation block,
the senior-staff window and (optionally) a machine fault. Every policy is run on
the SAME random draws (common random numbers) so differences come from the
policy, not from luck.

Dispatch rules model what staff do on the floor:
  * "fcfs":        current practice - treat whoever arrived first
  * "appointment": RAD-SMART - treat in appointment order; if the machine would
                   otherwise idle, take the next patient already present
Urgent same-day palliative patients are always taken first once ready.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DEPARTMENT
from .synth import sample_duration, make_urgent


@dataclass
class DayDraw:
    """One random realisation of the day, shared by all policies."""
    dur: dict          # pid -> actual minutes
    offset: dict       # pid -> arrival minus appointment (minutes)
    noshow: set
    comply: dict       # pid -> reads the rescheduling message?
    urgent: list       # urgent Patient objects appearing today


def draw_day(patients, rng, urgent_lambda=1.2, noshow_p=0.02, comply_p=0.85) -> DayDraw:
    urgent = make_urgent(rng, 1, lam=urgent_lambda)
    everyone = list(patients) + urgent
    dur = {p.pid: sample_duration(p, rng) for p in everyone}
    # Patients tend to arrive early (Munshi et al. 2021: 11 min early on average).
    offset = {p.pid: float(np.clip(rng.normal(-10, 12), -40, 25)) for p in everyone}
    for p in urgent:
        offset[p.pid] = 0.0
    noshow = {p.pid for p in patients if rng.random() < noshow_p}
    comply = {p.pid: rng.random() < comply_p for p in patients}
    return DayDraw(dur, offset, noshow, comply, urgent)


def simulate(patients, appt, rule, estimate, draw: DayDraw, dept=None, fault=None,
             new_appt=None, notified=frozenset()):
    """Play one day.

    appt:      pid -> (machine, appointment minute)   what the patient was told
    estimate:  pid -> minutes the staff expect (used to judge "fits before block")
    fault:     (machine, start, minutes) unplanned downtime
    new_appt:  pid -> minute   revised times after re-optimisation (optional)
    notified:  pids that were sent the revised time
    """
    d = dept or DEPARTMENT
    new_appt = new_appt or {}
    people = {p.pid: p for p in list(patients) + draw.urgent}
    appt = dict(appt)
    est = dict(estimate)
    for u in draw.urgent:
        appt[u.pid] = (u.machine, u.ready_time)
        est[u.pid] = est.get(u.pid, 15.0)

    # arrival times
    arrival, order_key = {}, {}
    for pid, (m, t) in appt.items():
        if pid in draw.noshow:
            continue
        told = t
        if pid in notified and pid in new_appt and draw.comply.get(pid, True):
            told = new_appt[pid]
        arrival[pid] = max(d["day_start"] - 45, told + draw.offset[pid])
        order_key[pid] = new_appt.get(pid, t)          # staff follow the live plan

    machines = sorted({m for m, _ in appt.values()})
    pending = {m: {pid for pid in arrival if appt[pid][0] == m} for m in machines}
    t = {m: float(d["day_start"]) for m in machines}
    blocks = {m: [[b["start"], b["end"] - b["start"], b["label"], False]
                  for b in d["machines"][m]["blocks"]] for m in machines}
    faults = {m: [] for m in machines}
    if fault:
        faults[fault[0]].append([fault[1], fault[2], "Fault", False])
    uses = []                                   # (start, end, accessory, machine)
    complex_runs = []                           # (start, end, machine)
    rec, skips_accessory, deferred, acc_delayed = {}, 0, [], set()
    block_delay = 0.0

    def ct_busy(a, s, e):
        pad = d["accessories"][a]["transfer_min"]
        return sum(1 for b in d["ct_sim_bookings"]
                   if b["accessory"] == a and s < b["end"] + pad and e > b["start"] - pad)

    def check(pid, m, now):
        """Can pid start on m at `now`? -> (ok, retry_time or None, reason)."""
        p = people[pid]
        e = est[pid]
        for bs, bl, _, done in blocks[m]:
            if not done and now < bs + bl and now + e > bs:
                return False, bs + bl, "block"
        if p.complex:
            lo, hi = d["senior_staff_window"]
            if now < lo:
                return False, lo, "staff"
            if now + e > hi:
                return False, None, "staff"            # cannot be done today
            busy = [en for s, en, mm in complex_runs if mm != m and s <= now < en]
            if len(busy) >= d["senior_staff_concurrent"]:
                return False, min(busy), "staff"
        for a in p.accessories:
            units = d["accessories"][a]["units"]
            in_use = [en for s, en, aa, mm in uses if aa == a and s <= now < en]
            if len(in_use) + ct_busy(a, now, now + e) >= units:
                nxt = list(in_use)
                pad = d["accessories"][a]["transfer_min"]
                nxt += [b["end"] + pad for b in d["ct_sim_bookings"]
                        if b["accessory"] == a and b["end"] + pad > now]
                return False, (min(nxt) if nxt else now + 5), "accessory"
        return True, None, ""

    while any(pending.values()):
        m = min((mm for mm in machines if pending[mm]), key=lambda mm: t[mm])
        now = t[m]
        # run any block / fault whose start time has passed
        ran = False
        for blk in blocks[m] + faults[m]:
            if not blk[3] and now >= blk[0]:
                if blk[2] != "Fault":
                    block_delay += now - blk[0]
                t[m] = now + blk[1]
                blk[3] = True
                ran = True
                break
        if ran:
            continue
        here = [pid for pid in pending[m] if arrival[pid] <= now]
        if not here:
            nxt = min(arrival[pid] for pid in pending[m])
            upcoming = [b[0] for b in blocks[m] + faults[m] if not b[3] and b[0] > now]
            t[m] = min([nxt] + upcoming)
            continue
        # pid breaks ties so the order never depends on set iteration (hash seed)
        if rule == "fcfs":
            here.sort(key=lambda pid: (not people[pid].urgent, arrival[pid], pid))
        else:
            here.sort(key=lambda pid: (not people[pid].urgent, order_key[pid], arrival[pid], pid))
        chosen, retry = None, []
        for pid in here:
            ok, when, why = check(pid, m, now)
            if ok:
                chosen = pid
                break
            if when is None:
                deferred.append(pid)
                pending[m].discard(pid)
            else:
                retry.append(when)
                if why == "accessory" and now >= order_key[pid] and pid not in acc_delayed:
                    acc_delayed.add(pid)          # due now, but held up by a device
                    skips_accessory += 1
        if chosen is None:
            nxt_arr = [arrival[pid] for pid in pending[m] if arrival[pid] > now]
            upcoming = [b[0] for b in blocks[m] + faults[m] if not b[3] and b[0] > now]
            cand = retry + nxt_arr + upcoming
            t[m] = min(cand) if cand else now + 5
            continue
        p = people[chosen]
        start = now
        end = start + draw.dur[chosen]
        for f in faults[m]:                            # fault hits mid-session
            if not f[3] and start < f[0] < end:
                end += f[1]
                f[3] = True
        for a in p.accessories:
            uses.append((start, end, a, m))
        if p.complex:
            complex_runs.append((start, end, m))
        got_msg = chosen in notified and chosen in new_appt and draw.comply.get(chosen, True)
        rec[chosen] = dict(machine=m, arrival=arrival[chosen], appt=appt[chosen][1],
                           told=new_appt[chosen] if got_msg else appt[chosen][1],
                           start=start, end=end, new_start=p.new_start, complex=p.complex,
                           urgent=p.urgent, category=_category(p))
        pending[m].discard(chosen)
        t[m] = end
    return _metrics(rec, d, skips_accessory, deferred, block_delay, people), rec


def _category(p):
    if p.urgent:
        return "urgent"
    if p.complex:
        return "complex"
    if p.new_start:
        return "new_start"
    return "routine"


def _metrics(rec, d, skips_accessory, deferred, block_delay, people):
    if not rec:
        return {}
    starts = np.array([r["start"] for r in rec.values()])
    wtg = np.array([max(0.0, r["start"] - r["arrival"]) for r in rec.values()])
    late = np.array([r["start"] - r["told"] for r in rec.values()])
    ends = np.array([r["end"] for r in rec.values()])
    last_end = {}
    for r in rec.values():
        last_end[r["machine"]] = max(last_end.get(r["machine"], 0), r["end"])
    overtime = sum(max(0.0, e - d["regular_end"]) for e in last_end.values())
    ns_late = sum(1 for r in rec.values() if (r["new_start"] or r["urgent"])
                  and r["end"] > d["new_start_latest_end"])
    urgent = [r for r in rec.values() if r["urgent"]]
    return {
        "patients": len(rec),
        "wait_median": float(np.median(wtg)),
        "wait_p90": float(np.percentile(wtg, 90)),
        "wait_mean": float(np.mean(wtg)),
        "delay_median": float(np.median(np.maximum(late, 0))),
        "within_15_pct": float(np.mean(np.abs(late) <= 15) * 100),
        "within_30_pct": float(np.mean(np.abs(late) <= 30) * 100),
        "overtime_min": float(overtime),
        "new_starts_after_5pm": int(ns_late),
        "complex_deferred": int(sum(1 for pid in deferred if people[pid].complex)),
        "accessory_delays": int(skips_accessory),
        "blood_slot_delay_min": float(block_delay),
        "urgent_same_day_pct": float(100 * sum(1 for r in urgent if r["end"] <= d["new_start_latest_end"])
                                     / len(urgent)) if urgent else float("nan"),
        "last_end": float(ends.max()),
        "time_in_dept_mean": float(np.mean([r["end"] - r["arrival"] for r in rec.values()])),
    }


def waiting_room_curve(rec, t0, t1, step=5):
    """Number of patients waiting (arrived, not yet started) over the day."""
    grid = np.arange(t0 - 30, t1, step)
    arr = np.array([r["arrival"] for r in rec.values()])
    st = np.array([r["start"] for r in rec.values()])
    return grid, np.array([np.sum((arr <= g) & (st > g)) for g in grid])


def monte_carlo(patients, policies, n_rep=300, seed=2026, fault=None):
    """Run every policy on the same n_rep random days.

    policies: name -> dict(appt=..., rule=..., estimate=..., new_appt=..., notified=...)
    Returns name -> list of metric dicts, and name -> mean waiting-room curve.
    """
    rng = np.random.default_rng(seed)
    results = {k: [] for k in policies}
    curves = {k: [] for k in policies}
    waits = {k: [] for k in policies}
    grid = None
    for _ in range(n_rep):
        draw = draw_day(patients, rng)
        for name, pol in policies.items():
            met, rec = simulate(patients, pol["appt"], pol["rule"], pol["estimate"], draw,
                                fault=pol.get("fault", fault), new_appt=pol.get("new_appt"),
                                notified=pol.get("notified", frozenset()))
            results[name].append(met)
            waits[name].extend(max(0.0, r["start"] - r["arrival"]) for r in rec.values())
            grid, c = waiting_room_curve(rec, DEPARTMENT["day_start"], DEPARTMENT["hard_end"] + 60)
            curves[name].append(c)
    curves = {k: (grid, np.mean(v, axis=0)) for k, v in curves.items()}
    return results, curves, {k: np.array(v) for k, v in waits.items()}


def summarise(results) -> dict:
    """Mean of each metric over replications (plus 95% interval for waits)."""
    out = {}
    for name, runs in results.items():
        keys = runs[0].keys()
        s = {}
        for k in keys:
            vals = np.array([r[k] for r in runs], dtype=float)
            vals = vals[~np.isnan(vals)]
            s[k] = float(vals.mean()) if len(vals) else float("nan")
            if k in ("wait_median", "wait_p90"):
                s[k + "_ci"] = [float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))]
        out[name] = s
    return out
