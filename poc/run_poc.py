"""Run every RAD-SMART proof-of-concept experiment and write results + figures.

    python run_poc.py            # ~2-3 minutes on a laptop

Outputs (poc/results/):
    results.json              all numbers quoted in the report
    schedule_rad_smart.csv    the optimised day plan with reason codes
    fig*.png                  figures used in the report and deck

Everything runs on synthetic (fake) data. Results show how the method behaves
under stated assumptions; they are not clinical evidence. Real numbers come
from the pilot's baseline and shadow-mode phases.
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import numpy as np

from radsmart.config import DEPARTMENT, TECHNIQUES, fmt, hm
from radsmart.duration_model import LookupPredictor, QuantileGBMPredictor, evaluate
from radsmart.forecast import (committed_load, daily_capacity, make_pipeline, naive,
                               occupancy_label, recommend)
from radsmart.scheduler import DayScheduler, planning_minutes
from radsmart.simulate import monte_carlo, summarise
from radsmart.synth import available_minutes, expected_duration, make_day, make_history

OUT = Path(__file__).parent / "results"
OUT.mkdir(exist_ok=True)
N_REP = 300

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


def hour_axis(ax, lo, hi):
    ticks = list(range(int(np.ceil(lo / 60)) * 60, int(hi) + 1, 120))
    ax.set_xticks(ticks)
    ax.set_xticklabels([fmt(t) for t in ticks])
    ax.set_xlim(lo, hi)


def save(fig, name):
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight")
    plt.close(fig)


# ------------------------------------------------------------------ experiments
def main():
    tic = time.perf_counter()
    res = {"assumptions": {
        "data": "synthetic (fake) patients; no real patient data used",
        "operating_day": f"{fmt(DEPARTMENT['day_start'])}-{fmt(DEPARTMENT['regular_end'])} "
                         f"(overtime to {fmt(DEPARTMENT['hard_end'])})",
        "blood_irradiation": "13:30-14:00 on Versa HD",
        "senior_staff_window": "10:00-17:00", "protected_block": "12:00-13:30",
        "new_start_cut_off": "17:00", "deadline_buffer_min": DEPARTMENT["deadline_buffer_min"],
        "urgent_same_day_starts_per_day": "Poisson(1.2), ready 12:30-15:30",
        "no_show_rate": 0.02, "arrival_offset": "Normal(-10, 12) min, clipped to [-40, +25]",
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
    # chart data for the interactive results page (results/web_data.json)
    pct = np.arange(0, 101)
    web = {"duration_abs_error_percentiles": {k: np.percentile(np.abs(v["errors"]), pct).round(2).tolist()
                                              for k, v in ev.items()}}

    # 2. one treatment day, single machine (today's department) ---------------
    day = make_day(seed=7)
    load = sum(expected_duration(p) for p in day)
    res["day"] = {"patients": len(day), "new_starts": sum(p.new_start for p in day),
                  "complex": sum(p.complex for p in day),
                  "expected_machine_minutes": round(load),
                  "available_minutes": available_minutes("VERSA"),
                  "load_pct": round(100 * load / available_minutes("VERSA"), 1),
                  "priority_mix": {
                      "elderly": sum(p.elderly for p in day), "inpatient": sum(p.inpatient for p in day),
                      "hospice_mhrc": sum(p.mhrc for p in day), "dormitory": sum(p.dormitory for p in day),
                      "public_transport": sum(p.transport for p in day), "paying": sum(p.paying for p in day),
                      "requested_time": sum(p.requested is not None for p in day),
                      "abc": sum("ABC" in p.accessories for p in day),
                      "breast_board": sum("BREAST_BOARD" in p.accessories for p in day)}}
    sch = DayScheduler()
    s_avg = sch.solve(day, lookup)
    s_ml = sch.solve(day, ml)
    res["solver"] = {name: {"seconds": round(s.solve_seconds, 1), "status": s.status,
                            "proven_gap_pct": round(100 * (s.mip_gap or 0), 2),
                            "unscheduled": s.unscheduled(), "variables": s.n_variables,
                            "constraints": s.n_constraints}
                     for name, s in (("averages", s_avg), ("ml", s_ml))}
    est_avg, est_ml = planning_minutes(day, lookup), planning_minutes(day, ml)
    policies = {
        "Current practice": dict(appt={p.pid: (p.machine, p.usual_time) for p in day},
                                 rule="fcfs", estimate=est_avg),
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
    web["department"] = {k: DEPARTMENT.get(k) for k in (
        "day_start", "regular_end", "hard_end", "protected_block", "senior_staff_window",
        "new_start_latest_end", "urgent_holds", "ct_sim_bookings")}
    web["department"]["machine_blocks"] = DEPARTMENT["machines"]["VERSA"]["blocks"]

    # 3. machine fault at 11:00 -------------------------------------------------
    fault = ("VERSA", hm("11:00"), 30)
    new_appt, notified, s_re = reoptimise(sch, day, s_ml, ml, fault)
    res["disruption"] = {"fault": "Versa HD down 11:00-11:30",
                         "reoptimisation_seconds": round(s_re.solve_seconds, 1),
                         "patients_replanned": len(new_appt), "patients_messaged": len(notified)}
    dpol = {
        "Current practice": dict(policies["Current practice"], fault=fault),
        "RAD-SMART plan, no re-planning": dict(policies["RAD-SMART (ML)"], fault=fault),
        "RAD-SMART live re-planning + messages": dict(policies["RAD-SMART (ML)"], fault=fault,
                                                      new_appt=new_appt, notified=notified),
    }
    dres, dcurves, _ = monte_carlo(day, dpol, n_rep=N_REP, seed=99)
    res["disruption_results"] = rounded(summarise(dres))
    fig_disruption(res["disruption_results"])
    fig_waiting_room(dcurves, dict(zip(dpol, (BASE, RS_AVG, RS_LIVE))), "fig4b_fault_waiting_room.png",
                     "Machine fault 11:00-11:30: patients waiting in the department",
                     "Average over 300 simulated days", fault=fault)
    web["fault"] = {"start": fault[1], "minutes": fault[2],
                    "reoptimisation_seconds": res["disruption"]["reoptimisation_seconds"]}
    web["fault_waiting_room"] = curve_json(dcurves)
    for row in web["schedule"]:
        row["replanned"] = float(new_appt[row["pid"]]) if row["pid"] in new_appt else None
        row["notified"] = row["pid"] in notified

    # 4. two machines: occupancy forecast and new-start recommendations -------
    M, H = ("VERSA", "HALCYON"), 15
    day2 = make_day(seed=21, machines=M)
    committed, completing = committed_load(day2, ml, H, M)
    cands = make_pipeline(ml, H, rate=5.5, machines=M)
    plan, starts, rec_load, waiting = recommend(committed, cands, H, M)
    heads = {m: sum(p.machine == m for p in day2) for m in M}
    n_starts, n_load = naive(committed, cands, H, M, headcount=heads)
    cap = {m: daily_capacity(m) for m in M}
    days = working_days(H)
    res["forecast"] = {
        "machines": {m: DEPARTMENT["machines"][m]["label"] for m in M},
        "patients_on_treatment": heads, "pipeline_patients": len(cands),
        "daily_capacity_min": {m: round(cap[m]) for m in M},
        "table": [{"day": days[k], **{f"{m}_committed_pct": round(100 * committed[m][k] / cap[m])
                                      for m in M},
                   **{f"{m}_completing": int(completing[m][k]) for m in M},
                   **{f"{m}_recommended_starts": int(starts[m][k]) for m in M},
                   **{f"{m}_occupancy": occupancy_label(100 * rec_load[m][k] / cap[m]) for m in M}}
                  for k in range(H)],
        "rad_smart_peak_pct": {m: round(float(100 * rec_load[m][2:].max() / cap[m])) for m in M},
        "headcount_peak_pct": {m: round(float(100 * n_load[m][2:].max() / cap[m])) for m in M},
        "headcount_days_over_capacity": {m: int((n_load[m][2:] > cap[m]).sum()) for m in M},
        "rad_smart_days_over_capacity": {m: int((rec_load[m][2:] > cap[m] + 1e-6).sum()) for m in M},
        "still_waiting_at_horizon": len(waiting),
    }
    fig_forecast(days, committed, rec_load, n_load, cap, M)
    web["forecast"] = {"days": days, "labels": res["forecast"]["machines"],
                       "capacity": {m: round(float(cap[m]), 1) for m in M},
                       **{key: {m: np.asarray(src[m], dtype=float).round(1).tolist() for m in M}
                          for key, src in (("committed", committed), ("rad_smart", rec_load),
                                           ("headcount", n_load))},
                       "recommended_starts": {m: [int(x) for x in starts[m]] for m in M},
                       "completing": {m: [int(x) for x in completing[m]] for m in M}}

    res["runtime_seconds"] = round(time.perf_counter() - tic, 1)
    (OUT / "results.json").write_text(json.dumps(res, indent=2))
    web["results"] = res
    (OUT / "web_data.json").write_text(json.dumps(web))
    print_summary(res)


# ------------------------------------------------------------------ helpers
def appt_of(schedule, day):
    """Appointment times from a schedule; anyone unscheduled keeps their usual time
    (in the product they are flagged for the RTT lead instead)."""
    out = {}
    for p in day:
        a = schedule.assignments[p.pid]
        out[p.pid] = (a.machine or p.machine, a.start if a.start is not None else p.usual_time)
    return out


def reoptimise(sch, day, s_plan, predictor, fault):
    """Re-plan the rest of the day when the machine fails at fault[1]."""
    m, f0, flen = fault
    remaining = [p for p in day if (s_plan.assignments[p.pid].start or 0) >= f0]
    notice = f0 + 45                         # patients booked later can still be told
    earliest = {p.pid: (f0 + flen if s_plan.assignments[p.pid].start < notice else notice)
                for p in remaining}
    prev = {p.pid: s_plan.assignments[p.pid].start for p in remaining}
    s = sch.solve(remaining, predictor, earliest=earliest, prev_time=prev,
                  extra_blocks={m: [(DEPARTMENT["day_start"], f0 + flen, "Past / fault")]})
    new_appt = {pid: a.start for pid, a in s.assignments.items() if a.start is not None}
    notified = frozenset(pid for pid in new_appt
                         if prev[pid] >= notice and abs(new_appt[pid] - prev[pid]) >= 5)
    return new_appt, notified, s


def curve_json(curves):
    """Mean patients waiting over the day, per policy, on one shared time grid."""
    grid = next(iter(curves.values()))[0]
    return {"grid": [float(g) for g in grid],
            "series": {pol: np.asarray(c, dtype=float).round(2).tolist() for pol, (_, c) in curves.items()}}


def schedule_json(day, s):
    rows = []
    for p in day:
        a = s.assignments[p.pid]
        flags = [n for n, v in (("new start", p.new_start), ("complex", p.complex),
                                ("elderly", p.elderly), ("inpatient", p.inpatient),
                                ("hospice", p.mhrc), ("dormitory", p.dormitory),
                                ("public transport", p.transport), ("paying", p.paying)) if v]
        rows.append({"pid": p.pid, "start": float(a.start), "minutes": round(float(a.planned_minutes), 1),
                     "cat": "complex" if p.complex else ("new_start" if p.new_start else "routine"),
                     "technique": TECHNIQUES[p.technique]["label"],
                     "fraction": f"{p.fraction_no}/{p.total_fx}", "usual": float(p.usual_time),
                     "accessories": list(p.accessories), "flags": flags,
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
        w.writerow(["appointment", "patient", "technique", "fraction", "planned_min",
                    "flags", "current_reporting_time", "why"])
        for a, p in rows:
            flags = [n for n, v in (("new start", p.new_start), ("complex", p.complex),
                                    ("elderly", p.elderly), ("inpatient", p.inpatient),
                                    ("hospice", p.mhrc), ("dormitory", p.dormitory),
                                    ("public transport", p.transport), ("paying", p.paying)) if v]
            w.writerow([fmt(a.start), p.pid, TECHNIQUES[p.technique]["label"],
                        f"{p.fraction_no}/{p.total_fx}", round(a.planned_minutes, 1),
                        "; ".join(flags + p.accessories), fmt(p.usual_time), " | ".join(a.reasons)])


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
        med = summary[name]["wait_median"]
        ax.plot(e, y, color=color, label=f"{name}: median {med:.0f} min")
        ax.plot([med], [50], "o", ms=6, color=color, mec=SURFACE, mew=2)
    ax.set_xlim(0, 240); ax.set_ylim(0, 100)
    ax.set_xticks(range(0, 241, 30))
    ax.set_xlabel("Minutes from arrival to entering the treatment room")
    ax.set_ylabel("% of patients treated within")
    ax.legend(loc="lower right")
    title(ax, "How long patients wait",
          f"Synthetic 67-patient day on one machine, {N_REP} simulated days; dots mark each median")
    save(fig, "fig1_wait_distribution.png")


def fig_waiting_room(curves, colors, name, head, sub, fault=None):
    fig, ax = plt.subplots(figsize=(6.4, 3.0))
    for pol, color in colors.items():
        grid, c = curves[pol]
        ax.plot(grid, c, color=color, label=pol)
    if fault:
        ax.axvspan(fault[1], fault[1] + fault[2], color=GRID, lw=0)
        ax.text(fault[1] - 5, ax.get_ylim()[1] * 0.95, "machine\nfault", fontsize=8, color=INK2,
                ha="right", va="top")
    hour_axis(ax, DEPARTMENT["day_start"] - 30, DEPARTMENT["hard_end"])
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Patients waiting (mean)")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.14), ncol=3, fontsize=8)
    title(ax, head, sub)
    save(fig, name)


def fig_gantt(day, s):
    d = DEPARTMENT
    fig, ax = plt.subplots(figsize=(6.8, 2.6))
    lanes = {"Versa HD": 2, "ABC device (1 unit)": 1, "Breast boards (2 units)": 0}
    ax.axvspan(*d["protected_block"], color="#eef4fc", lw=0)
    ax.text(sum(d["protected_block"]) / 2, 2.62, "protected\ncomplex block", ha="center",
            va="bottom", fontsize=7, color=INK2)
    for b in d["machines"]["VERSA"]["blocks"]:
        ax.add_patch(Rectangle((b["start"], 2 - 0.3), b["end"] - b["start"], 0.6, color=MUTED, lw=0))
    for h in d["urgent_holds"]:
        ax.add_patch(Rectangle((h["start"], 2 - 0.3), h["minutes"], 0.6, fill=False,
                               ec=MUTED, lw=1, hatch="////"))
    lane_of = {"ABC": lanes["ABC device (1 unit)"], "BREAST_BOARD": lanes["Breast boards (2 units)"]}
    for b in d["ct_sim_bookings"]:
        lane = lane_of[b["accessory"]]
        ax.add_patch(Rectangle((b["start"], lane - 0.3), b["end"] - b["start"], 0.6, color=MUTED, lw=0))
    for p in day:
        a = s.assignments[p.pid]
        if a.start is None:          # flagged for the RTT lead, not drawn
            continue
        cat = "complex" if p.complex else "new_start" if p.new_start else "routine"
        ax.add_patch(Rectangle((a.start, 2 - 0.3), a.planned_minutes, 0.6, color=CAT[cat],
                               lw=0.6, ec=SURFACE))
        for acc in p.accessories:
            lane = lane_of[acc]
            ax.add_patch(Rectangle((a.start, lane - 0.3), a.planned_minutes, 0.6, color=CAT[cat],
                                   lw=0.6, ec=SURFACE))
    ax.set_yticks(list(lanes.values())); ax.set_yticklabels(list(lanes.keys()))
    ax.tick_params(axis="y", length=0, labelcolor=INK2)
    ax.set_ylim(-0.6, 3.1)
    ax.grid(axis="y", visible=False)
    hour_axis(ax, d["day_start"], d["hard_end"])
    handles = [Rectangle((0, 0), 1, 1, color=CAT["routine"]), Rectangle((0, 0), 1, 1, color=CAT["new_start"]),
               Rectangle((0, 0), 1, 1, color=CAT["complex"]), Rectangle((0, 0), 1, 1, color=MUTED),
               Rectangle((0, 0), 1, 1, fill=False, ec=MUTED, hatch="////")]
    ax.legend(handles, ["Routine", "New start", "Complex", "Blood irradiation / CT simulator",
                        "Same-day urgent hold"], loc="upper center", bbox_to_anchor=(0.5, -0.16),
              ncol=5, fontsize=7.5, handlelength=1.2, columnspacing=1.2)
    title(ax, "One optimised day", f"{len(day)} patients on Versa HD; accessories never double-booked "
                                   "with the CT simulator")
    save(fig, "fig3_optimised_day.png")


def fig_disruption(summary):
    names = list(summary)
    colors = [BASE, RS_AVG, RS_LIVE]
    fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.4), sharey=True)
    for ax, key, head in ((axes[0], "wait_median", "Median wait (min)"),
                          (axes[1], "wait_p90", "90th-percentile wait (min)")):
        vals = [summary[n][key] for n in names]
        y = np.arange(len(names))[::-1]
        ax.barh(y, vals, height=0.55, color=colors)
        for yy, v in zip(y, vals):
            ax.text(v + max(vals) * 0.02, yy, f"{v:.0f}", va="center", fontsize=8.5, color=INK)
        ax.set_xlim(0, max(vals) * 1.18)
        ax.set_yticks(y); ax.set_yticklabels(names)
        ax.tick_params(axis="y", length=0, labelcolor=INK2)
        ax.grid(axis="y", visible=False)
        ax.set_title(head, loc="left", fontsize=9, color=INK2)
    fig.suptitle("Versa HD fault 11:00-11:30", x=0.02, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout()
    save(fig, "fig4_fault_recovery.png")


def fig_forecast(days, committed, rec_load, n_load, cap, M):
    fig, axes = plt.subplots(1, 2, figsize=(6.8, 2.8), sharey=True)
    x = np.arange(len(days))
    for ax, m in zip(axes, M):
        ax.fill_between(x, 0, 100 * committed[m] / cap[m], color="#efeee9", lw=0,
                        label="Already committed (patients on treatment)")
        ax.plot(x[2:], 100 * n_load[m][2:] / cap[m], color=BASE, label="Equal head-count, start when ready")
        ax.plot(x[2:], 100 * rec_load[m][2:] / cap[m], color=RS_ML, label="RAD-SMART recommendation")
        ax.axhline(100, color=INK2, lw=1)
        ax.text(0, 103, "capacity", ha="left", va="bottom", fontsize=7.5, color=INK2)
        ax.set_xticks(x[::2]); ax.set_xticklabels([f"D{k + 1}" for k in x[::2]])
        ax.set_title(DEPARTMENT["machines"][m]["label"], loc="left", fontsize=9, color=INK2)
        ax.set_xlabel("Working day")
    axes[0].set_ylabel("Planned load (% of capacity)")
    axes[0].set_ylim(0, 170)
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", bbox_to_anchor=(0.5, -0.1), ncol=3, fontsize=7.5)
    fig.suptitle("Three-week machine-load forecast with new-start recommendations",
                 x=0.02, ha="left", fontsize=10.5, fontweight="bold")
    fig.tight_layout()
    save(fig, "fig5_capacity_forecast.png")


def print_summary(res):
    print(json.dumps({k: res[k] for k in ("day", "solver", "duration_model")}, indent=1))
    keys = ["wait_median", "wait_p90", "delay_median", "within_15_pct", "within_30_pct",
            "time_in_dept_mean", "overtime_min", "new_starts_after_5pm", "complex_deferred",
            "accessory_delays", "blood_slot_delay_min", "urgent_same_day_pct"]
    for block in ("day_results", "disruption_results"):
        S = res[block]
        print(f"\n{block}")
        print("%-24s" % "metric" + "".join("%38s" % k for k in S))
        for k in keys:
            print("%-24s" % k + "".join("%38.1f" % S[n][k] for n in S))
    print("\ndisruption", res["disruption"])
    f = res["forecast"]
    print("\nforecast peaks  RAD-SMART", f["rad_smart_peak_pct"], " head-count", f["headcount_peak_pct"],
          " days over capacity (head-count)", f["headcount_days_over_capacity"])
    print("runtime", res["runtime_seconds"], "s")


if __name__ == "__main__":
    main()
