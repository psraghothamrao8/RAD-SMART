# RAD-SMART: Health-a-thon 2026 entry

**Radiotherapy AI-assisted Dynamic Scheduling, Machine Allocation and Resource Tracking.** Cancer track, use case 04: Clinic Operations & Patient Flow. Team leader and doctor partner: Dr Akshay Dinesan, Manipal. Technical lead: Abhinand T M. Team: P S Raghotham Rao, Dr Shirley Lewis Salins, Dr Umesh Velu.

RAD-SMART is an assistive, not diagnostic, operations layer for radiotherapy departments. It predicts each session's machine-minutes, builds and live-repairs a daily plan in which hard rules cannot be broken, stress-tests plans in a digital twin, and explains decisions and messages patients in their own language through Sarvam AI. A person approves every change.

**Live results page:** https://psraghothamrao8.github.io/RAD-SMART/ (GitHub Pages, served from `docs/`)

**Pitch deck:** https://psraghothamrao8.github.io/RAD-SMART/deck/ (web) · [PDF](docs/deck/RAD-SMART_Pitch_Deck.pdf)

## What is in this folder

| Path | What it is |
|---|---|
| `RAD-SMART.pdf` | Original problem statement from Dr Akshay Dinesan |
| `docs/RAD-SMART_Research_Report.pdf` (`.docx`, `.md`) | Full research report: problem, evidence, five approaches and the choice, solution design, PoC results, KPIs, implementation plan, pilot, requirements, budget, risks, references |
| `docs/Round1_Submission_Kit.pdf` (`.docx`, `.md`) | Ready-to-paste answers for the five Round 1 sections, deck outline, video script, likely jury questions, checklist, and links to the published deck and results page |
| `docs/figures/` | All figures (architecture, daily loop, PoC charts) |
| `docs/figures-src/` | HTML sources of the architecture and daily-loop diagrams |
| `poc/` | Working proof of concept in Python on synthetic patients, with its digital twin calibrated on aggregates of the department's records (see `poc/README.md`) |
| `tools/analyse_department_data.py` | Summarises the department's anonymised spreadsheet into the aggregates the twin uses: `python tools/analyse_department_data.py "<file>.xlsx"`. The spreadsheet is never committed |
| `tools/build_docs.py` | Rebuilds the DOCX and PDF from the Markdown: `python tools/build_docs.py docs/<file>.md` |
| `docs/index.html` | Interactive results page (the Round 1 prototype link), served by GitHub Pages. Built from `docs/web/page_template.html` and the PoC output; `docs/web/rad-smart-prototype.html` is the same page for Claude artifacts |
| `docs/deck/` | Pitch deck: `RAD-SMART_Pitch_Deck.pdf`, the web version `index.html`, and the 14 slide sources in `src/` |
| `tools/build_deck.py` | Rebuilds the web deck and its PDF from `docs/deck/src/` (needs Google Chrome): `python tools/build_deck.py` |
| `tools/build_results_page.py` | Rebuilds both copies of the results page after a PoC run: `python tools/build_results_page.py` |

## Key dates

- **Round 1 submission closes 25 Sep 2026, 23:59.** Aim to submit by 23 Sep.
- Shortlisting runs 26 Sep – 3 Oct, the build sprint 5 Oct – 8 Nov, and the Top 30 are announced by 14 Nov.
- The grand finale is at IIT Bombay on 28 Nov 2026.

## What the department's records show

The department shared anonymised arrival and treatment records for 55 days, October–December 2024 (3,137 patient-days). We use them only as aggregates.

- The median wait from arrival to treatment is 34 minutes, but one patient in ten waits more than 109 minutes. 22% are treated more than an hour after their appointment, and only 29% within 15 minutes of it.
- Waits build through the day, from about 19 minutes for patients arriving before 10:00 to about 66 minutes after 19:00, and evening patients now come about 32 minutes early.

## Headline PoC results (synthetic patients, 300 simulated days)

Tested under the department's own rules (its answers of 21 September 2026) on an 87-patient day from 08:30 to 01:00, 10 patients more than the busiest recorded day, in a digital twin calibrated on the records. Against the department's busiest recorded days (70–77 patients):

- The 90th-percentile wait from arrival to the treatment room falls from 130 to 76 minutes, and the share treated more than an hour after their time from 27% to 6%. The share treated within ±15 minutes rises from 30% to 53%.
- The median wait stays about the same (36 against 38 minutes), because patients are asked to arrive 20 minutes early (45 for pelvic patients) to prepare. Waits no longer build up in the evening: about 36 minutes for morning and evening arrivals alike, against 19 and 66 in the records.
- The independent checker found all 7 hard rules met, including new starts by 17:00, MHRC patients on the 17:00 bus and public-transport patients home by 21:00.
- With live re-planning under the department's downtime rules, the median wait after a 45-minute fault is 39 minutes instead of 53 without re-planning; every ongoing patient is treated the same day and 1 new start is proposed for the next day. After a 150-minute fault it is 36 minutes instead of 104, with 5 new starts moved to the next day. Each re-plan takes 2–11 seconds.
- Two-machine new-start planning around a TBI course keeps peak load at 98–99%, instead of 154% on one machine.

The pilot's primary KPI is a 90th-percentile wait at least 25% lower than the records' 109 minutes.

## Data

The prototype's patients are synthetic. `tools/analyse_department_data.py` summarises the department's anonymised spreadsheet into aggregates only (`poc/data/department_profile.json`). The spreadsheet itself is excluded by `.gitignore` and never committed.
