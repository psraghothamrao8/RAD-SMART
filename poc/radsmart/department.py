"""The department's measured behaviour, used to calibrate the digital twin.

Reads poc/data/department_profile.json, which tools/analyse_department_data.py
builds from the department's anonymised arrival and treatment records
(Oct-Dec 2024). The file holds aggregates only: how appointment times are
spread over the day, and how early or late patients arrive for an appointment
at each hour.

  * Current practice books individual appointment times on a 5-minute grid,
    spread over the day as the department's records show (many share a time).
  * Patients arrive earlier the later their appointment: a median of about
    10 minutes before a morning appointment and 30-40 minutes before an
    evening one, because the evening runs late.
  * With RAD-SMART the times are kept, so patients are assumed to arrive the way
    today's morning patients do, when the schedule still runs close to time
    (appointments 08:00-09:59), counted from the reporting time they are given.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .config import hm

PROFILE_PATH = Path(__file__).resolve().parent.parent / "data/department_profile.json"
PROFILE = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
_T = PROFILE["twin"]
_GRID = np.array(_T["quantile_grid"], dtype=float) / 100
_SLOTS_BY_VOLUME = {int(lo): c for lo, c in _T["appointment_slots_by_volume"].items()}
_BY_HOUR = {int(h): np.array(q, dtype=float) for h, q in _T["arrival_offset_quantiles_by_hour"].items()}
_RELIABLE = np.array(_T["reliable_arrival_offset_quantiles"], dtype=float)


def _inverse_cdf(q, u):
    return float(np.interp(u, _GRID, q))


def arrival_offset(u: float, mode: str, told: float) -> float:
    """Arrival minus the time the patient was told, for a uniform draw u.

    mode "today": today's habits for an appointment at that hour.
    mode "reliable": today's morning habits, when the schedule runs on time.
    The same u is used for every policy (common random numbers), so a patient
    who tends to come early does so under both.
    """
    if mode == "reliable":
        return _inverse_cdf(_RELIABLE, u)
    h = int(told // 60)
    h = min(max(h, min(_BY_HOUR)), max(_BY_HOUR))
    return _inverse_cdf(_BY_HOUR[h], u)


def window(p) -> tuple[int, int]:
    """Hours a technologist would book this patient into today."""
    if p.complex or p.new_start:
        return hm("10:00"), hm("16:00")
    if p.transport:
        return hm("08:00"), hm("19:00")
    if p.flexible:
        return hm("17:00"), hm("23:00")
    return hm("08:00"), hm("21:00")


def book_today(patients, rng) -> dict:
    """Current-practice appointment times (pid -> minute) for one day.

    The day's times follow the department's recorded spread of appointment
    times on days with a similar number of patients (busier days book more of
    them into the evening), using systematic sampling so the day's mix matches
    the records. Then each
    patient takes a time inside their own window: fixed and narrow windows
    first. MHRC patients come on the bus for 16:00; paying patients keep the
    time they asked for.
    """
    n = len(patients)
    counts = _SLOTS_BY_VOLUME[max(lo for lo in _SLOTS_BY_VOLUME if lo <= max(n, min(_SLOTS_BY_VOLUME)))]
    slots = np.array(sorted(int(k) for k in counts), dtype=float)
    cdf = np.cumsum([counts[str(int(k))] for k in slots]) / sum(counts.values())
    marks = (rng.random() + np.arange(n)) / n
    pool = list(slots[np.searchsorted(cdf, marks)])
    out = {}
    order = sorted(patients, key=lambda p: (not p.mhrc, p.requested is None,
                                             window(p)[1] - window(p)[0], rng.random()))
    for p in order:
        if p.mhrc:
            t = hm("16:00")
        elif p.requested is not None:
            t = round(p.requested / 5) * 5
        else:
            lo, hi = window(p)
            inside = [i for i, s in enumerate(pool) if lo <= s < hi]
            if inside:
                t = pool[inside[int(rng.integers(len(inside)))]]
            else:
                t = min(pool, key=lambda s: max(lo - s, s - hi + 5)) if pool else lo
        if t in pool:
            pool.remove(t)
        elif pool:
            pool.remove(min(pool, key=lambda s: abs(s - t)))
        out[p.pid] = float(t)
    return out
