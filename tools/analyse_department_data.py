"""Summarise the department's anonymised arrival and treatment records.

    python tools/analyse_department_data.py "Anonymised data_RADSMART.xlsx"

Input: the department's spreadsheet (one row per anonymised RT number, four
columns per day: Appointment, Arrival, Treatment, Delay). It is never committed;
*.xlsx is in .gitignore.

Output: poc/data/department_profile.json, aggregates only (counts, medians,
percentages, hourly profiles and quantiles). No row-level data leaves the
spreadsheet. The digital twin and run_poc.py read this file, so the results can
be reproduced without the spreadsheet.

Cleaning rules:
  * 12:00 AM means "not recorded" (the system enters it for missing times).
  * wait = treatment - arrival. A negative wait is fixed only when it is an
    obvious AM/PM slip (+12 h) or a treatment after midnight (+24 h) giving
    0-300 minutes; any other negative wait is an entry error and is dropped.
  * appointment offsets further than 4 hours are entry errors and are dropped.
  * "New Case" / "IP" in the appointment column mark new starts and inpatients
    (no appointment time recorded).
"""

from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "poc/data/department_profile.json"
Q = list(range(0, 101, 5))                 # quantile grid for the twin's samplers
RELIABLE_HOURS = (8, 10)                   # appointments 08:00-09:59: the schedule runs close to time


def minutes(v):
    if isinstance(v, dt.time):
        m = v.hour * 60 + v.minute + v.second / 60
        return np.nan if m == 0 else m
    return np.nan


def load(path) -> pd.DataFrame:
    raw = pd.read_excel(path, header=None)
    rows = []
    for c in range(3, raw.shape[1], 4):
        date = raw.iloc[0, c]
        if not isinstance(date, dt.datetime):
            continue
        assert raw.iloc[2, c:c + 4].tolist() == ["Appointment", "Arrival", "Treatment", "Delay"], c
        for r in range(3, raw.shape[0]):
            ap, ar, tr = raw.iloc[r, c:c + 3].tolist()
            if not any(isinstance(v, (dt.time, dt.datetime, str)) for v in (ap, ar, tr)):
                continue
            rows.append({"date": date.date(), "rt": raw.iloc[r, 1],
                         "appt": minutes(ap), "arr": minutes(ar), "trt": minutes(tr),
                         "label": ap if isinstance(ap, str) else None,
                         "not_treated": isinstance(tr, str) and "reat" in tr})
    return pd.DataFrame(rows)


def clean_wait(arr, trt):
    if np.isnan(arr) or np.isnan(trt):
        return np.nan, "missing"
    d = trt - arr
    if d >= 0:
        return d, "ok"
    for add, why in ((1440, "midnight"), (720, "am_pm")):
        if 0 <= d + add <= 300:
            return d + add, why
    return np.nan, "error"


def pct(s, cond):
    return round(float(np.mean(cond(s)) * 100), 1)


def stats(w):
    w = np.asarray(w, dtype=float)
    return {"n": int(len(w)), "median": round(float(np.median(w)), 1), "mean": round(float(np.mean(w)), 1),
            "p75": round(float(np.percentile(w, 75)), 1), "p90": round(float(np.percentile(w, 90)), 1),
            "p95": round(float(np.percentile(w, 95)), 1),
            "within_15_pct": pct(w, lambda x: x <= 15), "over_60_pct": pct(w, lambda x: x > 60),
            "over_120_pct": pct(w, lambda x: x > 120)}


def punctuality(late):
    late = np.asarray(late, dtype=float)
    return {"n": int(len(late)), "median_min": round(float(np.median(late)), 1),
            "within_15_pct": pct(late, lambda x: np.abs(x) <= 15),
            "early_over_15_pct": pct(late, lambda x: x < -15),
            "late_over_15_pct": pct(late, lambda x: x > 15),
            "late_over_60_pct": pct(late, lambda x: x > 60)}


def main(path):
    df = load(path)
    res = [clean_wait(a, t) for a, t in zip(df.arr, df.trt)]
    df["wait"] = [r[0] for r in res]
    df["wait_fix"] = [r[1] for r in res]
    vol = df.groupby("date").size()
    df["volume"] = df.date.map(vol)
    df["weekday"] = pd.to_datetime(df.date).dt.dayofweek < 5

    w = df.dropna(subset=["wait"])
    a = df.dropna(subset=["appt", "arr"]).copy()
    a["offset"] = a.arr - a.appt
    a = a[a.offset.abs() < 240]
    t = df.dropna(subset=["appt", "trt"]).copy()
    t["late"] = t.trt - t.appt
    t = t[t.late.abs() < 240]
    b = df.dropna(subset=["appt", "arr", "trt", "wait"]).copy()
    b = b[((b.trt - b.appt).abs() < 240) & ((b.arr - b.appt).abs() < 240)]
    b["dept_delay"] = (b.trt - np.maximum(b.appt, b.arr)).clip(lower=0)

    weekdays = df[df.weekday]
    busy = df.volume >= 70
    buckets = [(0, 44), (45, 59), (60, 69), (70, 999)]
    by_volume = []
    for lo, hi in buckets:
        m = (df.volume >= lo) & (df.volume <= hi)
        ww, tt = w[m.loc[w.index]], t[m.loc[t.index]]
        by_volume.append({"patients_per_day": f"{lo}-{hi}" if hi < 999 else f"{lo}+",
                          "days": int(df[m].date.nunique()), "wait": stats(ww.wait),
                          "punctuality": punctuality(tt.late)})

    hours = range(8, 23)
    arr_hr, appt_hr = w.arr // 60, t.appt // 60
    by_arrival_hour = [{"hour": h, "n": int((arr_hr == h).sum()),
                        "wait_median": round(float(w.wait[arr_hr == h].median()), 1),
                        "wait_p90": round(float(w.wait[arr_hr == h].quantile(.9)), 1)}
                       for h in hours if (arr_hr == h).sum() >= 20]
    by_appt_hour = []
    for h in hours:
        tt, aa, bb = t[appt_hr == h], a[a.appt // 60 == h], b[b.appt // 60 == h]
        if len(tt) < 20:
            continue
        by_appt_hour.append({"hour": h, "n": int(len(tt)),
                             "within_15_pct": pct(tt.late, lambda x: np.abs(x) <= 15),
                             "late_over_60_pct": pct(tt.late, lambda x: x > 60),
                             "arrival_offset_median": round(float(aa.offset.median()), 1),
                             "dept_delay_median": round(float(bb.dept_delay.median()), 1),
                             "dept_delay_over_30_pct": pct(bb.dept_delay, lambda x: x > 30)})

    # the twin's samplers
    ap = df[["appt", "volume"]].dropna()
    ap = ap[(ap.appt >= 8 * 60) & (ap.appt < 23 * 60)]
    slot_counts = (ap.appt // 5 * 5).value_counts().sort_index()
    slots_by_volume = {}
    for lo, hi in buckets[1:]:                  # busier days book more patients into the evening
        m = (ap.volume >= lo) & (ap.volume <= hi)
        c = (ap.appt[m] // 5 * 5).value_counts().sort_index()
        slots_by_volume[str(lo)] = {str(int(k)): int(v) for k, v in c.items()}
    offset_q = {}
    for h in hours:
        s = a.offset[a.appt // 60 == h]
        if len(s) >= 40:
            offset_q[str(h)] = np.percentile(s, Q).round(1).tolist()
    rel = a.offset[(a.appt >= RELIABLE_HOURS[0] * 60) & (a.appt < RELIABLE_HOURS[1] * 60)]

    starts = []
    for _, g in df[df.volume >= 40].groupby("date"):
        s = np.sort(g.trt.dropna().values)
        s = s[s > 300]
        starts += list(np.diff(s))
    starts = np.array(starts)
    wd = weekdays.groupby("date")
    month = pd.to_datetime(weekdays.date).dt.strftime("%Y-%m")

    profile = {
        "source": "Department of Radiotherapy, Manipal: anonymised arrival and treatment records "
                  "(Versa HD), shared by Dr Akshay Dinesan. Aggregates only.",
        "period": [str(df.date.min()), str(df.date.max())],
        "days": int(df.date.nunique()), "weekdays": int(weekdays.date.nunique()),
        "patient_days": int(len(df)), "patients": int(df.rt.nunique()),
        "cleaning": {"waits_usable": int(len(w)), "missing_12am_or_blank": int((df.wait_fix == "missing").sum()),
                     "fixed_am_pm": int((df.wait_fix == "am_pm").sum()),
                     "fixed_after_midnight": int((df.wait_fix == "midnight").sum()),
                     "dropped_entry_errors": int((df.wait_fix == "error").sum()),
                     "not_treated": int(df.not_treated.sum())},
        "volume": {"weekday_mean": round(float(wd.size().mean()), 1), "weekday_max": int(wd.size().max()),
                   "by_month_weekday_mean": {k: round(float(v), 1) for k, v in
                                              weekdays.groupby(month).apply(lambda g: g.groupby("date").size().mean()).items()},
                   "new_starts_per_weekday": round(float(wd.apply(lambda g: (g.label == "New Case").sum()).mean()), 1),
                   "inpatients_per_weekday": round(float(wd.apply(lambda g: (g.label == "IP").sum()).mean()), 1),
                   "last_treatment_median": round(float(weekdays[weekdays.trt > 300].groupby("date").trt.max().median()), 0)},
        "wait": stats(w.wait),
        "wait_busy_days": stats(w.wait[busy.loc[w.index]]),
        "wait_percentiles": np.percentile(w.wait, range(101)).round(1).tolist(),
        "wait_percentiles_busy_days": np.percentile(w.wait[busy.loc[w.index]], range(101)).round(1).tolist(),
        "punctuality": punctuality(t.late),
        "punctuality_busy_days": punctuality(t.late[busy.loc[t.index]]),
        "arrival_offset": {"median": round(float(a.offset.median()), 1),
                           "early_over_15_pct": pct(a.offset, lambda x: x < -15),
                           "within_15_pct": pct(a.offset, lambda x: np.abs(x) <= 15),
                           "late_over_15_pct": pct(a.offset, lambda x: x > 15)},
        "dept_delay": {"what": "treatment minus the later of appointment and arrival",
                       "median": round(float(b.dept_delay.median()), 1),
                       "p90": round(float(b.dept_delay.quantile(.9)), 1),
                       "over_30_pct": pct(b.dept_delay, lambda x: x > 30),
                       "over_60_pct": pct(b.dept_delay, lambda x: x > 60)},
        "by_volume": by_volume,
        "by_arrival_hour": by_arrival_hour,
        "by_appointment_hour": by_appt_hour,
        "machine": {"gap_between_starts_median": round(float(np.median(starts)), 1),
                    "gap_between_starts_p25": round(float(np.percentile(starts, 25)), 1)},
        "twin": {
            "appointment_slots": {str(int(k)): int(v) for k, v in slot_counts.items()},
            "appointment_slots_by_volume": slots_by_volume,
            "arrival_offset_quantiles_by_hour": offset_q,
            "reliable_arrival_offset_quantiles": np.percentile(rel, Q).round(1).tolist(),
            "reliable_hours": list(RELIABLE_HOURS),
            "quantile_grid": Q,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(profile, indent=1), encoding="utf-8")
    print(f"wrote {OUT}")
    print(json.dumps({k: profile[k] for k in ("period", "days", "patient_days", "patients", "cleaning", "volume",
                                              "wait", "wait_busy_days", "punctuality", "punctuality_busy_days",
                                              "arrival_offset", "dept_delay", "machine")}, indent=1))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ROOT / "Anonymised data_RADSMART.xlsx")
