"""Synthetic (fully fake) radiotherapy department data.

The hackathon rules allow only fake or fully anonymised data, so every patient
here is generated. Distributions follow the RAD-SMART problem statement
(routine 7-15 min, new start / complex 20-60 min, 70-90 patients/day) and
published data (mean set-up + treatment 15.1 +/- 10.9 min over 34,438 sessions,
Munshi et al., JCRT 2021; first fractions longer, Xie et al., JACMP 2023).

The "true" duration model below is hidden from the scheduler. The scheduler only
sees predictions: either a lookup table of averages (day-1 mode) or the machine
learning model trained on historical sessions (duration_model.py).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

from .config import DEPARTMENT, TECHNIQUES, SITE_EFFECT, MOBILITY_EXTRA, IMAGING_EXTRA, hm

SITES_BY_TECH = {
    "PALL": {"BONE": 0.6, "BRAIN": 0.25, "THORAX": 0.15},
    "3DCRT": {"PELVIS": 0.4, "THORAX": 0.2, "ABDOMEN": 0.2, "HN": 0.2},
    "IMRT": {"HN": 0.7, "PELVIS": 0.2, "BRAIN": 0.1},
    "VMAT": {"HN": 0.35, "PELVIS": 0.35, "THORAX": 0.15, "BRAIN": 0.15},
    "BREAST": {"BREAST": 1.0},
    "BREAST_DIBH": {"BREAST": 1.0},
    "SBRT": {"THORAX": 0.5, "ABDOMEN": 0.3, "BONE": 0.2},
    "SRT": {"BRAIN": 1.0},
    "CSI": {"BRAIN": 1.0},
    "TBI": {"WHOLE_BODY": 1.0},
}

IMAGING_BY_TECH = {
    "PALL": {"none": 0.8, "kv": 0.2},
    "3DCRT": {"none": 0.6, "kv": 0.35, "cbct": 0.05},
    "IMRT": {"none": 0.1, "kv": 0.5, "cbct": 0.4},
    "VMAT": {"none": 0.1, "kv": 0.5, "cbct": 0.4},
    "BREAST": {"none": 0.5, "kv": 0.45, "cbct": 0.05},
    "BREAST_DIBH": {"none": 0.3, "kv": 0.6, "cbct": 0.1},
    "SBRT": {"cbct": 1.0},
    "SRT": {"cbct": 1.0},
    "CSI": {"kv": 0.5, "cbct": 0.5},
    "TBI": {"none": 1.0},
}

# Routine daily mix (share of ongoing routine patients on one machine).
ROUTINE_MIX = {"PALL": 0.13, "3DCRT": 0.19, "IMRT": 0.23, "VMAT": 0.24,
               "BREAST": 0.16, "BREAST_DIBH": 0.05}

LANGUAGES = {"Kannada": 0.38, "Malayalam": 0.20, "Hindi": 0.14, "Konkani": 0.08,
             "Tulu": 0.08, "English": 0.08, "Tamil": 0.02, "Telugu": 0.02}

# Current practice: hourly reporting blocks, filled by head-count and skewed to
# the morning ("too many patients asked to report during the same period").
BASELINE_BLOCKS = ["07:30", "08:30", "09:30", "10:30", "11:30", "12:30",
                   "14:00", "15:00", "16:00", "17:00", "18:00", "19:00"]
BASELINE_BLOCK_WEIGHTS = [13, 12, 12, 11, 9, 6, 8, 8, 7, 6, 4, 4]


@dataclass
class Patient:
    pid: str
    technique: str
    site: str
    machine: str
    fraction_no: int
    total_fx: int
    new_start: bool
    complex: bool
    accessories: list
    mobility: str
    imaging: str
    age: int
    inpatient: bool = False
    mhrc: bool = False            # hospice / respite centre resident
    dormitory: bool = False       # hospital dormitory resident (flexible)
    transport: bool = False       # depends on public transport
    latest_end: int | None = None  # must finish by (last bus), minutes
    paying: bool = False
    requested: int | None = None  # explicit time request, minutes
    usual_time: int = 0           # current-practice reporting time
    language: str = "Kannada"
    urgent: bool = False          # same-day palliative start
    ready_time: int | None = None  # urgent: earliest possible start
    eligible: list = field(default_factory=list)

    @property
    def elderly(self) -> bool:
        return self.age >= 70

    @property
    def remaining_after_today(self) -> int:
        return self.total_fx - self.fraction_no

    def to_dict(self) -> dict:
        d = asdict(self)
        d["elderly"] = self.elderly
        return d


def _pick(rng, weights: dict):
    keys = list(weights)
    p = np.array([weights[k] for k in keys], dtype=float)
    return keys[rng.choice(len(keys), p=p / p.sum())]


def true_median(p: Patient) -> float:
    """Hidden ground-truth median session length in minutes."""
    t = TECHNIQUES[p.technique]
    minutes = t["median"] * SITE_EFFECT[p.site]
    if p.fraction_no == 1:
        minutes += t["first_extra"]
    minutes += MOBILITY_EXTRA[p.mobility] + IMAGING_EXTRA[p.imaging]
    if p.elderly:
        minutes += 1.0
    if p.inpatient:
        minutes += 1.5
    if p.machine == "HALCYON" and p.technique in ("IMRT", "VMAT", "3DCRT", "CSI"):
        minutes *= 0.85   # ring-gantry delivery is faster
    return minutes


def sigma_of(p: Patient) -> float:
    return TECHNIQUES[p.technique]["sigma"]


def sample_duration(p: Patient, rng) -> float:
    return true_median(p) * math.exp(sigma_of(p) * rng.standard_normal())


def expected_duration(p: Patient) -> float:
    return true_median(p) * math.exp(sigma_of(p) ** 2 / 2)


def make_patient(rng, pid: str, technique: str, machine: str, new_start: bool,
                 total_fx: int | None = None) -> Patient:
    t = TECHNIQUES[technique]
    lo, hi = t["course"]
    total = total_fx or int(rng.integers(lo, hi + 1))
    fraction_no = 1 if new_start else int(rng.integers(min(2, total), total + 1))
    age = int(np.clip(rng.normal(56, 13), 18, 90))
    if technique == "CSI":
        age = int(rng.integers(8, 30))
    inpatient = rng.random() < (0.20 if technique == "PALL" else 0.06)
    if inpatient:
        mobility = _pick(rng, {"walking": 0.4, "wheelchair": 0.3, "stretcher": 0.3})
    else:
        mobility = _pick(rng, {"walking": 0.9, "wheelchair": 0.08, "stretcher": 0.02})
    p = Patient(
        pid=pid, technique=technique, site=_pick(rng, SITES_BY_TECH[technique]),
        machine=machine, fraction_no=fraction_no, total_fx=total, new_start=new_start,
        complex=t["complex"], accessories=list(t["accessories"]), mobility=mobility,
        imaging=_pick(rng, IMAGING_BY_TECH[technique]), age=age, inpatient=inpatient,
        language=_pick(rng, LANGUAGES), eligible=list(t["machines"]),
    )
    if not inpatient:
        p.mhrc = rng.random() < (0.12 if technique == "PALL" or p.elderly else 0.02)
        p.dormitory = (not p.mhrc) and rng.random() < 0.12
        p.transport = (not p.mhrc) and (not p.dormitory) and rng.random() < 0.28
        if p.transport:
            p.latest_end = hm("16:00") + 15 * int(rng.integers(0, 11))  # 16:00-18:30
        p.paying = rng.random() < 0.35
        if p.paying and rng.random() < 0.4 and not t["complex"]:   # complex: booked by physics
            p.requested = hm(str(rng.choice(["08:00", "09:00", "17:30", "18:30", "19:30"])))
    p.usual_time = _baseline_block(rng, p)
    return p


def _baseline_block(rng, p: Patient) -> int:
    """Reporting time a technologist would give today (current practice)."""
    blocks = [hm(b) for b in BASELINE_BLOCKS]
    w = np.array(BASELINE_BLOCK_WEIGHTS, dtype=float)
    ok = np.ones(len(blocks), dtype=bool)
    if p.requested is not None:
        return min(blocks, key=lambda b: abs(b - p.requested))
    if p.complex or p.new_start:
        ok = np.array([b in (hm("10:30"), hm("11:30"), hm("14:00")) for b in blocks])
    elif p.mhrc:
        ok = np.array([b in (hm("09:30"), hm("10:30")) for b in blocks])
    elif p.inpatient:
        ok = np.array([hm("10:30") <= b <= hm("15:00") for b in blocks])
    elif p.transport:
        ok = np.array([b <= min(p.latest_end - 60, hm("15:00")) for b in blocks])
    elif p.dormitory:
        w = w * np.linspace(0.6, 1.8, len(blocks))   # dormitory: later is fine
    w = w * ok
    return blocks[rng.choice(len(blocks), p=w / w.sum())]


def make_day(seed: int = 7, machines=("VERSA",), target_load: float = 0.90,
             complex_mix=("SRT", "CSI"), new_start_mix=("VMAT", "IMRT", "3DCRT", "BREAST", "SBRT"),
             routine_mix: dict | None = None) -> list[Patient]:
    """Build one treatment day for the given machines.

    Routine patients are added until the expected machine load reaches
    `target_load` x available minutes on each machine.
    """
    rng = np.random.default_rng(seed)
    routine_mix = routine_mix or ROUTINE_MIX
    patients: list[Patient] = []
    n = 0

    def nid():
        nonlocal n
        n += 1
        return f"P{n:03d}"

    # complex procedures (on first eligible machine present)
    for tech in complex_mix:
        m = next(mm for mm in TECHNIQUES[tech]["machines"] if mm in machines)
        patients.append(make_patient(rng, nid(), tech, m, new_start=False))
    for tech in new_start_mix:
        m = next(mm for mm in TECHNIQUES[tech]["machines"] if mm in machines)
        patients.append(make_patient(rng, nid(), tech, m, new_start=True))

    for m in machines:
        avail = available_minutes(m)
        load = sum(expected_duration(p) for p in patients if p.machine == m)
        while load < target_load * avail:
            tech = _pick(rng, routine_mix)
            if m not in TECHNIQUES[tech]["machines"]:
                continue
            p = make_patient(rng, nid(), tech, m, new_start=False)
            patients.append(p)
            load += expected_duration(p)
    return patients


def available_minutes(machine: str) -> float:
    d = DEPARTMENT
    blocked = sum(b["end"] - b["start"] for b in d["machines"][machine]["blocks"])
    return d["regular_end"] - d["day_start"] - blocked


def make_urgent(rng, start_id: int, machine: str = "VERSA", lam: float = 1.2) -> list[Patient]:
    """Same-day palliative starts that appear during the day (unknown at 07:30)."""
    k = rng.poisson(lam)
    out = []
    for i in range(k):
        p = make_patient(rng, f"U{start_id + i:02d}", "PALL", machine, new_start=True)
        p.urgent = True
        p.transport = False
        p.latest_end = None
        p.requested = None
        p.ready_time = int(rng.uniform(hm("12:30"), hm("15:30")))
        p.usual_time = p.ready_time
        out.append(p)
    return out


def make_history(seed: int = 11, n_sessions: int = 12000, machines=("VERSA", "HALCYON")):
    """Historical session log (features + actual minutes) for model training."""
    rng = np.random.default_rng(seed)
    rows = []
    mix = dict(ROUTINE_MIX)
    mix.update({"SBRT": 0.015, "SRT": 0.012, "CSI": 0.02, "TBI": 0.004})
    for i in range(n_sessions):
        tech = _pick(rng, mix)
        m = str(rng.choice([mm for mm in TECHNIQUES[tech]["machines"] if mm in machines]))
        p = make_patient(rng, f"H{i}", tech, m, new_start=rng.random() < 0.05)
        row = p.to_dict()
        row["duration"] = sample_duration(p, rng)
        row["hour"] = int(rng.integers(8, 20))
        rows.append(row)
    return rows
