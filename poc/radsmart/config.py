"""Department configuration for the RAD-SMART proof of concept.

Every scheduling rule lives here as data, not code, so the same engine can be
re-used by another department by editing this file (or, in the full product,
through the natural-language Rule Studio, which writes the same structure).

All values are ILLUSTRATIVE. They follow the RAD-SMART problem statement where it
gives numbers and published Indian/international data elsewhere; they must be
replaced with the real department's parameters before any pilot.
"""

from __future__ import annotations


def hm(text: str) -> int:
    """'13:30' -> minutes after midnight."""
    h, m = text.split(":")
    return int(h) * 60 + int(m)


def fmt(minutes: float) -> str:
    """Minutes after midnight -> 'HH:MM'."""
    minutes = int(round(minutes))
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


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
# --------------------------------------------------------------------------
TECHNIQUES = {
    "PALL": dict(label="Palliative 2D/3D", median=4.0, first_extra=10, sigma=0.28,
                 complex=False, accessories=[], course=(1, 10), machines=["VERSA", "HALCYON"]),
    "3DCRT": dict(label="3D-CRT", median=5.0, first_extra=11, sigma=0.27,
                  complex=False, accessories=[], course=(20, 30), machines=["VERSA", "HALCYON"]),
    "IMRT": dict(label="IMRT", median=6.5, first_extra=13, sigma=0.25,
                 complex=False, accessories=[], course=(30, 35), machines=["VERSA", "HALCYON"]),
    "VMAT": dict(label="VMAT", median=5.5, first_extra=13, sigma=0.25,
                 complex=False, accessories=[], course=(25, 33), machines=["VERSA", "HALCYON"]),
    "BREAST": dict(label="Breast (breast board)", median=6.0, first_extra=11, sigma=0.25,
                   complex=False, accessories=["BREAST_BOARD"], course=(15, 25),
                   machines=["VERSA", "HALCYON"]),
    "BREAST_DIBH": dict(label="Breast DIBH (ABC)", median=10.0, first_extra=14, sigma=0.25,
                        complex=False, accessories=["ABC", "BREAST_BOARD"], course=(15, 25),
                        machines=["VERSA"]),
    "SBRT": dict(label="SBRT", median=26.0, first_extra=12, sigma=0.22,
                 complex=True, accessories=[], course=(3, 5), machines=["VERSA"]),
    "SRT": dict(label="SRT", median=22.0, first_extra=12, sigma=0.22,
                complex=True, accessories=[], course=(1, 5), machines=["VERSA"]),
    "CSI": dict(label="Craniospinal (CSI)", median=25.0, first_extra=15, sigma=0.22,
                complex=True, accessories=[], course=(20, 30), machines=["VERSA", "HALCYON"]),
    "TBI": dict(label="Total body (TBI)", median=50.0, first_extra=10, sigma=0.18,
                complex=True, accessories=[], course=(1, 6), machines=["VERSA"]),
}

# Anatomical site groups change set-up time a little (immobilisation, imaging).
SITE_EFFECT = {"HN": 1.10, "BRAIN": 1.05, "THORAX": 1.00, "BREAST": 1.00,
               "PELVIS": 0.97, "ABDOMEN": 1.00, "BONE": 0.92, "WHOLE_BODY": 1.00}

MOBILITY_EXTRA = {"walking": 0.0, "wheelchair": 3.0, "stretcher": 8.0}
IMAGING_EXTRA = {"none": 0.0, "kv": 1.0, "cbct": 2.5}


DEPARTMENT = {
    "name": "Demo radiotherapy department (synthetic data)",
    "grid_min": 2,                  # optimiser time resolution (minutes)
    "day_start": hm("07:30"),       # first patient after morning machine QA
    "regular_end": hm("20:30"),     # two RTT shifts; later = overtime
    "hard_end": hm("21:30"),        # nothing may be planned after this
    "machines": {
        "VERSA": {"label": "Versa HD",
                  "blocks": [{"start": hm("13:30"), "end": hm("14:00"),
                              "label": "Blood irradiation"}]},
        "HALCYON": {"label": "Halcyon", "blocks": []},
    },
    # Complex procedures (SBRT/SRT/TBI/CSI) need senior staff: hard window.
    "senior_staff_window": (hm("10:00"), hm("17:00")),
    "senior_staff_concurrent": 1,   # one senior physicist across all machines
    # Protected block preferred for complex procedures (problem statement s.11).
    "protected_block": (hm("12:00"), hm("13:30")),
    "new_start_latest_end": hm("17:00"),
    # Plan to finish this many minutes before any hard deadline (17:00 new-start
    # cut-off, senior-staff window, last bus) so ordinary delays cannot break it.
    "deadline_buffer_min": 25,
    # Same-day palliative starts: capacity held back, used as catch-up buffer
    # when no urgent patient appears.
    "urgent_holds": [{"machine": "VERSA", "start": hm("14:40"), "minutes": 20},
                     {"machine": "VERSA", "start": hm("16:10"), "minutes": 20}],
    "accessories": {"ABC": {"units": 1, "transfer_min": 10},
                    "BREAST_BOARD": {"units": 2, "transfer_min": 5}},
    # Accessories booked on the CT simulator (planning scans) today.
    "ct_sim_bookings": [
        {"accessory": "ABC", "start": hm("10:00"), "end": hm("10:45"), "label": "DIBH planning CT"},
        {"accessory": "ABC", "start": hm("15:30"), "end": hm("16:15"), "label": "DIBH coaching"},
        {"accessory": "BREAST_BOARD", "start": hm("09:00"), "end": hm("09:40"), "label": "Breast planning CT"},
        {"accessory": "BREAST_BOARD", "start": hm("14:30"), "end": hm("15:10"), "label": "Breast planning CT"},
    ],
    # Soft-constraint weights (cost per 10 minutes of deviation). Tunable per
    # department; the Rule Studio exposes them as plain-language sliders.
    "weights": {
        "pref_general": 1.0,       # stay near the patient's usual/requested time
        "pref_requested": 2.0,     # patient explicitly requested a time
        "pref_flexible": 0.3,      # dormitory residents: flexible
        "pref_tolerance": 30,      # minutes of free movement around preference
        "elderly_after_1pm": 1.5,  # elderly: earlier is better
        "transport_after_noon": 1.0,
        "inpatient_outside": 2.0,  # ward logistics window
        "mhrc_outside": 4.0,       # hospice/respite vehicle window
        "complex_outside_block": 3.0,
        "pref_complex": 0.2,       # complex cases: staff availability outranks requests
        "routine_in_block": 0.6,
        "overtime": 6.0,
        "unscheduled": 1000.0,
    },
    "inpatient_window": (hm("10:00"), hm("16:00")),
    "mhrc_window": (hm("09:30"), hm("12:00")),
    "elderly_pref_before": hm("13:00"),
    "transport_pref_before": hm("12:00"),
    "target_utilisation": 0.92,    # for new-start capacity forecasting
}
