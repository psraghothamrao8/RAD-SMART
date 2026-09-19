# RAD-SMART proof of concept

This proof of concept implements the predict, optimise and simulate core of RAD-SMART on **synthetic data only**. No patient data is used or needed.

## Run it

```bash
pip install -r requirements.txt
python run_poc.py
```

A full run takes under a minute on a laptop. Results are identical from run to run (fixed seeds, ties broken by patient ID); only solver timings vary. It writes to `results/`:

| File | Contents |
|---|---|
| `results.json` | Every number quoted in the report: assumptions, model accuracy, solver statistics, KPIs |
| `run_log.txt` | Human-readable summary tables |
| `schedule_rad_smart.csv` | The optimised 67-patient day, with a reason code for every placement |
| `web_data.json` | Chart data for the interactive results page |
| `fig1`–`fig6*.png` | Figures used in the report |

## What each module does

| Module | Role |
|---|---|
| `radsmart/config.py` | Department rules as data: techniques and durations, operating day, blood-irradiation slot, senior-staff window, protected block, new-start cut-off and buffer, urgent holds, accessories and CT-simulator bookings, objective weights |
| `radsmart/synth.py` | Synthetic patients, days, urgent arrivals and 12,000 historical sessions; models "current practice" as hourly block appointments |
| `radsmart/duration_model.py` | Lookup table of averages versus quantile gradient boosting (P50 / P80), with evaluation |
| `radsmart/scheduler.py` | Two-stage coarse-to-fine MILP (HiGHS via SciPy). Hard rules as constraints, soft preferences in the objective, reason codes, minimum-disruption re-planning |
| `radsmart/simulate.py` | Monte Carlo digital twin: arrivals, no-shows, duration noise, urgent patients, faults, message compliance, accessory hand-offs; KPIs defined as in Munshi et al. (2021) |
| `radsmart/forecast.py` | Committed load from remaining fractions, pipeline of new patients, 2-day-ahead new-start recommendation per machine, compared with equal head-count |
| `run_poc.py` | Runs every experiment and draws the figures |

## Headline results (300 simulated days)

| Metric | Current practice (modelled) | RAD-SMART (ML) |
|---|---|---|
| Median wait, arrival to treatment room | 70.8 min | 19.2 min |
| 90th-percentile wait | 226.5 min | 52.0 min |
| Within ±15 min of appointment | 15.5% | 62.4% |
| Live re-plan after a 30-min fault | n/a | 4.0 s; median wait 93.0 → 19.4 min |

## Limitations

- The data are synthetic, and the "current practice" baseline is a model, not a measurement.
- The day simulation covers one machine; the two-machine test covers the forecast only.
- Production would use OR-Tools CP-SAT; this PoC uses the open-source HiGHS MILP solver through SciPy.

See Section 7 of `../docs/RAD-SMART_Research_Report.pdf` for full details.
