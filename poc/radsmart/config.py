"""Department configuration for the RAD-SMART proof of concept.

Every scheduling rule lives here as data, not code, so the same engine can be
re-used by another department by editing this file (or, in the full product,
through the natural-language Rule Studio, which writes the same structure).

Operating rules follow the department's answers to our questions (Dr Akshay
Dinesan, 21 Sep 2026): operating hours, the complex-case window, shared
accessories, priority slots, urgent starts, reporting times and downtime rules.
Session durations and patient mixes are ILLUSTRATIVE: the department has no
workflow timestamps yet, so these are replaced by its own estimates at the start
of the pilot and then by measured times.
"""

from __future__ import annotations


def hm(text: str) -> int:
    """'13:30' -> minutes after midnight."""
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: float) -> str:
    """Minutes after midnight -> 'HH:MM' (the day runs past midnight: 25:00 -> 01:00)."""
    minutes = int(round(minutes))
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


# --------------------------------------------------------------------------
# Treatment techniques.
#   median     : median minutes of a routine fraction (room entry -> exit)
#   first_extra: extra minutes on the first fraction (setup verification etc.)
#   sigma      : log-normal spread of the actual duration
#   complex    : needs senior staff inside the protected window
#   accessories: shared devices needed during the session
#   course     : (min, max) number of fractions in a course
#   machines   : machines the plan can be delivered on (set by physics)
# Problem statement: routine 7-15 min; new start / complex 20-60 min.
# TBI: two fractions a day, 60-90 min each (department answers); it has its own
# first-of-morning and evening slots, so it is planned as fixed blocks (TBI_PLAN).
# --------------------------------------------------------------------------
TECHNIQUES = {
    "PALL": dict(label="Palliative 2D/3D", median=5.5, first_extra=12, sigma=0.28,
                 complex=False, accessories=[], course=(1, 10), machines=["VERSA", "HALCYON"]),
    "3DCRT": dict(label="3D-CRT", median=6.0, first_extra=13, sigma=0.27,
                  complex=False, accessories=[], course=(20, 30), machines=["VERSA", "HALCYON"]),
    "IMRT": dict(label="IMRT", median=7.5, first_extra=15, sigma=0.25,
                 complex=False, accessories=[], course=(30, 35), machines=["VERSA", "HALCYON"]),
    "VMAT": dict(label="VMAT", median=7.0, first_extra=15, sigma=0.25,
                 complex=False, accessories=[], course=(25, 33), machines=["VERSA", "HALCYON"]),
    "BREAST": dict(label="Breast (breast board)", median=7.0, first_extra=13, sigma=0.25,
                   complex=False, accessories=["BREAST_BOARD"], course=(15, 25),
                   machines=["VERSA", "HALCYON"]),
    "BREAST_DIBH": dict(label="Breast DIBH (ABC)", median=11.0, first_extra=15, sigma=0.25,
                        complex=False, accessories=["ABC", "BREAST_BOARD"], course=(15, 25),
                        machines=["VERSA"]),
    "SBRT": dict(label="SBRT", median=26.0, first_extra=12, sigma=0.22,
                 complex=True, accessories=[], course=(3, 5), machines=["VERSA"]),
    "SRT": dict(label="SRT", median=22.0, first_extra=12, sigma=0.22,
                complex=True, accessories=[], course=(1, 5), machines=["VERSA"]),
    "CSI": dict(label="Craniospinal (CSI)", median=25.0, first_extra=15, sigma=0.22,
                complex=True, accessories=[], course=(20, 30), machines=["VERSA", "HALCYON"]),
    "TBI": dict(label="Total body (TBI)", median=75.0, first_extra=10, sigma=0.12,
                complex=True, accessories=[], course=(1, 6), machines=["VERSA"]),
}

# Anatomical site groups change set-up time a little (immobilisation, imaging).
SITE_EFFECT = {"HN": 1.10, "BRAIN": 1.05, "THORAX": 1.00, "BREAST": 1.00,
               "PELVIS": 0.97, "ABDOMEN": 1.00, "BONE": 0.92, "WHOLE_BODY": 1.00}

MOBILITY_EXTRA = {"walking": 0.0, "wheelchair": 3.0, "stretcher": 8.0}
IMAGING_EXTRA = {"none": 0.0, "kv": 1.0, "cbct": 2.5}


DEPARTMENT = {
    "name": "Demo radiotherapy department (synthetic patients, department rules)",
    "grid_min": 2,                  # optimiser time resolution (minutes)
    # The machine starts at 08:30 and currently runs to about 01:00-02:00 with
    # three RTT shifts; minutes past midnight continue the same day (25:00 = 01:00).
    "day_start": hm("08:30"),
    "regular_end": hm("25:00"),     # 01:00; later is overtime
    "hard_end": hm("26:00"),        # 02:00; nothing may be planned after this
    "patient_ceiling": 90,          # current operational ceiling per day
    "machines": {
        "VERSA": {"label": "Versa HD",
                  "blocks": [{"start": hm("13:30"), "end": hm("14:00"),
                              "label": "Blood irradiation"}]},
        # Second machine expected early 2027; its capability matrix is still to
        # be agreed by the department, so eligibility below is a placeholder.
        "HALCYON": {"label": "Halcyon", "blocks": []},
    },
    # Complex cases (SBRT/SRT/CSI): hard window 10:00-17:00 with senior staff;
    # 12:00-13:30 is the preferred (soft) protected block, released to other
    # patients when no complex case needs it.
    "senior_staff_window": (hm("10:00"), hm("17:00")),
    "senior_staff_concurrent": 1,   # one senior team across all machines
    "protected_block": (hm("12:00"), hm("13:30")),
    "new_start_latest_end": hm("17:00"),
    # Plan to finish this many minutes before a hard deadline (17:00 new-start
    # cut-off, senior-staff window, 21:00 public transport) so ordinary delays
    # cannot break it.
    "deadline_buffer_min": 25,
    # Patients from the Manipal Hospice and Respite Centre (MHRC) arrive for
    # protected 16:00-17:00 slots and must finish in time for the 17:00 bus.
    "mhrc_window": (hm("16:00"), hm("16:55")),
    "mhrc_buffer_min": 10,
    "mhrc_bus_arrival": hm("15:45"),   # the hospice bus brings them together
    "public_transport_latest_end": hm("21:00"),
    # Same-day urgent (palliative) starts: 0-3 a day, arriving in the afternoon,
    # treated before 18:00. Capacity is held back for them and used as catch-up
    # buffer (also for imaging re-treatments) when nobody needs it.
    "urgent_latest_end": hm("18:00"),
    "urgent_holds": [{"machine": "VERSA", "start": hm("14:40"), "minutes": 20},
                     {"machine": "VERSA", "start": hm("17:00"), "minutes": 20}],
    # Reporting: every patient reports 20 min before the machine slot; pelvic
    # patients (cervix, endometrium, rectum, anal canal, bladder) drink 500 mL of
    # water, wait 30 min, and so report 45 min before.
    "report_lead_min": 20,
    "report_lead_pelvic_min": 45,
    "pelvic_fill_min": 30,
    "prep_min": 10,                 # check-in and changing before a patient is ready
    "call_in_min": 15,              # inpatients and dormitory residents can be called in
    "come_early_min": 25,           # nearby patients messaged to come early
    # One breast board and one ABC unit, shared with the CT simulator
    # (open 11:00-18:00); moving either between rooms takes under 2 minutes.
    "accessories": {"ABC": {"units": 1, "transfer_min": 2},
                    "BREAST_BOARD": {"units": 1, "transfer_min": 2}},
    "ct_sim_hours": (hm("11:00"), hm("18:00")),
    # Windows in which an accessory is reserved for the linac. A CT-simulator
    # booking may use a reserved window only if the linac plan does not need it.
    "accessory_reservations": [
        {"accessory": "ABC", "start": hm("08:30"), "end": hm("11:00"), "why": "before CT hours"},
        {"accessory": "BREAST_BOARD", "start": hm("08:30"), "end": hm("11:00"), "why": "before CT hours"},
        {"accessory": "ABC", "start": hm("12:00"), "end": hm("13:30"), "why": "ABC treatments in the complex block"},
        {"accessory": "ABC", "start": hm("16:00"), "end": hm("17:00"), "why": "new starts and MHRC patients"},
        {"accessory": "BREAST_BOARD", "start": hm("16:00"), "end": hm("17:00"), "why": "new starts and MHRC patients"},
        {"accessory": "BREAST_BOARD", "start": hm("18:00"), "end": hm("26:00"), "why": "linac only after 18:00"},
    ],
    # Accessories booked on the CT simulator (planning scans) today: all inside
    # CT hours and outside the reserved windows (checked by ct_booking_problems).
    "ct_sim_bookings": [
        {"accessory": "ABC", "start": hm("11:00"), "end": hm("11:40"), "label": "DIBH planning CT"},
        {"accessory": "ABC", "start": hm("14:00"), "end": hm("14:45"), "label": "DIBH coaching"},
        {"accessory": "BREAST_BOARD", "start": hm("11:30"), "end": hm("12:10"), "label": "Breast planning CT"},
        {"accessory": "BREAST_BOARD", "start": hm("14:50"), "end": hm("15:30"), "label": "Breast planning CT"},
        {"accessory": "BREAST_BOARD", "start": hm("17:10"), "end": hm("17:50"), "label": "Breast planning CT"},
    ],
    # Machine downtime rules (department answers):
    #   up to 60 min:  nobody is sent home; ongoing patients are all treated
    #                  today; a few new starts may be proposed for deferral (when
    #                  they can no longer finish by 17:00, or fitting them in would
    #                  keep patients already waiting much longer); the rest of the
    #                  day is re-planned.
    #   over 120 min:  new starts move to the next day except urgent palliative
    #                  starts; some ongoing patients may be deferred.
    #   Either way the oncologist or senior RTT approves every deferral.
    "downtime_short_max_min": 60,
    "downtime_long_min": 120,
    # Soft-constraint weights (cost per 10 minutes of deviation). Tunable per
    # department; the Rule Studio exposes them as plain-language sliders.
    "weights": {
        "pref_general": 1.0,       # stay near the patient's usual time
        "pref_paying": 4.0,        # paying patients: their preferred time where possible
        "pref_flexible": 0.2,      # inpatients, dormitory, nearby: can move
        "pref_tolerance": 30,      # minutes of free movement around preference
        "pref_tolerance_paying": 15,
        "elderly_after_1pm": 1.5,  # older patients: earlier is better
        "late_evening": 2.0,       # non-flexible patients finishing after 21:00
        "night": 1.0,              # anyone finishing after 23:00 (keeps the day short)
        "mhrc_wait": 2.0,          # MHRC patients: as soon after 16:00 as possible
        "complex_outside_block": 3.0,
        "pref_complex": 0.2,       # complex cases: staff availability outranks requests
        "overtime": 6.0,
        "move": 3.0,               # re-planning: moving a patient who can still be told
        "move_long": 3.0,          # ... and extra beyond 60 min, so small shifts are shared out
        "present_wait": 20.0,      # re-planning: each minute a patient already here waits
        "present_long_wait": 50.0, # ... and extra beyond 60 min, so nobody waits for hours
        "unscheduled": 1000.0,
    },
    "elderly_pref_before": hm("13:00"),
    "late_evening_after": hm("21:00"),
    "night_after": hm("23:00"),
    "target_utilisation": 0.92,    # for new-start capacity forecasting
}

# Total body irradiation: about once every two to three months, known a month
# ahead. Two fractions a day of 60-90 min: the first treatment of the morning
# and one in the evening. New starts are tapered in the week before.
TBI_PLAN = {"machine": "VERSA", "days": 3, "fraction_min": 90,
            "slots": [(hm("08:30"), hm("10:00")), (hm("18:30"), hm("20:00"))]}


def ct_booking_problems(dept: dict | None = None) -> list[str]:
    """CT-simulator bookings outside CT hours or inside a linac reservation."""
    d = dept or DEPARTMENT
    lo, hi = d["ct_sim_hours"]
    out = []
    for b in d["ct_sim_bookings"]:
        if b["start"] < lo or b["end"] > hi:
            out.append(f"{b['label']} {fmt(b['start'])}-{fmt(b['end'])}: outside CT hours")
        for r in d["accessory_reservations"]:
            if r["accessory"] == b["accessory"] and b["start"] < r["end"] and b["end"] > r["start"]:
                out.append(f"{b['label']} {fmt(b['start'])}-{fmt(b['end'])}: {b['accessory']} "
                           f"reserved for the linac ({r['why']})")
    return out
