# RAD-SMART proof of concept

This proof of concept implements the predict, optimise and simulate core of RAD-SMART on **synthetic patients**. Its digital twin is calibrated on aggregates of the department's anonymised arrival and treatment records (`data/department_profile.json`). No row-level patient data is used or stored.

## Run it

```bash
pip install -r requirements.txt
python run_poc.py
```

To rebuild the department profile from the spreadsheet, which is kept outside the repository:

```bash
python ../tools/analyse_department_data.py "Anonymised data_RADSMART.xlsx"
```

A full run takes about three minutes on a laptop. Seeds are fixed and ties are broken by patient ID, so runs reproduce, with one exception: a solve that stops at its time limit can return a slightly different best plan. Solver timings always vary. It writes to `results/`:

| File | Contents |
|---|---|
| `results.json` | Every number quoted in the report: assumptions, model accuracy, solver statistics, KPIs |
| `run_log.txt` | Human-readable summary tables |
| `schedule_rad_smart.csv` | The optimised 87-patient day, with the reporting time and a reason code for every placement |
| `web_data.json` | Chart data for the interactive results page |
| `fig0`–`fig6*.png` | Figures used in the report (`fig0` summarises the department's records) |

## What each module does

| Module | Role |
|---|---|
| `radsmart/config.py` | The department's rules as data (answers of 21 Sep 2026): operating day 08:30–01:00, blood-irradiation slot, senior-staff window and protected block, new-start and urgent cut-offs, MHRC slots and bus, public-transport limit, reporting and bladder-filling times, urgent holds, one breast board and one ABC with CT-simulator bookings and reservations, downtime rules, TBI, objective weights |
| `radsmart/synth.py` | Synthetic patients (including MHRC, dormitory, nearby, public-transport, paying and pelvic patients, and the department's languages), days, urgent arrivals and 12,000 historical sessions; books "current practice" appointment times the way the department's records show |
| `radsmart/department.py` | Reads the department profile: the recorded spread of appointment times on days of similar volume, and how early or late patients arrive for each hour. Books today's appointment times and draws arrivals for the twin |
| `radsmart/duration_model.py` | Lookup table of averages versus gradient boosting (expected, P50 and P80 minutes), with evaluation |
| `radsmart/scheduler.py` | Two-stage coarse-to-fine MILP (HiGHS via SciPy). Hard rules as constraints, soft preferences in the objective, reason codes, re-planning that treats patients already waiting first, and an independent rule checker (`check_plan`) |
| `radsmart/simulate.py` | Monte Carlo digital twin: reporting times, arrivals drawn from the recorded habits, no-shows, duration noise, urgent patients, imaging holds, faults and deferrals, message compliance, call-in of flexible patients, accessory hand-offs; KPIs defined as in Munshi et al. (2021) |
| `radsmart/forecast.py` | Committed load from remaining fractions, pipeline of new patients, TBI capacity, 2-day-ahead new-start recommendation per machine, compared with equal head-count and a manual taper |
| `run_poc.py` | Checks the twin against the records, runs every experiment (the day, the urgent-hold trade-off, both downtime rules, the forecast) and draws the figures |

## Headline results (300 simulated days)

| Metric | Today, recorded (70–77-patient days) | Today's booking, twin projection (87 patients) | RAD-SMART, ML (87 patients) |
|---|---|---|---|
| Median wait, arrival to treatment room (preparation included) | 37.5 min | 133.2 min | 36.3 min |
| 90th-percentile wait | 130.0 min | 210.2 min | 75.5 min |
| Within ±15 min of appointment | 30.1% | 10.0% | 52.9% |
| More than 1 hour after appointment | 27.4% | 66.3% | 5.8% |

| Machine fault | RAD-SMART plan, no re-planning | RAD-SMART live re-planning |
|---|---|---|
| 45 min at 11:00: median wait | 52.6 min | 39.0 min (re-planned in 1.5 s; 1 new start proposed for the next day) |
| 150 min at 10:00: median wait | 104.4 min | 36.1 min (re-planned in 10.8 s; 5 new starts to the next day) |

On a typical recorded day (60 patients) the twin reproduces today's median wait and punctuality closely (37.5 against 35 minutes; 24% against 28% within ±15 minutes) but under-predicts the longest waits, and on busy days it predicts longer waits than were recorded. Today's figures are therefore quoted from the records.

## Limitations

- The patients are synthetic. The rules are the department's, and the twin's booking pattern and arrival habits come from its records, but session lengths are estimates: the department records arrival and treatment-start times, not how long sessions take.
- RAD-SMART's benefit assumes that patients stop arriving early once times are kept. If they keep today's habits, the 90th-percentile wait is 110 minutes rather than 76.
- The day simulation covers one machine; the two-machine test covers the forecast only.
- Production would use OR-Tools CP-SAT; this PoC uses the open-source HiGHS MILP solver through SciPy.

See Section 7 of `../docs/RAD-SMART_Research_Report.pdf` for full details.
