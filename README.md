# RAD-SMART: Health-a-thon 2026 entry

**Radiotherapy AI-assisted Dynamic Scheduling, Machine Allocation and Resource Tracking.** Cancer track, use case 04: Clinic Operations & Patient Flow. Team: Dr Akshay Dinesan, Manipal (team leader, doctor partner); Abhinand T M (technical lead); P S Raghotham Rao (lead engineer); Dr Shirley Lewis Salins and Dr Umesh Velu (doctor partners).

RAD-SMART is an assistive, not diagnostic, operations layer for radiotherapy departments. It predicts each session's machine-minutes, gives each course a new-start slot and a standing slot in which hard rules cannot be broken, repairs the day live when a machine breaks down, stress-tests plans in a digital twin, and explains decisions and messages patients in their own language through Sarvam AI. A person approves every change: the doctor each course, a technologist or doctor each breakdown response.

**It runs inside CARE**, the Open Healthcare Network's open-source hospital information system, as a pair of plugins with a **RADSMART** button on the patient's visit page (`app/`, see [`app/README.md`](app/README.md)).

**Live results page:** https://psraghothamrao8.github.io/RAD-SMART/ (GitHub Pages, served from `docs/`)

**Pitch deck:** https://psraghothamrao8.github.io/RAD-SMART/deck/ (web) · [PDF](docs/deck/RAD-SMART_Pitch_Deck.pdf)

**Technical guide (meeting prep):** https://psraghothamrao8.github.io/RAD-SMART/tech/ · **The maths, worked through:** https://psraghothamrao8.github.io/RAD-SMART/tech/maths.html

## What is in this folder

| Path | What it is |
|---|---|
| `RAD-SMART.pdf` | Original problem statement from Dr Akshay Dinesan |
| `docs/RAD-SMART_Research_Report.pdf` (`.docx`, `.md`) | Full research report: problem, evidence, five approaches and the choice, solution design, PoC results, KPIs, implementation plan, pilot, requirements, budget, risks, references |
| `docs/RAD-SMART_Impact_Analysis.pdf` (`.docx`, `.md`) | Four pages: how much RAD-SMART improves waiting, with and without it, on the original dataset (the department's records) and on the simulated dataset, and what it costs |
| `app/` | The application: a backend plugin (`care_radsmart`, Django) and a frontend plugin (`care_radsmart_fe`, React) for CARE. Setup, roles, permissions and the API are in `app/README.md` |
| `docs/Round1_Submission_Kit.pdf` (`.docx`, `.md`) | Ready-to-paste answers for the five Round 1 sections, deck outline, video script, likely jury questions, checklist, and links to the published deck and results page |
| `docs/figures/` | All figures (architecture, daily loop, PoC charts, screenshots of the CARE application with synthetic patients) |
| `docs/figures-src/` | HTML sources of the architecture and daily-loop diagrams |
| `poc/` | Working proof of concept in Python on synthetic patients, with its digital twin calibrated on aggregates of the department's records (see `poc/README.md`) |
| `tools/analyse_department_data.py` | Summarises the department's anonymised spreadsheet into the aggregates the twin uses: `python tools/analyse_department_data.py "<file>.xlsx"`. The spreadsheet is never committed |
| `tools/build_docs.py` | Rebuilds the DOCX and PDF from the Markdown: `python tools/build_docs.py docs/<file>.md` |
| `docs/index.html` | Interactive results page (the Round 1 prototype link), served by GitHub Pages. Built from `docs/web/page_template.html` and the PoC output; `docs/web/rad-smart-prototype.html` is the same page for Claude artifacts |
| `docs/deck/` | Pitch deck: `RAD-SMART_Pitch_Deck.pdf`, the web version `index.html`, and the 10 slide sources in `src/` |
| `tools/build_deck.py` | Rebuilds the web deck and its PDF from `docs/deck/src/` (needs Google Chrome): `python tools/build_deck.py` |
| `tools/build_results_page.py` | Rebuilds both copies of the results page after a PoC run: `python tools/build_results_page.py` |

## Key dates

- Round 1 closed on 25 Sep 2026, and we were shortlisted.
- The build sprint runs 5 Oct – 8 Nov, and the Top 30 are announced by 14 Nov.
- The grand finale is at IIT Bombay on 28 Nov 2026.

## What the department's records show

The department shared anonymised arrival and treatment records for 55 days, October–December 2024 (3,137 patient-days). We use them only as aggregates.

- The median wait from arrival to treatment is 34 minutes, but one patient in ten waits more than 109 minutes. 22% are treated more than an hour after their appointment, and only 29% within 15 minutes of it.
- Waits build through the day, from about 19 minutes for patients arriving before 10:00 to about 66 minutes after 19:00, and evening patients now come about 32 minutes early.

## With and without RAD-SMART

The impact analysis (`docs/RAD-SMART_Impact_Analysis.pdf`) keeps the two datasets apart.

| Dataset | 90th-percentile wait, without → with | Treated more than 1 hour late, without → with |
|---|---|---|
| Original: the department's 55 recorded days, re-planned in the twin | 108.6 → **70.4 min** (−35%) | 22.2% → **5.7%** |
| Simulated: 12 weeks of synthetic courses with standing slots | 81.6 → **49.3 min** (−40%) | 18.6% → **3.6%** |

The price, over the 12 weeks: the last patient finishes at about 00:07 instead of 21:55, one new start in five begins a little later (0.4 working days on average), and a time the patient asks for is kept less often.

## Headline PoC results (synthetic patients, 300 simulated days)

Tested under the department's own rules (its answers of 21 September and 24 October 2026) on an 87-patient day from 08:30 to 01:00, 10 patients more than the busiest recorded day, in a digital twin calibrated on the records. Against the department's busiest recorded days (70–77 patients):

- The 90th-percentile wait from arrival to the treatment room falls from 130 to 76 minutes, and the share treated more than an hour after their time from 27% to 6%. The share treated within ±15 minutes rises from 30% to 53%.
- The median wait stays about the same (36 against 38 minutes), because patients are asked to arrive 20 minutes early (45 for pelvic patients) to prepare. Waits no longer build up in the evening: about 36 minutes for morning and evening arrivals alike, against 19 and 66 in the records.
- The independent checker found all 8 hard rules met, including new starts by 17:00, MHRC patients on the 17:00 bus and public-transport patients home by 21:00.
- With live re-planning under the department's downtime rules of 24 October, the median wait after a 45-minute fault is 37 minutes instead of 53 without re-planning: nobody is sent home, and 1 new start moves to the next day. After a 150-minute fault it is 39 minutes instead of 104: one patient who had not left home is sent back (the fraction is added at the end of the course) and 2 new starts move to the next day. Each re-plan takes 10–14 seconds.
- Two-machine new-start planning around a TBI course keeps peak load at 98–99%, instead of 154% on one machine.

The pilot's primary KPI is a 90th-percentile wait at least 25% lower than the records' 109 minutes.

## Data

The prototype's patients are synthetic. `tools/analyse_department_data.py` summarises the department's anonymised spreadsheet into aggregates only (`poc/data/department_profile.json`). The spreadsheet itself is excluded by `.gitignore` and never committed.
