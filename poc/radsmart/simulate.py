"""Discrete-event 'digital twin' of a treatment day (Monte Carlo).

A set of appointment times is played out many times under uncertainty:
actual session lengths, patient punctuality, no-shows, same-day urgent
palliative starts, imaging holds, shared-accessory availability, the
blood-irradiation block, the senior-staff window and (optionally) a machine
fault. Every policy is run on the SAME random draws (common random numbers) so
differences come from the policy, not from luck.

Patients are told a reporting time: 20 minutes before their machine slot, or 45
minutes for pelvic patients, who drink 500 mL of water on arrival and cannot be
treated for 30 minutes. Everyone else needs about 10 minutes to check in and
change. In current practice the hourly block IS the reporting time.

Dispatch rules model what staff do on the floor:
  * "fcfs":        current practice - treat whoever is ready first
  * "appointment": RAD-SMART - treat in appointment order; if the machine would
                   otherwise idle, take the next patient already ready
In both, urgent same-day palliative patients go first once ready, and after
16:00 patients from the hospice (MHRC) go first so they catch the 17:00 bus.
Inpatients and dormitory residents are in the building: if the machine would
stand idle, staff call the next one in (ready about 15 minutes later). With
RAD-SMART, patients who live nearby can also be messaged to come early; those
who read the message are ready about 25 minutes later.

Imaging holds: after on-board imaging, the radiation oncologist occasionally
decides not to proceed. Half are repositioned and treated straight away; the
other half are treated later the same day.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .config import DEPARTMENT
from .synth import sample_duration, make_urgent

IMAGING_HOLD_P = 0.02          # per session (assumption: "occasionally")
REPOSITION_MIN = 8             # extra minutes when corrected on the spot
RETURN_AFTER_MIN = 45          # a held patient is ready again this much later
IMAGING_AT = 0.6               # share of the session done when imaging is reviewed


@dataclass
class DayDraw:
    """One random realisation of the day, shared by all policies."""
    dur: dict          # pid -> actual minutes
    offset: dict       # pid -> arrival minus reporting time (minutes)
    noshow: set
    comply: dict       # pid -> reads the rescheduling message?
    urgent: list       # urgent Patient objects appearing today
    hold: dict         # pid -> "reposition" | "later" (imaging holds)


def draw_day(patients, rng, urgent_lambda=1.2, noshow_p=0.02, comply_p=0.85) -> DayDraw:
    urgent = make_urgent(rng, 1, lam=urgent_lambda)
    everyone = list(patients) + urgent
    dur = {p.pid: sample_duration(p, rng) for p in everyone}
    # Most patients come a little before their reporting time; some are late.
    offset = {p.pid: float(np.clip(rng.normal(-5, 12), -40, 25)) for p in everyone}
    for p in urgent:
        offset[p.pid] = 0.0
    noshow = {p.pid for p in patients if rng.random() < noshow_p}
    comply = {p.pid: rng.random() < comply_p for p in patients}
    hold = {}
    for p in everyone:
        if rng.random() < IMAGING_HOLD_P:
            hold[p.pid] = "reposition" if rng.random() < 0.5 else "later"
    return DayDraw(dur, offset, noshow, comply, urgent, hold)


def simulate(patients, appt, rule, estimate, draw: DayDraw, dept=None, fault=None,
             new_appt=None, notified=frozenset(), lead=True, deferred=frozenset()):
    """Play one day.

    appt:      pid -> (machine, minute)   what the patient was told: the machine
               slot (lead=True, RAD-SMART) or the reporting block (lead=False)
    estimate:  pid -> minutes the staff expect (used to judge "fits before block")
    fault:     (machine, start, minutes) unplanned downtime
    new_appt:  pid -> minute   revised slots after re-optimisation (optional)
    notified:  pids that were sent the revised time
    deferred:  pids moved to another day after approval (not treated today)
    """
    d = dept or DEPARTMENT
    new_appt = new_appt or {}
    people = {p.pid: p for p in list(patients) + draw.urgent}
    appt = dict(appt)
    est = dict(estimate)
    for u in draw.urgent:
        appt[u.pid] = (u.machine, u.ready_time)
        est[u.pid] = est.get(u.pid, 15.0)

    # arrival and ready times
    arrival, ready, order_key = {}, {}, {}
    for pid, (m, t) in appt.items():
        if pid in draw.noshow or pid in deferred:
            continue
        p = people[pid]
        told = t
        if pid in notified and pid in new_appt and draw.comply.get(pid, True):
            told = new_appt[pid]
        report = told - (p.report_lead if lead and not p.urgent else 0)
        arrival[pid] = max(d["day_start"] - 60, report + draw.offset[pid])
        if p.mhrc:                                     # everyone on the hospice bus
            arrival[pid] = d["mhrc_bus_arrival"] + abs(draw.offset[pid]) / 4
        prep = 0 if p.urgent else (d["pelvic_fill_min"] if p.pelvic else d["prep_min"])
        ready[pid] = arrival[pid] + prep
        order_key[pid] = new_appt.get(pid, t)          # staff follow the live plan
    first_ready = dict(ready)

    machines = sorted({m for m, _ in appt.values()})
    pending = {m: {pid for pid in ready if appt[pid][0] == m} for m in machines}
    t = {m: float(d["day_start"]) for m in machines}
    blocks = {m: [[b["start"], b["end"] - b["start"], b["label"], False]
                  for b in d["machines"][m]["blocks"]] for m in machines}
    faults = {m: [] for m in machines}
    if fault:
        faults[fault[0]].append([fault[1], fault[2], "Fault", False])
    uses = []                                   # (start, end, accessory, machine)
    complex_runs = []                           # (start, end, machine)
    rec, skips_accessory, not_today, acc_delayed = {}, 0, [], set()
    block_delay = 0.0
    held, n_hold, called = set(), 0, 0
    mhrc_from = d["mhrc_window"][0]

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

    def lead_of(q):
        pq = people[q]
        base = d["call_in_min"] if (pq.inpatient or pq.dormitory) else d["come_early_min"]
        return base + (d["pelvic_fill_min"] if pq.pelvic else 0)

    def call_in(m, now, free_at, nxt):
        """Call the next flexible patient so they are ready when the machine is
        free (free_at) if nobody else will be. Returns the new next-ready time."""
        nonlocal called
        cands = [q for q in pending[m] if q not in held and not people[q].urgent
                 and arrival[q] > now and max(now + lead_of(q), free_at) < min(ready[q], nxt)
                 and (people[q].inpatient or people[q].dormitory
                      or (rule == "appointment" and people[q].nearby and draw.comply.get(q, True)))]
        if not cands:
            return nxt
        q = min(cands, key=lambda x: (order_key[x], x))
        ready[q] = first_ready[q] = max(now + lead_of(q), free_at)
        arrival[q] = ready[q] - (d["pelvic_fill_min"] if people[q].pelvic else d["prep_min"])
        called += 1
        return min(nxt, ready[q])

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
        here = [pid for pid in pending[m] if ready[pid] <= now]
        if not here:
            nxt = min(ready[pid] for pid in pending[m])
            if nxt > now + 5:                               # machine idle: call someone in
                nxt = call_in(m, now, now, nxt)
            upcoming = [b[0] for b in blocks[m] + faults[m] if not b[3] and b[0] > now]
            t[m] = min([nxt] + upcoming)
            continue

        # pid breaks ties so the order never depends on set iteration (hash seed)
        def first(pid):
            p = people[pid]
            return (not p.urgent, not (p.mhrc and now >= mhrc_from))
        if rule == "fcfs":
            here.sort(key=lambda pid: (first(pid), ready[pid], pid))
        else:
            here.sort(key=lambda pid: (first(pid), order_key[pid], ready[pid], pid))
        chosen, retry = None, []
        for pid in here:
            ok, when, why = check(pid, m, now)
            if ok:
                chosen = pid
                break
            if when is None:
                not_today.append(pid)
                pending[m].discard(pid)
            else:
                retry.append(when)
                if why == "accessory" and now >= order_key[pid] and pid not in acc_delayed:
                    acc_delayed.add(pid)          # due now, but held up by a device
                    skips_accessory += 1
        if chosen is None:
            nxt_ready = [ready[pid] for pid in pending[m] if ready[pid] > now]
            upcoming = [b[0] for b in blocks[m] + faults[m] if not b[3] and b[0] > now]
            cand = retry + nxt_ready + upcoming
            t[m] = min(cand) if cand else now + 5
            continue
        p = people[chosen]
        start = now
        minutes = draw.dur[chosen]
        hold = draw.hold.get(chosen) if chosen not in held else None
        if hold == "reposition":
            minutes += REPOSITION_MIN
        elif hold == "later":
            minutes *= IMAGING_AT
        end = start + minutes
        for f in faults[m]:                            # fault hits mid-session
            if not f[3] and start < f[0] < end:
                end += f[1]
                f[3] = True
        for a in p.accessories:
            uses.append((start, end, a, m))
        if p.complex:
            complex_runs.append((start, end, m))
        t[m] = end
        others = [ready[q] for q in pending[m] if q != chosen]
        if others and min(others) > start + est[chosen] + 5:   # look ahead: nobody ready at the end
            call_in(m, start, start + est[chosen], min(others))
        if hold:
            n_hold += 1
        if hold == "later":                            # comes back later today
            held.add(chosen)
            ready[chosen] = end + RETURN_AFTER_MIN
            continue
        got_msg = chosen in notified and chosen in new_appt and draw.comply.get(chosen, True)
        rec[chosen] = dict(machine=m, arrival=arrival[chosen], ready=first_ready[chosen],
                           appt=appt[chosen][1],
                           told=new_appt[chosen] if got_msg else appt[chosen][1],
                           start=start, end=end, new_start=p.new_start, complex=p.complex,
                           urgent=p.urgent, category=_category(p), mhrc=p.mhrc,
                           transport=p.transport, flexible=p.flexible,
                           requested=p.requested, held=chosen in held)
        pending[m].discard(chosen)
    met = _metrics(rec, d, skips_accessory, not_today, block_delay, people, n_hold, len(deferred))
    if met:
        met["called_in_early"] = called
    return met, rec


def _category(p):
    if p.urgent:
        return "urgent"
    if p.complex:
        return "complex"
    if p.new_start:
        return "new_start"
    return "routine"


def _metrics(rec, d, skips_accessory, not_today, block_delay, people, n_hold, n_deferred):
    if not rec:
        return {}
    rows = [r for r in rec.values() if not r["held"]]      # held patients: counted separately
    wtg = np.array([max(0.0, r["start"] - r["arrival"]) for r in rows])
    excess = np.array([max(0.0, r["start"] - r["ready"]) for r in rows])
    late = np.array([r["start"] - r["told"] for r in rows])
    ends = np.array([r["end"] for r in rec.values()])
    last_end = {}
    for r in rec.values():
        last_end[r["machine"]] = max(last_end.get(r["machine"], 0), r["end"])
    overtime = sum(max(0.0, e - d["regular_end"]) for e in last_end.values())
    ns_late = sum(1 for r in rec.values() if r["new_start"] and not r["urgent"]
                  and r["end"] > d["new_start_latest_end"])
    urgent = [r for r in rec.values() if r["urgent"]]
    paying = [r for r in rec.values() if r["requested"] is not None]
    return {
        "patients": len(rec),
        "wait_median": float(np.median(wtg)),
        "wait_p90": float(np.percentile(wtg, 90)),
        "wait_mean": float(np.mean(wtg)),
        "excess_wait_median": float(np.median(excess)),
        "excess_wait_p90": float(np.percentile(excess, 90)),
        "delay_median": float(np.median(np.maximum(late, 0))),
        "within_15_pct": float(np.mean(np.abs(late) <= 15) * 100),
        "within_30_pct": float(np.mean(np.abs(late) <= 30) * 100),
        "overtime_min": float(overtime),
        "last_end": float(ends.max()),
        "new_starts_after_5pm": int(ns_late),
        "complex_deferred": int(sum(1 for pid in not_today if people[pid].complex)),
        "mhrc_missed_bus": int(sum(1 for r in rec.values() if r["mhrc"] and r["end"] > d["mhrc_window"][1])),
        "transport_after_9pm": int(sum(1 for r in rec.values()
                                       if r["transport"] and r["end"] > d["public_transport_latest_end"])),
        "others_after_9pm": int(sum(1 for r in rec.values() if not r["flexible"] and not r["transport"]
                                    and not r["urgent"] and r["end"] > d["late_evening_after"])),
        "paying_within_15_pct": float(100 * np.mean([abs(r["start"] - r["requested"]) <= 15 for r in paying]))
                                if paying else float("nan"),
        "accessory_delays": int(skips_accessory),
        "blood_slot_delay_min": float(block_delay),
        "urgent_same_day_pct": float(100 * sum(1 for r in urgent if r["end"] <= d["urgent_latest_end"])
                                     / len(urgent)) if urgent else float("nan"),
        "imaging_holds": int(n_hold),
        "held_treated_same_day": int(sum(1 for r in rec.values() if r["held"])),
        "deferred": int(n_deferred),
        "time_in_dept_mean": float(np.mean([r["end"] - r["arrival"] for r in rec.values()])),
    }


def waiting_room_curve(rec, t0, t1, step=5):
    """Number of patients waiting (arrived, not yet started) over the day."""
    grid = np.arange(t0 - 60, t1, step)
    arr = np.array([r["arrival"] for r in rec.values()])
    st = np.array([r["start"] for r in rec.values()])
    return grid, np.array([np.sum((arr <= g) & (st > g)) for g in grid])


def monte_carlo(patients, policies, n_rep=300, seed=2026, fault=None):
    """Run every policy on the same n_rep random days.

    policies: name -> dict(appt=..., rule=..., estimate=..., lead=..., new_appt=...,
                           notified=..., deferred=..., fault=...)
    Returns name -> list of metric dicts, name -> mean waiting-room curve, and
    name -> every patient's wait.
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
                                notified=pol.get("notified", frozenset()), lead=pol.get("lead", True),
                                deferred=pol.get("deferred", frozenset()))
            results[name].append(met)
            waits[name].extend(max(0.0, r["start"] - r["arrival"]) for r in rec.values() if not r["held"])
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
