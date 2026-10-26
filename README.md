# RAD-SMART: Health-a-thon 2026 entry

**Radiotherapy AI-assisted Dynamic Scheduling, Machine Allocation and Resource Tracking.** Cancer track, use case 04: Clinic Operations & Patient Flow. Team: Dr Akshay Dinesan, Manipal (team leader, doctor partner); Abhinand T M (technical lead); P S Raghotham Rao (lead engineer); Dr Shirley Lewis Salins and Dr Umesh Velu (doctor partners).

RAD-SMART is an assistive, not diagnostic, operations layer for radiotherapy departments. It predicts each session's machine-minutes, gives each course a new-start slot and a standing slot in which hard rules cannot be broken, repairs the day live when a machine breaks down, stress-tests plans in a digital twin, and explains decisions and messages patients in their own language through Sarvam AI. A person approves every change: the doctor each course, a technologist or doctor each breakdown response.

**It runs inside CARE**, the Open Healthcare Network's open-source hospital information system, as a pair of plugins with a **RADSMART** button on the patient's visit page (`app/`, see [`app/README.md`](app/README.md)).

**Patients and Sarvam AI.** After each approval RAD-SMART drafts the patient's message in Kannada, Malayalam, Hindi or Konkani (Tulu speakers read Kannada script) with Sarvam Translate, and a voice note with Bulbul v3; a technologist opens it in WhatsApp and presses send. Each patient has one private phone page, with no app and no login: today's time, changes after a breakdown, messages with voice notes, a QR code that reception scans to check them in, and four reply buttons (on my way, late, cannot come, want another time). Sarvam-105B explains a proposed time in plain words. A translation that changes a time, or an explanation that invents one, is thrown away; without Sarvam everything works in English. In our evaluation ([`docs/evaluation/`](docs/evaluation/sarvam_evaluation.md)), 140 of 140 translations across five languages kept every time, and 20 of 20 explanations were accepted.

**Phase 2 final submission:** [PDF](docs/Phase2_Submission.pdf) ([DOCX](docs/Phase2_Submission.docx)): the eight template sections, what is built and what is not, and the evidence.

**Demo video (3¾ min, narrated, with captions, recorded on the live demonstration):** https://psraghothamrao8.github.io/RAD-SMART/#demo · [MP4 file](docs/media/RAD-SMART_demo.mp4)

[![The RAD-SMART demo: a recording of the app in CARE](docs/media/demo_poster.jpg)](https://psraghothamrao8.github.io/RAD-SMART/#demo)

**Try it live:** https://radsmart.braveglacier-5f9807f7.uaenorth.azurecontainerapps.io/try/ (synthetic patients only). In the demonstration, go straight in as a doctor, reception, a technologist or a patient with one click and no password, and a patient's messages can go to your own Telegram. In real use, staff sign in to CARE with their own accounts. The demonstration starts again every morning at 05:30 IST; how it is hosted, free, is in [`deploy/azure/`](deploy/azure/README.md).

**How to use the app, and how to demo it:** [User guide (PDF)](docs/RAD-SMART_User_Guide.pdf): the five everyday tasks with screenshots, and a 5-minute demo script

**Website:** https://psraghothamrao8.github.io/RAD-SMART/ (a one-page summary with simple charts; GitHub Pages, served from `docs/`)

**Pitch deck:** https://psraghothamrao8.github.io/RAD-SMART/deck/ (web) · [PDF](docs/deck/RAD-SMART_Pitch_Deck.pdf)

**Research paper:** [PDF](docs/RAD-SMART_Research_Paper.pdf) (8 pages)

**Technical guide (meeting prep):** https://psraghothamrao8.github.io/RAD-SMART/tech/ · **The maths, worked through:** https://psraghothamrao8.github.io/RAD-SMART/tech/maths.html

## What is in this folder

| Path | What it is |
|---|---|
| `docs/Phase2_Submission.pdf` (`.docx`, `.md`) | The Phase 2 final submission: team and problem, users and solution, the working MVP and AI approach, build sprint progress, evaluation, safety, deployment and costs, next steps, with a short version of each section |
| `docs/evaluation/` | The Sarvam AI evaluation (`sarvam_evaluation.md`), its raw results, and every translation with its back-translation for native speakers to rate (`sarvam_translations_for_rating.csv`). Rerun with `python tools/evaluate_sarvam.py --env-file <file with SARVAM_API_KEY>`; it fetches only missing results |
| `docs/RAD-SMART_User_Guide.pdf` (`.docx`, `.md`) | How to use the app (doctor and technologist, step by step with screenshots) and how to show it: setup checklist, a 5-minute demo script, fallbacks and likely questions |
| `docs/media/` | The demo video (`RAD-SMART_demo.mp4`) and its poster image |
| `docs/RAD-SMART_Research_Paper.pdf` (`.docx`, `.md`) | Eight-page research paper: the problem, the method, results on both datasets, limitations |
| `docs/RAD-SMART_Research_Report.pdf` (`.docx`, `.md`) | Full research report: problem, evidence, five approaches and the choice, solution design, PoC results, KPIs, implementation plan, pilot, requirements, budget, risks, references |
| `docs/RAD-SMART_Impact_Analysis.pdf` (`.docx`, `.md`) | Four pages: how much RAD-SMART improves waiting, with and without it, on the original dataset (the department's records) and on the simulated dataset, and what it costs |
| `app/` | The application: a backend plugin (`care_radsmart`, Django) and a frontend plugin (`care_radsmart_fe`, React) for CARE. Setup, roles, permissions and the API are in `app/README.md` |
| `docs/Round1_Submission_Kit.pdf` (`.docx`, `.md`) | Ready-to-paste answers for the five Round 1 sections, deck outline, video script, likely jury questions, checklist, and links to the published deck and website |
| `docs/figures/` | All figures (architecture, daily loop, PoC charts, screenshots of the CARE application with synthetic patients) |
| `docs/figures-src/` | HTML sources of the architecture and daily-loop diagrams |
| `poc/` | Working proof of concept in Python on synthetic patients, with its digital twin calibrated on aggregates of the department's records (see `poc/README.md`) |
| `tools/analyse_department_data.py` | Summarises the department's anonymised spreadsheet into the aggregates the twin uses: `python tools/analyse_department_data.py "<file>.xlsx"`. The spreadsheet is never committed |
| `tools/build_docs.py` | Rebuilds the DOCX and PDF from the Markdown: `python tools/build_docs.py docs/<file>.md` |
| `docs/index.html` | The project website (the prototype link), served by GitHub Pages. Plain HTML: edit it directly |
| `docs/deck/` | Pitch deck: `RAD-SMART_Pitch_Deck.pdf`, the web version `index.html`, and the 9 slide sources in `src/` |
| `tools/demo-video/` | How the demo video is made: a script drives the app in headless Chrome and records it, and a Remotion project adds titles, captions and the pointer (see its README) |
| `tools/build_deck.py` | Rebuilds the web deck and its PDF from `docs/deck/src/` (needs Google Chrome): `python tools/build_deck.py` |
| `workspace/` | Rebuilds the whole development environment from this repository: `bash workspace/restore.sh` fetches CARE at the pinned commits, wires in the plugins, starts Docker and loads the synthetic data (see `workspace/README.md`) |
| `deploy/azure/` | Hosts the demonstration server on Azure using only an Azure for Students subscription's free services, with a guard that takes it offline before the free hours run out (see `deploy/azure/README.md`) |

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
