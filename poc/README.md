# RAD-SMART proof of concept

This proof of concept implements the predict, optimise and simulate core of RAD-SMART on **synthetic patients**: the day optimiser, the standing-slot allocator for courses, and the breakdown triage. The CARE application in `../app/` calls the same engine. Its digital twin is calibrated on aggregates of the department's anonymised arrival and treatment records (`data/department_profile.json`). No row-level patient data is used or stored.

## Run it

```bash
pip install -r requirements.txt
python run_poc.py
```

To rebuild the department profile from the spreadsheet, which is kept outside the repository:

```bash
python ../tools/analyse_department_data.py "Anonymised data_RADSMART.xlsx"
```

A full run takes about three minutes on a laptop. Seeds are fixed and ties are broken by patient ID, so runs reproduce, with one exception: a solve that stops at its time limit can return a slightly different best plan. Solver timings always vary. It writes to `results/`, and the figures to `../docs/figures/`:

| File | Contents |
|---|---|
| `results.json` | Every number quoted in the report: assumptions, model accuracy, solver statistics, KPIs |
| `run_log.txt` | Human-readable summary tables |
| `schedule_rad_smart.csv` | The optimised 87-patient day, with the reporting time and a reason code for every placement |
| `web_data.json` | Chart data as JSON: waits by hour, the day plan, both breakdowns and the forecast |
| `../docs/figures/fig0`–`fig6*.png` | Figures used in the report (`fig0` summarises the department's records) |
| `../docs/figures/fig7_original_dataset.png`, `fig8_simulated_dataset.png` | The impact analysis and the research paper: with and without RAD-SMART on the original and on the simulated dataset |

## What each module does

| Module | Role |
|---|---|
| `radsmart/config.py` | The department's rules as data (answers of 21 Sep and 24 Oct 2026): operating day 08:30–01:00, blood-irradiation slot, senior-staff window and protected block, new-start and urgent cut-offs, MHRC slots and bus, public-transport limit, reporting and bladder-filling times, urgent holds, one breast board and one ABC with CT-simulator bookings and reservations, downtime rules, TBI, objective weights |
| `radsmart/synth.py` | Synthetic patients (including MHRC, dormitory, nearby, public-transport, paying and pelvic patients, and the department's languages), days, urgent arrivals and 12,000 historical sessions; books "current practice" appointment times the way the department's records show |
| `radsmart/department.py` | Reads the department profile: the recorded spread of appointment times on days of similar volume, and how early or late patients arrive for each hour. Books today's appointment times and draws arrivals for the twin |
| `radsmart/duration_model.py` | Lookup table of averages versus gradient boosting (expected, P50 and P80 minutes), with evaluation |
| `radsmart/scheduler.py` | Two-stage coarse-to-fine MILP (HiGHS via SciPy). Hard rules as constraints, soft preferences in the objective, reason codes, re-planning that treats patients already waiting first, and an independent rule checker (`check_plan`) |
| `radsmart/simulate.py` | Monte Carlo digital twin: reporting times, arrivals drawn from the recorded habits, no-shows, duration noise, urgent patients, imaging holds, faults and deferrals, message compliance, call-in of flexible patients, accessory hand-offs; KPIs defined as in Munshi et al. (2021) |
| `radsmart/courses.py` | Courses and standing slots: treatment dates for each pattern (daily, alternate days, twice a day, twice or once a week), a slot book per machine and date, the allocator that gives a new-start slot before 17:00 and one standing slot free on every treatment date (keeping 150 minutes before 17:00 for new starts), slot-change requests, and the day's plan built from standing slots, with a ninth checker rule |
| `radsmart/downtime.py` | Breakdown triage under the department's rules of 24 Oct 2026: up to 60 minutes everyone is treated with overtime; over 60 minutes only as many patients are sent back as the expected downtime needs; new starts wait for the machine; patients at home are told to postpone travel; patients already waiting go first. Proposes only: a person approves |
| `radsmart/weeks.py` | Twelve weeks of synthetic courses booked twice, today's way and with standing slots, played out in the twin with common random numbers |
| `radsmart/forecast.py` | Committed load from remaining fractions, pipeline of new patients, TBI capacity, 2-day-ahead new-start recommendation per machine, compared with equal head-count and a manual taper |
| `run_poc.py` | Checks the twin against the records, runs every experiment (the day, the urgent-hold trade-off, both breakdowns, the weeks with standing slots, the forecast), the with/without analysis on both datasets, and draws the figures |

## Headline results (300 simulated days)

| Metric | Today, recorded (70–77-patient days) | Today's booking, twin projection (87 patients) | RAD-SMART, ML (87 patients) |
|---|---|---|---|
| Median wait, arrival to treatment room (preparation included) | 37.5 min | 133.2 min | 36.3 min |
| 90th-percentile wait | 130.0 min | 210.2 min | 75.5 min |
| Within ±15 min of appointment | 30.1% | 10.0% | 52.9% |
| More than 1 hour after appointment | 27.4% | 66.3% | 5.8% |

| Machine fault | RAD-SMART plan, no re-planning | RAD-SMART live re-planning |
|---|---|---|
| 45 min at 11:00: median wait | 52.6 min | 37.3 min (re-planned in 10.1 s; nobody sent home; 1 new start to the next day) |
| 150 min at 10:00: median wait | 104.4 min | 39.4 min (re-planned in 13.9 s; 1 patient sent back before travelling; 2 new starts to the next day) |

| With and without RAD-SMART | 90th-percentile wait | More than 1 hour late |
|---|---|---|
| Original dataset: the department's 55 recorded days, re-planned in the twin | 108.6 → 70.4 min | 22.2% → 5.7% |
| Simulated dataset: 12 weeks with standing slots (about 63 patients a day) | 81.6 → 49.3 min | 18.6% → 3.6% |

Across all 55 recorded days the twin, replaying today's booking, gives a 90th-percentile wait of 106.1 minutes against the 108.6 recorded. It under-predicts the longest waits on quieter days and over-predicts them on the busiest, so today's figures are quoted from the records.

## Limitations

- The patients are synthetic. The rules are the department's, and the twin's booking pattern and arrival habits come from its records, but session lengths are estimates: the department records arrival and treatment-start times, not how long sessions take.
- RAD-SMART's benefit assumes that patients stop arriving early once times are kept. If they keep today's habits, the 90th-percentile wait is 110 minutes rather than 76.
- The day simulation covers one machine; the two-machine test covers the forecast only.
- The 12-week test starts from an empty machine. Standing slots cost a later evening (about 00:07 instead of 21:55), a short delay for one new start in five, and fewer requested times kept (4% within 15 minutes against 31%).
- Production would use OR-Tools CP-SAT; this PoC uses the open-source HiGHS MILP solver through SciPy.

See Section 7 of `../docs/RAD-SMART_Research_Report.pdf` for full details.
