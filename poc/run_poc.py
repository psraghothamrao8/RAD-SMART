"""Run every RAD-SMART proof-of-concept experiment and write results + figures.

    python run_poc.py            # a few minutes on a laptop

Outputs (poc/results/):
    results.json              all numbers quoted in the report
    web_data.json             chart data for the interactive results page
    schedule_rad_smart.csv    the optimised day plan with reason codes
    fig*.png                  figures used in the report and deck

Patients are synthetic (fake); the department's rules come from its answers to
our questions (21 Sep 2026). Results show how the method behaves under stated
assumptions; they are not clinical evidence. Real numbers come from the pilot's
baseline and shadow-mode phases.
"""

from __future__ import annotations

import csv
import json
import time
from collections import Counter
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from radsmart.config import DEPARTMENT, TECHNIQUES, TBI_PLAN, ct_booking_problems, fmt, hm
from radsmart.duration_model import LookupPredictor, QuantileGBMPredictor, evaluate
from radsmart.forecast import (capacity_profile, committed_load, daily_capacity, make_pipeline,
                               naive, occupancy_label, recommend)
from radsmart.scheduler import DayScheduler, check_plan, planning_minutes
from radsmart.simulate import monte_carlo, summarise
from radsmart.synth import available_minutes, expected_duration, make_day, make_history

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
N_REP = 300
N_PATIENTS = 87            # planned the evening before; 0-3 urgent starts join on the day
FAULTS = [                 # the department's two downtime rules
    ("short", "45-minute fault at 11:00", ("VERSA", hm("11:00"), 45)),
    ("long", "150-minute fault at 10:00", ("VERSA", hm("10:00"), 150)),
]
TBI_DAYS = [10, 11, 12]    # working days 11-13 of the forecast (known a month ahead)
PIPELINE_RATE = 7.0        # new patients approved per working day (two machines)

# ---------------------------------------------------------------- chart style
SURFACE, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BASE, RS_AVG, RS_ML, RS_LIVE = MUTED, "#86b6ef", "#2a78d6", "#104281"   # validated ordinal ramp
CAT = {"routine": "#2a78d6", "new_start": "#eb6834", "complex": "#1baf7a"}  # categorical slots 1-3
plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"], "font.size": 9,
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "text.color": INK, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6, "grid.linestyle": "-",
    "axes.axisbelow": True, "legend.frameon": False, "lines.linewidth": 2,
})


def title(ax, head, sub=None):
    ax.set_title(head, loc="left", fontsize=10.5, fontweight="bold", color=INK, pad=18 if sub else 8)
    if sub:
        ax.text(0, 1.02, sub, transform=ax.transAxes, fontsize=8.5, color=INK2, va="bottom")


def hour_axis(ax, lo, hi, step=180):
    ticks = list(range(int(np.ceil(lo / 60)) * 60, int(hi) + 1, step))
    ax.set_xticks(ticks)
    ax.set_xticklabels([fmt(t) for t in ticks])
    ax.set_xlim(lo, hi)


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close(fig)


def flags_of(p):
    return [n for n, v in (("new start", p.new_start), ("complex", p.complex), ("older", p.elderly),
                           ("inpatient", p.inpatient), ("MHRC", p.mhrc), ("dormitory", p.dormitory),
                           ("lives nearby", p.nearby), ("public transport", p.transport),
                           ("paying", p.paying), ("pelvic", p.pelvic)) if v]


# ------------------------------------------------------------------ experiments
def main():
    tic = time.perf_counter()
    d = DEPARTMENT
    assert not ct_booking_problems(), ct_booking_problems()
    res = {"assumptions": {
        "data": "synthetic (fake) patients; department rules from its answers (21 Sep 2026)",
        "operating_day": f"{fmt(d['day_start'])}-{fmt(d['regular_end'])} (overtime to {fmt(d['hard_end'])})",
        "patients": f"{N_PATIENTS} planned + 0-3 same-day urgent starts (ceiling {d['patient_ceiling']})",
        "blood_irradiation": "13:30-14:00 on Versa HD",
        "senior_staff_window": "10:00-17:00", "protected_block": "12:00-13:30",
        "new_start_cut_off": "17:00", "urgent_cut_off": "18:00",
        "mhrc": "16:00-17:00 slots, 17:00 bus", "public_transport": "finish by 21:00",
        "deadline_buffer_min": d["deadline_buffer_min"],
        "reporting": "20 min before the slot; pelvic 45 min (500 mL water, 30 min wait)",
        "accessories": "1 breast board, 1 ABC, shared with the CT simulator (11:00-18:00), 2-min transfer",
        "urgent_same_day_starts_per_day": "Poisson(1.2) capped at 3, ready 13:00-16:30",
        "imaging_holds": "2% of sessions; half repositioned at once, half treated later the same day",
        "no_show_rate": 0.02, "arrival_offset": "Normal(-5, 12) min around the reporting time, clipped to [-40, +25]",
        "message_compliance": 0.85, "replications": N_REP,
    }}

    # 1. duration prediction ------------------------------------------------
    hist = make_history(n_sessions=12000)
    train, test = hist[:10000], hist[10000:]
    lookup = LookupPredictor().fit(train)
    ml = QuantileGBMPredictor().fit(train)
    ev = evaluate([lookup, ml], test)
    res["duration_model"] = {k: {kk: round(vv, 2) for kk, vv in v.items() if kk != "errors"}
                             for k, v in ev.items()}
    fig_duration(ev)
    pct = np.arange(0, 101)
    web = {"duration_abs_error_percentiles": {k: np.percentile(np.abs(v["errors"]), pct).round(2).tolist()
                                              for k, v in ev.items()}}

    # 2. one treatment day, single machine (today's department) ---------------
    day = make_day(seed=7, n_patients=N_PATIENTS)
    load = sum(expected_duration(p) for p in day)
    res["day"] = {"patients": len(day), "new_starts": sum(p.new_start for p in day),
                  "complex": sum(p.complex for p in day),
                  "expected_machine_minutes": round(load),
                  "available_minutes": available_minutes("VERSA"),
                  "load_pct": round(100 * load / available_minutes("VERSA"), 1),
                  "priority_mix": {
                      "older_70_plus": sum(p.elderly for p in day), "inpatient": sum(p.inpatient for p in day),
                      "mhrc": sum(p.mhrc for p in day), "dormitory": sum(p.dormitory for p in day),
                      "nearby": sum(p.nearby for p in day), "flexible": sum(p.flexible for p in day),
                      "public_transport": sum(p.transport for p in day), "paying": sum(p.paying for p in day),
                      "preferred_time": sum(p.requested is not None for p in day),
                      "pelvic": sum(p.pelvic for p in day),
                      "abc": sum("ABC" in p.accessories for p in day),
                      "breast_board": sum("BREAST_BOARD" in p.accessories for p in day)},
                  "languages": dict(Counter(p.language for p in day).most_common())}
    sch = DayScheduler()
    s_avg = sch.solve(day, lookup)
    s_ml = sch.solve(day, ml)
    res["solver"] = {name: {"seconds": round(s.solve_seconds, 1), "status": s.status,
                            "proven_gap_pct": round(100 * (s.mip_gap or 0), 2),
                            "unscheduled": s.unscheduled(), "variables": s.n_variables,
                            "constraints": s.n_constraints}
                     for name, s in (("averages", s_avg), ("ml", s_ml))}
    res["plan_check"] = {name: check_plan(day, s) for name, s in (("averages", s_avg), ("ml", s_ml))}
    res["plan"] = plan_stats(day, s_ml)
    est_avg, est_ml = planning_minutes(day, lookup), planning_minutes(day, ml)
    policies = {
        "Current practice": dict(appt={p.pid: (p.machine, p.usual_time) for p in day},
                                 rule="fcfs", estimate=est_avg, lead=False),
        "RAD-SMART (averages)": dict(appt=appt_of(s_avg, day), rule="appointment", estimate=est_avg),
        "RAD-SMART (ML)": dict(appt=appt_of(s_ml, day), rule="appointment", estimate=est_ml),
    }
    results, curves, waits = monte_carlo(day, policies, n_rep=N_REP)
    res["day_results"] = rounded(summarise(results))
    fig_waits(waits, res["day_results"])
    fig_waiting_room(curves, {"Current practice": BASE, "RAD-SMART (averages)": RS_AVG,
                              "RAD-SMART (ML)": RS_ML},
                     "fig2_waiting_room.png", "Patients waiting in the department",
                     "Average over 300 simulated days, same patients and random events for every policy")
    fig_gantt(day, s_ml)
    write_schedule(day, s_ml)
    web["wait_percentiles"] = {k: np.percentile(v, pct).round(1).tolist() for k, v in waits.items()}
    web["waiting_room"] = curve_json(curves)
    web["schedule"] = schedule_json(day, s_ml)
    web["department"] = {k: d.get(k) for k in (
        "day_start", "regular_end", "hard_end", "protected_block", "senior_staff_window",
        "new_start_latest_end", "urgent_latest_end", "mhrc_window", "public_transport_latest_end",
        "urgent_holds", "ct_sim_bookings", "ct_sim_hours", "accessory_reservations")}
    web["department"]["machine_blocks"] = d["machines"]["VERSA"]["blocks"]

    # 2b. how much capacity to hold for urgent starts: waits versus finishing time
    res["buffer_tradeoff"] = buffer_tradeoff(day, ml, est_ml, policies["Current practice"])

    # 3. machine downtime: the department's two rules --------------------------
    res["disruption"], res["disruption_results"], web["scenarios"] = {}, {}, {}
    fault_curves = {}
    for key, label, fault in FAULTS:
        rp = reoptimise(sch, day, s_ml, ml, fault)
        res["disruption"][key] = {
            "label": label, "rule": rp["rule"],
            "reoptimisation_seconds": round(rp["schedule"].solve_seconds, 1),
            "patients_replanned": len(rp["new_appt"]), "patients_moved": rp["moved"],
            "patients_messaged": len(rp["notified"]),
            "new_starts_moved_to_next_day": sorted(rp["postponed"]),
            "deferral_proposals": sorted(rp["deferred"] - rp["postponed"]),
            "plan_check": check_plan([p for p in day if p.pid in rp["patients"]], rp["schedule"]),
        }
        dpol = {
            "Current practice": dict(policies["Current practice"], fault=fault),
            "RAD-SMART plan, no re-planning": dict(policies["RAD-SMART (ML)"], fault=fault),
            "RAD-SMART live re-planning + messages": dict(policies["RAD-SMART (ML)"], fault=fault,
                                                          new_appt=rp["new_appt"], notified=rp["notified"],
                                                          deferred=frozenset(rp["deferred"])),
        }
        dres, dcurves, _ = monte_carlo(day, dpol, n_rep=N_REP, seed=99)
        res["disruption_results"][key] = rounded(summarise(dres))
        fault_curves[key] = dcurves
        web["scenarios"][key] = {"label": label, "start": fault[1], "minutes": fault[2],
                                 **res["disruption"][key], "waiting_room": curve_json(dcurves)}
        for row in web["schedule"]:
            pid = row["pid"]
            row.setdefault("scen", {})[key] = {
                "t": float(rp["new_appt"][pid]) if pid in rp["new_appt"] else None,
                "notified": pid in rp["notified"], "deferred": pid in rp["deferred"],
                "postponed": pid in rp["postponed"]}
    fig_disruption(res["disruption_results"])
    for key, label, fault in FAULTS:
        fig_waiting_room(fault_curves[key], dict(zip(fault_curves[key], (BASE, RS_AVG, RS_LIVE))),
                         f"fig4{'b' if key == 'short' else 'c'}_fault_waiting_room.png",
                         f"{label[0].upper()}{label[1:]}: patients waiting in the department",
                         "Average over 300 simulated days", fault=fault)

    # 4. two machines, three weeks, a TBI course: new-start recommendations ----
    M, H = ("VERSA", "HALCYON"), 15
    day2 = make_day(seed=21, machines=M)
    committed, completing = committed_load(day2, ml, H, M)
    cands = make_pipeline(ml, H, rate=PIPELINE_RATE, machines=M)
    cap = {m: capacity_profile(m, H, TBI_DAYS) for m in M}
    plan, starts, rec_load, waiting, rs_delay = recommend(committed, cands, H, M, cap=cap)
    heads = {m: sum(p.machine == m for p in day2) for m in M}
    taper = (TBI_DAYS[0] - 5, TBI_DAYS[-1])
    n_starts, n_load, n_delay = naive(committed, cands, H, M, headcount=heads, taper=taper)
    flat = {m: daily_capacity(m) for m in M}
    days = working_days(H)
    res["forecast"] = {
        "machines": {m: d["machines"][m]["label"] for m in M},
        "patients_on_treatment": heads, "pipeline_patients": len(cands),
        "daily_capacity_min": {m: round(flat[m]) for m in M},
        "tbi": {"machine": TBI_PLAN["machine"], "days": [days[k] for k in TBI_DAYS],
                "minutes_per_day": len(TBI_PLAN["slots"]) * TBI_PLAN["fraction_min"],
                "manual_taper": f"at most 2 new starts a day on days {taper[0] + 1}-{taper[1] + 1}"},
        "table": [{"day": days[k], "tbi": k in TBI_DAYS,
                   **{f"{m}_committed_pct": round(100 * committed[m][k] / flat[m]) for m in M},
                   **{f"{m}_completing": int(completing[m][k]) for m in M},
                   **{f"{m}_recommended_starts": int(starts[m][k]) for m in M},
                   **{f"{m}_occupancy": occupancy_label(100 * rec_load[m][k] / cap[m][k]) for m in M}}
                  for k in range(H)],
        "rad_smart_peak_pct": {m: round(float(100 * (rec_load[m][2:] / cap[m][2:]).max())) for m in M},
        "headcount_peak_pct": {m: round(float(100 * (n_load[m][2:] / cap[m][2:]).max())) for m in M},
        "rad_smart_tbi_peak_pct": round(float(100 * max(rec_load["VERSA"][k] / cap["VERSA"][k] for k in TBI_DAYS))),
        "headcount_tbi_peak_pct": round(float(100 * max(n_load["VERSA"][k] / cap["VERSA"][k] for k in TBI_DAYS))),
        "headcount_days_over_capacity": {m: int((n_load[m][2:] > cap[m][2:] + 1e-6).sum()) for m in M},
        "rad_smart_days_over_capacity": {m: int((rec_load[m][2:] > cap[m][2:] + 1e-6).sum()) for m in M},
        "rad_smart_mean_days_to_start": round(float(np.mean(rs_delay)), 1) if rs_delay else 0.0,
        "headcount_mean_days_to_start": round(float(np.mean(n_delay)), 1) if n_delay else 0.0,
        "still_waiting_at_horizon": len(waiting),
    }
    fig_forecast(days, committed, rec_load, n_load, flat, cap, M)
    web["forecast"] = {"days": days, "labels": res["forecast"]["machines"], "tbi_days": TBI_DAYS,
                       "capacity": {m: round(float(flat[m]), 1) for m in M},
                       "capacity_by_day": {m: np.asarray(cap[m], dtype=float).round(1).tolist() for m in M},
                       **{key: {m: np.asarray(src[m], dtype=float).round(1).tolist() for m in M}
                          for key, src in (("committed", committed), ("rad_smart", rec_load),
                                           ("headcount", n_load))},
                       "recommended_starts": {m: [int(x) for x in starts[m]] for m in M},
                       "headcount_starts": {m: [int(x) for x in n_starts[m]] for m in M},
                       "completing": {m: [int(x) for x in completing[m]] for m in M}}

    res["runtime_seconds"] = round(time.perf_counter() - tic, 1)
    (OUT / "results.json").write_text(json.dumps(res, indent=2))
    web["results"] = res
    (OUT / "web_data.json").write_text(json.dumps(web))
    (OUT / "run_log.txt").write_text(print_summary(res), encoding="utf-8")


# ------------------------------------------------------------------ helpers
def appt_of(schedule, day):
    """Appointment times from a schedule; anyone unscheduled keeps their usual time
    (in the product they are flagged for the designated approver instead)."""
    out = {}
    for p in day:
        a = schedule.assignments[p.pid]
        out[p.pid] = (a.machine or p.machine, a.start if a.start is not None else p.usual_time)
    return out


def buffer_tradeoff(day, predictor, estimate, baseline):
    """Re-plan the same day with 40, 20 and 0 minutes held for urgent starts and
    simulate each: a department choice between shorter waits and an earlier finish."""
    d = DEPARTMENT
    saved = d["urgent_holds"]
    variants = [("40 min held (two 20-min holds)", saved), ("20 min held (one hold at 14:40)", saved[:1]),
                ("Nothing held", [])]
    pols, out = {"Current practice": baseline}, []
    try:
        for label, holds in variants:
            d["urgent_holds"] = holds
            s = DayScheduler().solve(day, predictor)
            pols[label] = dict(appt=appt_of(s, day), rule="appointment", estimate=estimate)
    finally:
        d["urgent_holds"] = saved
    S = summarise(monte_carlo(day, pols, n_rep=N_REP)[0])
    for label in pols:
        r = S[label]
        out.append({"policy": label, "wait_median": round(r["wait_median"], 1),
                    "wait_p90": round(r["wait_p90"], 1), "within_15_pct": round(r["within_15_pct"], 1),
                    "last_end": fmt(r["last_end"]), "overtime_min": round(r["overtime_min"], 1),
                    "urgent_same_day_pct": round(r["urgent_same_day_pct"], 1)})
    return out


def plan_stats(day, s):
    d = DEPARTMENT
    rows = [(p, s.assignments[p.pid]) for p in day if s.assignments[p.pid].start is not None]
    ends = {p.pid: a.start + a.planned_minutes for p, a in rows}
    pay = [(p, a) for p, a in rows if p.requested is not None]
    late = [p for p, a in rows if ends[p.pid] > d["late_evening_after"]]
    return {
        "planned_last_end": fmt(max(ends.values())),
        "paying_with_preference": len(pay),
        "paying_within_15_min": sum(abs(a.start - p.requested) <= 15 for p, a in pay),
        "sessions_after_21": len(late),
        "sessions_after_21_flexible": sum(p.flexible for p in late),
        "older_before_13": sum(a.start <= d["elderly_pref_before"] for p, a in rows if p.elderly),
        "older": sum(p.elderly for p, _ in rows),
        "complex_in_protected_block": sum(d["protected_block"][0] <= a.start < d["protected_block"][1]
                                          for p, a in rows if p.complex),
        "mhrc_slots": [fmt(a.start) for p, a in rows if p.mhrc],
    }


def reoptimise(sch, day, s_plan, predictor, fault):
    """Re-plan the rest of the day when the machine fails at fault[1] for fault[2] min.

    Department rules: up to 60 min, nobody is sent home, every ongoing patient is
    treated today and only new starts that can no longer finish by 17:00 are
    proposed for deferral. Over 120 min, new starts move to the next working day
    (urgent palliative starts excepted) and, if the day cannot hold everyone,
    some ongoing patients are proposed for deferral. The oncologist or senior RTT
    approves every deferral.
    """
    d = DEPARTMENT
    m, f0, flen = fault
    long = flen > d["downtime_long_min"]
    remaining = [p for p in day if s_plan.assignments[p.pid].start is not None
                 and s_plan.assignments[p.pid].start >= f0]
    notice = f0 + 45                         # patients booked later can still be told
    prev = {p.pid: s_plan.assignments[p.pid].start for p in remaining}
    postponed = {p.pid for p in remaining if long and p.new_start and not p.urgent}
    todo = [p for p in remaining if p.pid not in postponed]
    earliest = {p.pid: (f0 + flen if prev[p.pid] < notice else notice) for p in todo}
    # Who is proposed first if the day cannot hold everyone: patients who can
    # still be told before leaving home, never those already here or on the MHRC bus.
    defer_cost = {}
    for p in todo:
        if p.new_start or p.complex:
            continue                         # default (5x): kept unless impossible
        defer_cost[p.pid] = 5000.0 if p.mhrc else 3000.0 if prev[p.pid] < notice else 1000.0
    present = {p.pid for p in todo if prev[p.pid] < notice}
    s = sch.solve(todo, predictor, earliest=earliest, prev_time=prev, defer_cost=defer_cost,
                  present=present, time_limit=10.0,
                  extra_blocks={m: [(d["day_start"], f0 + flen, "Past / fault")]})
    new_appt = {pid: a.start for pid, a in s.assignments.items() if a.start is not None}
    deferred = set(s.unscheduled()) | postponed
    moved = sum(1 for pid in new_appt if abs(new_appt[pid] - prev[pid]) >= 5)
    notified = frozenset([pid for pid in new_appt if prev[pid] >= notice and abs(new_appt[pid] - prev[pid]) >= 5]
                         + [pid for pid in deferred if prev[pid] >= notice])
    rule = ("over 120 min: new starts to the next day (urgent palliative excepted); "
            "ongoing patients deferred only if the day cannot hold them" if long else
            "up to 60 min: nobody sent home; all ongoing patients treated today; "
            "new starts deferred only if they can no longer finish by 17:00")
    return dict(new_appt=new_appt, notified=notified, deferred=deferred, postponed=postponed,
                moved=moved, schedule=s, patients={p.pid for p in todo}, rule=rule)


def curve_json(curves):
    """Mean patients waiting over the day, per policy, on one shared time grid."""
    grid = next(iter(curves.values()))[0]
    return {"grid": [float(g) for g in grid],
            "series": {pol: np.asarray(c, dtype=float).round(2).tolist() for pol, (_, c) in curves.items()}}


def schedule_json(day, s):
    rows = []
    for p in day:
        a = s.assignments[p.pid]
        rows.append({"pid": p.pid, "start": float(a.start), "minutes": round(float(a.planned_minutes), 1),
                     "cat": "complex" if p.complex else ("new_start" if p.new_start else "routine"),
                     "technique": TECHNIQUES[p.technique]["label"],
                     "fraction": f"{p.fraction_no}/{p.total_fx}", "usual": float(p.usual_time),
                     "preferred": float(p.requested) if p.requested is not None else None,
                     "report": float(a.start - p.report_lead), "pelvic": p.pelvic,
                     "accessories": list(p.accessories), "flags": flags_of(p),
                     "language": p.language, "reasons": list(a.reasons)})
    return sorted(rows, key=lambda r: r["start"])


def rounded(d):
    return {k: {kk: (round(vv, 1) if isinstance(vv, float) else [round(x, 1) for x in vv]
                     if isinstance(vv, list) else vv) for kk, vv in v.items()} for k, v in d.items()}


def working_days(n):
    names = ["Mon", "Tue", "Wed", "Thu", "Fri"]
    return [f"{names[k % 5]} (day {k + 1})" for k in range(n)]


def write_schedule(day, s):
    rows = sorted(((s.assignments[p.pid], p) for p in day), key=lambda x: x[0].start)
    with open(OUT / "schedule_rad_smart.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["slot", "report_by", "patient", "technique", "fraction", "planned_min",
                    "flags", "language", "current_reporting_time", "why"])
        for a, p in rows:
            w.writerow([fmt(a.start), fmt(a.start - p.report_lead), p.pid, TECHNIQUES[p.technique]["label"],
                        f"{p.fraction_no}/{p.total_fx}", round(a.planned_minutes, 1),
                        "; ".join(flags_of(p) + [{"BREAST_BOARD": "breast board"}.get(x, x) for x in p.accessories]), p.language, fmt(p.usual_time),
                        " | ".join(a.reasons)])


# --------------------------------------------------------------------- figures
def fig_duration(ev):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    for name, color in (("Lookup table (averages)", RS_AVG), ("Quantile gradient boosting", RS_ML)):
        e = np.sort(np.abs(ev[name]["errors"]))
        y = np.arange(1, len(e) + 1) / len(e) * 100
        ax.plot(e, y, color=color, label=f"{name}  (MAE {ev[name]['mae_min']:.1f} min)")
        y3 = ev[name]["within_3min_pct"]
        ax.plot([3], [y3], "o", ms=6, color=color, mec=SURFACE, mew=2)
        above = color == RS_ML           # empty space: above-left of ML, below-right of lookup
        ax.annotate(f"{y3:.0f}% within 3 min", (3, y3), xytext=(-8, 6) if above else (8, -8),
                    textcoords="offset points", fontsize=8, color=INK2,
                    ha="right" if above else "left", va="bottom" if above else "top")
    ax.set_xlim(0, 12); ax.set_ylim(0, 100)
    ax.set_xlabel("Absolute error of predicted session length (minutes)")
    ax.set_ylabel("% of held-out sessions")
    ax.legend(loc="lower right")
    title(ax, "Predicting machine minutes", "2,000 held-out synthetic sessions")
    save(fig, "fig6_duration_prediction.png")


def fig_waits(waits, summary):
    fig, ax = plt.subplots(figsize=(6.4, 3.2))
    colors = {"Current practice": BASE, "RAD-SMART (averages)": RS_AVG, "RAD-SMART (ML)": RS_ML}
    for name, color in colors.items():
        e = np.sort(waits[name])
        y = np.arange(1, len(e) + 1) / len(e) * 100
        med = summary[name]["wait_median"]          # the typical day's median (KPI tables)
        ax.plot(e, y, color=color, label=f"{name}: median {med:.0f} min")
        ax.plot([med], [100 * np.searchsorted(e, med) / len(e)], "o", ms=6, color=color, mec=SURFACE, mew=2)
    ax.set_xlim(0, 300); ax.set_ylim(0, 100)
    ax.set_xticks(range(0, 301, 30))
    ax.set_xlabel("Minutes from arrival to entering the treatment room (includes the 20/45-min preparation)")
    ax.set_ylabel("% of patients treated within")
    ax.legend(loc="lower right")
    title(ax, "How long patients wait",
          f"Synthetic {N_PATIENTS}-patient day on one machine, {N_REP} simulated days; dots mark the typical day's median")
    save(fig, "fig1_wait_distribution.png")


def fig_waiting_room(curves, colors, name, head, sub, fault=None):
    d = DEPARTMENT
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    for pol, color in colors.items():
        grid, c = curves[pol]
        ax.plot(grid, c, color=color, label=pol)
    if fault:
        ax.axvspan(fault[1], fault[1] + fault[2], color=GRID, lw=0)
        ax.text(fault[1] + fault[2] + 8, ax.get_ylim()[1] * 0.95, "machine\nfault", fontsize=8, color=INK2,
                ha="left", va="top")
    hour_axis(ax, d["day_start"] - 60, d["hard_end"] + 60)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Patients waiting (mean)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8)
    title(ax, head, sub)
    save(fig, name)


def fig_gantt(day, s):
    d = DEPARTMENT
    fig, ax = plt.subplots(figsize=(7.2, 2.7))
    lanes = {"Versa HD": 2, "ABC (1 unit)": 1, "Breast board (1 unit)": 0}
    ax.axvspan(*d["protected_block"], color="#eef4fc", lw=0)
    ax.text(sum(d["protected_block"]) / 2, 2.62, "complex\nblock", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.axvspan(d["mhrc_window"][0], hm("17:00"), color="#fdf1ea", lw=0)
    ax.text(hm("16:30"), 2.62, "MHRC\n16-17", ha="center", va="bottom", fontsize=7, color=INK2)
    ax.axvline(d["public_transport_latest_end"], color=AXIS, lw=1, ls=(0, (3, 3)))
    ax.text(d["public_transport_latest_end"] + 6, 2.62, "public transport\nhome by 21:00", ha="left",
            va="bottom", fontsize=7, color=INK2)
    for b in d["machines"]["VERSA"]["blocks"]:
        ax.add_patch(Rectangle((b["start"], 2 - 0.3), b["end"] - b["start"], 0.6, color=MUTED, lw=0))
    for h in d["urgent_holds"]:
        ax.add_patch(Rectangle((h["start"], 2 - 0.3), h["minutes"], 0.6, fill=False,
                               ec=MUTED, lw=1, hatch="////"))
    lane_of = {"ABC": lanes["ABC (1 unit)"], "BREAST_BOARD": lanes["Breast board (1 unit)"]}
    for b in d["ct_sim_bookings"]:
        lane = lane_of[b["accessory"]]
        ax.add_patch(Rectangle((b["start"], lane - 0.3), b["end"] - b["start"], 0.6, color=MUTED, lw=0))
    for p in day:
        a = s.assignments[p.pid]
        if a.start is None:          # flagged for the approver, not drawn
            continue
        cat = "complex" if p.complex else "new_start" if p.new_start else "routine"
        ax.add_patch(Rectangle((a.start, 2 - 0.3), a.planned_minutes, 0.6, color=CAT[cat],
                               lw=0.5, ec=SURFACE))
        for acc in p.accessories:
            lane = lane_of[acc]
            ax.add_patch(Rectangle((a.start, lane - 0.3), a.planned_minutes, 0.6, color=CAT[cat],
                                   lw=0.5, ec=SURFACE))
    ax.set_yticks(list(lanes.values())); ax.set_yticklabels(list(lanes.keys()))
    ax.tick_params(axis="y", length=0, labelcolor=INK2)
    ax.set_ylim(-0.6, 3.25)
    ax.grid(axis="y", visible=False)
    hour_axis(ax, d["day_start"], d["regular_end"], step=120)
    handles = [Rectangle((0, 0), 1, 1, color=CAT["routine"]), Rectangle((0, 0), 1, 1, color=CAT["new_start"]),
               Rectangle((0, 0), 1, 1, color=CAT["complex"]), Rectangle((0, 0), 1, 1, color=MUTED),
               Rectangle((0, 0), 1, 1, fill=False, ec=MUTED, hatch="////")]
    ax.legend(handles, ["Routine", "New start", "Complex", "Blood irradiation / CT simulator",
                        "Urgent-start hold"], loc="upper center", bbox_to_anchor=(0.5, -0.16),
              ncol=5, fontsize=7.5, handlelength=1.2, columnspacing=1.2)
    last = max(a.start + a.planned_minutes for a in s.assignments.values() if a.start is not None)
    title(ax, "One optimised day", f"{len(day)} patients on Versa HD, {fmt(d['day_start'])} to {fmt(last)}; "
                                   "accessories never double-booked with the CT simulator")
    save(fig, "fig3_optimised_day.png")


def fig_disruption(summary):
    keys = list(summary)
    names = list(summary[keys[0]])
    colors = [BASE, RS_AVG, RS_LIVE]
    fig, axes = plt.subplots(1, len(keys), figsize=(6.8, 2.5), sharey=True)
    for ax, key, (_, label, _) in zip(axes, keys, FAULTS):
        vals = [summary[key][n]["wait_median"] for n in names]
        y = np.arange(len(names))[::-1]
        ax.barh(y, vals, height=0.55, color=colors)
        for yy, v in zip(y, vals):
            ax.text(v + max(vals) * 0.02, yy, f"{v:.0f}", va="center", fontsize=8.5, color=INK)
        ax.set_xlim(0, max(vals) * 1.2)
        ax.set_yticks(y); ax.set_yticklabels(names)
        ax.tick_params(axis="y", length=0, labelcolor=INK2)
        ax.grid(axis="y", visible=False)
        ax.set_title(label[0].upper() + label[1:], loc="left", fontsize=9, color=INK2)
        ax.set_xlabel("Median wait (min)")
    fig.suptitle("Machine downtime: median wait under each policy", x=0.02, ha="left",
                 fontsize=10.5, fontweight="bold")
    fig.tight_layout()
    save(fig, "fig4_fault_recovery.png")


def fig_forecast(days, committed, rec_load, n_load, flat, cap, M):
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.9), sharey=True)
    x = np.arange(len(days))
    for ax, m in zip(axes, M):
        if m == TBI_PLAN["machine"]:
            ax.axvspan(TBI_DAYS[0] - 0.5, TBI_DAYS[-1] + 0.5, color="#fdf1ea", lw=0)
            ax.text(np.mean(TBI_DAYS), 158, "TBI", ha="center", va="top", fontsize=7.5, color=INK2)
        ax.fill_between(x, 0, 100 * committed[m] / flat[m], color="#efeee9", lw=0,
                        label="Already committed (patients on treatment)")
        ax.step(x, 100 * cap[m] / flat[m], where="mid", color=INK2, lw=1, label="Capacity")
        ax.plot(x[2:], 100 * n_load[m][2:] / flat[m], color=BASE,
                label="Equal head-count, start when ready (manual taper before TBI)")
        ax.plot(x[2:], 100 * rec_load[m][2:] / flat[m], color=RS_ML, label="RAD-SMART recommendation")
        ax.set_xticks(x[::2]); ax.set_xticklabels([f"D{k + 1}" for k in x[::2]])
        ax.set_title(DEPARTMENT["machines"][m]["label"], loc="left", fontsize=9, color=INK2)
        ax.set_xlabel("Working day")
    axes[0].set_ylabel("Planned load (% of a normal day)")
    axes[0].set_ylim(0, 160)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.5, -0.14), ncol=2, fontsize=7.5)
    fig.suptitle("Three-week machine-load forecast with new-start recommendations",
                 x=0.02, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout()
    save(fig, "fig5_capacity_forecast.png")


def print_summary(res):
    lines = [json.dumps({k: res[k] for k in ("day", "solver", "plan", "plan_check", "duration_model")}, indent=1)]
    keys = ["wait_median", "wait_p90", "excess_wait_median", "delay_median", "within_15_pct", "within_30_pct",
            "time_in_dept_mean", "overtime_min", "last_end", "new_starts_after_5pm", "complex_deferred",
            "mhrc_missed_bus", "transport_after_9pm", "others_after_9pm", "paying_within_15_pct",
            "accessory_delays", "blood_slot_delay_min", "urgent_same_day_pct", "imaging_holds",
            "held_treated_same_day", "called_in_early", "deferred"]
    lines.append("\nbuffer trade-off")
    for row in res["buffer_tradeoff"]:
        lines.append("  " + json.dumps(row))
    blocks = [("day_results", res["day_results"])] + [(f"disruption_results[{k}]", v)
                                                       for k, v in res["disruption_results"].items()]
    for block, S in blocks:
        lines.append(f"\n{block}")
        lines.append("%-24s" % "metric" + "".join("%40s" % k for k in S))
        for k in keys:
            lines.append("%-24s" % k + "".join("%40.1f" % S[n].get(k, float("nan")) for n in S))
    lines.append("\ndisruption " + json.dumps(res["disruption"], indent=1))
    f = res["forecast"]
    lines.append(f"\nforecast peaks  RAD-SMART {f['rad_smart_peak_pct']}  head-count {f['headcount_peak_pct']}"
                 f"  TBI days {f['rad_smart_tbi_peak_pct']} vs {f['headcount_tbi_peak_pct']}"
                 f"  days over capacity (head-count) {f['headcount_days_over_capacity']}"
                 f"  mean days to start {f['rad_smart_mean_days_to_start']} vs {f['headcount_mean_days_to_start']}")
    lines.append(f"runtime {res['runtime_seconds']} s")
    text = "\n".join(lines)
    print(text)
    return text


if __name__ == "__main__":
    main()
