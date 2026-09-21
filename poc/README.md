# RAD-SMART proof of concept

This proof of concept implements the predict, optimise and simulate core of RAD-SMART on **synthetic data only**. No patient data is used or needed.

## Run it

```bash
pip install -r requirements.txt
python run_poc.py
```

A full run takes about four minutes on a laptop. Seeds are fixed and ties are broken by patient ID, so runs reproduce, with one exception: a solve that stops at its time limit (the average-table plan) can return a slightly different best plan. Solver timings always vary. It writes to `results/`:

| File | Contents |
|---|---|
| `results.json` | Every number quoted in the report: assumptions, model accuracy, solver statistics, KPIs |
| `run_log.txt` | Human-readable summary tables |
| `schedule_rad_smart.csv` | The optimised 87-patient day, with the reporting time and a reason code for every placement |
| `web_data.json` | Chart data for the interactive results page |
| `fig1`–`fig6*.png` | Figures used in the report |

## What each module does

| Module | Role |
|---|---|
| `radsmart/config.py` | The department's rules as data (answers of 21 Sep 2026): operating day 08:30–01:00, blood-irradiation slot, senior-staff window and protected block, new-start and urgent cut-offs, MHRC slots and bus, public-transport limit, reporting and bladder-filling times, urgent holds, one breast board and one ABC with CT-simulator bookings and reservations, downtime rules, TBI, objective weights |
| `radsmart/synth.py` | Synthetic patients (including MHRC, dormitory, nearby, public-transport, paying and pelvic patients, and the department's languages), days, urgent arrivals and 12,000 historical sessions; models "current practice" as hourly block appointments |
| `radsmart/duration_model.py` | Lookup table of averages versus gradient boosting (expected, P50 and P80 minutes), with evaluation |
| `radsmart/scheduler.py` | Two-stage coarse-to-fine MILP (HiGHS via SciPy). Hard rules as constraints, soft preferences in the objective, reason codes, re-planning that treats patients already waiting first, and an independent rule checker (`check_plan`) |
| `radsmart/simulate.py` | Monte Carlo digital twin: reporting times, arrivals, no-shows, duration noise, urgent patients, imaging holds, faults and deferrals, message compliance, call-in of flexible patients, accessory hand-offs; KPIs defined as in Munshi et al. (2021) |
| `radsmart/forecast.py` | Committed load from remaining fractions, pipeline of new patients, TBI capacity, 2-day-ahead new-start recommendation per machine, compared with equal head-count and a manual taper |
| `run_poc.py` | Runs every experiment (the day, the urgent-hold trade-off, both downtime rules, the forecast) and draws the figures |

## Headline results (300 simulated days)

| Metric | Current practice (modelled) | RAD-SMART (ML) |
|---|---|---|
| Median wait, arrival to treatment room (preparation included) | 100.0 min | 32.8 min |
| 90th-percentile wait | 172.9 min | 61.6 min |
| Within ±15 min of appointment | 9.6% | 72.6% |
| 45-min fault at 11:00: median wait | 144.0 min | 40.3 min (re-planned in 26.3 s) |
| 150-min fault at 10:00: median wait | 215.7 min | 35.0 min (re-planned in 3.7 s; new starts to the next day) |

## Limitations

- The data are synthetic. The rules are the department's, but session lengths are estimates (no timestamps exist yet), and the "current practice" baseline is a model, not a measurement.
- The day simulation covers one machine; the two-machine test covers the forecast only.
- Production would use OR-Tools CP-SAT; this PoC uses the open-source HiGHS MILP solver through SciPy.

See Section 7 of `../docs/RAD-SMART_Research_Report.pdf` for full details.
