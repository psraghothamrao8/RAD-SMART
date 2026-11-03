# RAD-SMART

**Radiotherapy AI-assisted Dynamic Scheduling, Machine Allocation and Resource Tracking**

[![Live on Microsoft Azure](https://img.shields.io/badge/live-Microsoft%20Azure-0078D4?logo=microsoftazure&logoColor=white)](https://radsmart.braveglacier-5f9807f7.uaenorth.azurecontainerapps.io/try/)
[![Docker](https://img.shields.io/badge/packaged-Docker-2496ED?logo=docker&logoColor=white)](deploy/azure/Dockerfile)
[![Runs inside CARE](https://img.shields.io/badge/runs%20inside-CARE%20(OHN)-1C5CAB)](https://github.com/ohcnetwork/care)
[![Engine tests](https://github.com/psraghothamrao8/RAD-SMART/actions/workflows/engine-tests.yml/badge.svg)](https://github.com/psraghothamrao8/RAD-SMART/actions/workflows/engine-tests.yml)
[![Sarvam AI](https://img.shields.io/badge/languages-Sarvam%20AI-F26B1D)](docs/evaluation/sarvam_evaluation.md)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Health-a-thon 2026 · Cancer track · Use case 04: Clinic Operations & Patient Flow. Team: Dr Akshay Dinesan, Manipal (team leader, doctor partner); Abhinand T M (technical lead); P S Raghotham Rao (lead engineer); Dr Shirley Lewis Salins and Dr Umesh Velu (doctor partners).

One radiotherapy machine treats 70–90 patients a day, and one patient in ten waits more than 109 minutes. RAD-SMART is an assistive, not diagnostic, operations layer for radiotherapy departments. It predicts each session's machine-minutes, gives each course a new-start slot and a standing slot in which hard rules cannot be broken, repairs the day live when a machine breaks down, stress-tests plans in a digital twin, and explains decisions and messages patients in their own language through Sarvam AI. A person approves every change: the doctor each course, a technologist or doctor each breakdown response.

On the department's own 55 recorded days, replayed, the long wait falls from **109 to 70 minutes (−35%)**, and patients treated more than an hour late from **22% to 6%**.

| | |
|---|---|
| **Try it live** | **https://radsmart.braveglacier-5f9807f7.uaenorth.azurecontainerapps.io/try/**: a guided tour of the whole pipeline in seven one-click steps, with synthetic patients and no password (or sign in as `care-doctor` or `care-staff`, password `radsmart2026`) |
| **Watch the demo** (5 min, narrated, recorded on the live server) | https://psraghothamrao8.github.io/RAD-SMART/#demo · [MP4](docs/media/RAD-SMART_demo.mp4) |
| **Final submission** | [Final presentation](docs/RAD-SMART_Final_Presentation.pptx) ([PDF](docs/RAD-SMART_Final_Presentation.pdf)) · [Two-page solution brief](docs/RAD-SMART_Solution_Brief.pptx) ([PDF](docs/RAD-SMART_Solution_Brief.pdf)) |
| **Website** | https://psraghothamrao8.github.io/RAD-SMART/ |
| **Read more** | [User guide and demo script](docs/RAD-SMART_User_Guide.pdf) · [research paper](docs/RAD-SMART_Research_Paper.pdf) (8 pages) · [impact analysis](docs/RAD-SMART_Impact_Analysis.pdf) · [technical guide](https://psraghothamrao8.github.io/RAD-SMART/tech/) and [the maths, worked through](https://psraghothamrao8.github.io/RAD-SMART/tech/maths.html) |
| **Earlier rounds** | Phase 2 submission: [PDF](docs/Phase2_Submission.pdf) · [DOCX](docs/Phase2_Submission.docx) · [template, PPTX](docs/RAD-SMART_Phase2_Submission.pptx). Round 1 pitch deck: [web](https://psraghothamrao8.github.io/RAD-SMART/deck/) · [PDF](docs/deck/RAD-SMART_Pitch_Deck.pdf) |

[![The RAD-SMART demo: a recording of the app in CARE](docs/media/demo_poster.jpg)](https://psraghothamrao8.github.io/RAD-SMART/#demo)

## What it does

**It runs inside CARE**, the Open Healthcare Network's open-source hospital information system, as a pair of plugins with a **RADSMART** button on the patient's visit page (`app/`, see [`app/README.md`](app/README.md)). CARE's own code is unchanged.

| Who | What they do in RAD-SMART |
|---|---|
| Doctor | Enters a course and the patient's preferred part of the day; approves its first day (before 17:00) and one standing daily time; asks for a plain-words explanation |
| Technologist | Runs the day board (arrived, in room, out) with a live queue: who to call next, who is late, taking a ready patient in out of turn with a one-tap reason, putting a patient first for an emergency; reports a breakdown and approves the re-plan; sends patients' messages |
| Reception | Checks patients in by scanning the QR code on their phone |
| Patient and family | One private phone page, no app and no login: today's time, changes, messages with voice notes, the check-in code, four reply buttons, a morning, afternoon or evening preference |
| Head of department | Insights: are long waits falling? |

**The patient's preferred time.** A patient can ask for the morning (08:30–12:00), afternoon or evening (to 21:00). A new patient often starts wherever there is room; as other courses finish, RAD-SMART looks for a free slot inside the preferred part of the day, on every remaining treatment day, that keeps every rule and the time kept for new starts, and offers it to staff. Staff ask the patient, and nothing changes until they approve.

**Patients come early and late.** The day board shows who to call next: the first patient in the plan's order who is here, so the machine never waits for someone who has not come. A technologist can take anyone in at any time. RAD-SMART asks why with one tap, reminds them of anything to check (bladder preparation, senior staff, a shared ABC unit or breast board), and records it, but never blocks them.

**Emergencies.** Staff can put any patient first today with a reason (an emergency, the doctor asks, the patient is unwell): once here they are first in the queue, and a breakdown never proposes sending them back. On New course, *Emergency start today* places the first fraction today in the first free time, using the time the engine keeps free every day for urgent starts, and marks it priority.

**Patients and Sarvam AI.** After each approval RAD-SMART drafts the patient's message in Kannada, Malayalam, Hindi or Konkani (Tulu speakers read Kannada script) with Sarvam Translate, and a voice note with Bulbul v3; a technologist opens it in WhatsApp and presses send. Sarvam-105B explains a proposed time in plain words. A translation that changes a time, or an explanation that invents one, is thrown away; without Sarvam everything works in English. In our evaluation ([`docs/evaluation/`](docs/evaluation/sarvam_evaluation.md)), 112 of 112 translations in four languages kept every time, and 20 of 20 explanations were accepted.

## Results

**The department's records.** 55 days, October–December 2024, 3,137 patient-days. The median wait from arrival to treatment is 34 minutes, but one patient in ten waits more than 109 minutes. 22% are treated more than an hour after their appointment, and only 29% within 15 minutes of it. Waits build through the day, from about 19 minutes for patients arriving before 10:00 to about 66 minutes after 19:00, and evening patients now come about 32 minutes early.

**With and without RAD-SMART.** The [impact analysis](docs/RAD-SMART_Impact_Analysis.pdf) keeps the two datasets apart.

| Dataset | 90th-percentile wait, without → with | Treated more than 1 hour late, without → with |
|---|---|---|
| Original: the department's 55 recorded days, re-planned in the twin | 108.6 → **70.4 min** (−35%) | 22.2% → **5.7%** |
| Simulated: 12 weeks of synthetic courses with standing slots | 81.6 → **49.3 min** (−40%) | 18.6% → **3.6%** |

The price, over the 12 weeks: the last patient finishes at about 00:07 instead of 21:55, one new start in five begins a little later (0.4 working days on average), and a time the patient asks for is kept less often.

**Stress tests.** 300 simulated days of 87 patients, 08:30 to 01:00 (10 more than the busiest recorded day), under the department's own rules (its answers of 21 September and 24 October 2026), in the twin calibrated on the records:

- Against the busiest recorded days (70–77 patients), the 90th-percentile wait falls from 130 to 76 minutes and the share treated more than an hour late from 27% to 6%; the share treated within ±15 minutes rises from 30% to 53%. The median stays about the same (36 against 38 minutes), because patients are asked to arrive 20 minutes early (45 for pelvic patients) to prepare. Evening waits no longer build up: about 36 minutes for morning and evening arrivals alike, against 19 and 66 in the records.
- The independent checker found all 8 hard rules met, including new starts by 17:00, MHRC patients on the 17:00 bus and public-transport patients home by 21:00.
- Breakdowns, re-planned under the department's downtime rules: after a 45-minute fault the median wait is 37 minutes instead of 53, nobody is sent home and 1 new start moves to the next day. After a 150-minute fault it is 39 instead of 104: one patient who had not left home is sent back (the fraction is added at the end of the course) and 2 new starts move to the next day. Each re-plan takes 10–14 seconds.
- Two-machine new-start planning around a TBI course keeps peak load at 98–99%, instead of 154% on one machine.

The pilot's primary KPI is a 90th-percentile wait at least 25% lower than the records' 109 minutes.

## Architecture and deployment

```mermaid
flowchart LR
  subgraph Users["Staff and patients, in any browser or phone"]
    S["CARE + RADSMART pages"]
    P["Patient's phone page"]
  end
  subgraph Azure["Microsoft Azure"]
    subgraph ACA["Container Apps: one Docker image"]
      N["nginx"] --> G["gunicorn: CARE (Django)<br/>+ care_radsmart plugin"]
      G --> E["Scheduling engine<br/>prediction · optimiser · twin"]
    end
    DB[("Azure Database<br/>for PostgreSQL")]
    J["Daily job:<br/>migrations, fresh demo day"]
    R["Container Registry"]
  end
  Sv["Sarvam AI<br/>Translate · Bulbul · 105B"]
  W["WhatsApp in real use<br/>Telegram in the demo"]
  S --> N
  P --> N
  G --> DB
  J --> DB
  R -. image .-> ACA
  G -- "message text only,<br/>no names or numbers" --> Sv
  G --> W
```

| Layer | Technology |
|---|---|
| Hospital system | [CARE](https://github.com/ohcnetwork/care) (Django, PostgreSQL) and [care_fe](https://github.com/ohcnetwork/care_fe) (React), at pinned versions |
| RAD-SMART backend | Django plugin `care_radsmart`: models, a role-checked REST API, the Sarvam layer, the patient page, the Telegram demo channel |
| RAD-SMART frontend | React and TypeScript plugin `care_radsmart_fe`, loaded by CARE through Module Federation |
| Engine | Python: gradient boosting (scikit-learn) for session minutes; mixed-integer optimisation (SciPy with HiGHS); a Monte Carlo digital twin; an independent rule checker |
| Language AI | Sarvam Translate, Bulbul v3 (voice) and Sarvam-105B (explanations), each output checked |
| Packaging | One Docker image built on CARE's production image, with nginx and gunicorn |
| Hosting | Azure Container Apps (HTTPS; one copy kept warm by day while judges try it, otherwise scale to zero), Azure Database for PostgreSQL with daily backups, Azure Container Registry, a daily Container Apps job |
| Operations | [`deploy/azure/deploy.sh`](deploy/azure/deploy.sh): one script creates, builds, migrates, deploys and checks everything |

**The live server** runs in demonstration mode: synthetic patients, one-click roles with no password, and a fresh day every morning at 05:30 IST. In real use, staff sign in to CARE with their own accounts and RAD-SMART checks the role at every step. Moving to the pilot is configuration, not new code: the same image runs with demonstration mode off, on the hospital's own server (Docker Compose, beside its CARE) or in an Indian Azure region. How it is hosted, and what each piece costs, is in [`deploy/azure/`](deploy/azure/README.md).

## Run it yourself

```bash
# the whole development environment: CARE at pinned versions, both plugins, synthetic data
bash workspace/restore.sh

# deploy to Azure (after az login, with the development environment running)
bash deploy/azure/deploy.sh all

# the plugin's 40 automated tests, inside the running CARE backend
docker exec care_radsmart_dev-backend-1 python manage.py test care_radsmart.tests

# the engine's quick checks, also run by GitHub on every push
cd poc && pip install -r requirements.txt && python -m unittest discover -s tests -v
```

New to Docker or Azure? [`deploy/HOSTING_GUIDE.md`](deploy/HOSTING_GUIDE.md) explains every command, from an empty PC to the live server.

Details: [`workspace/README.md`](workspace/README.md) (development), [`app/README.md`](app/README.md) (the plugins, roles and API), [`poc/README.md`](poc/README.md) (the engine and its experiments).

## Repository

| Path | What it is |
|---|---|
| `app/` | The application: a backend plugin (`care_radsmart`, Django) and a frontend plugin (`care_radsmart_fe`, React) for CARE. Setup, roles, permissions and the API are in [`app/README.md`](app/README.md) |
| `poc/` | The scheduling engine in Python, its experiments on synthetic patients and its tests; the digital twin is calibrated on aggregates of the department's records ([`poc/README.md`](poc/README.md)) |
| `deploy/` | The Docker image and `deploy.sh`, which runs RAD-SMART on Microsoft Azure with a cost guard ([`deploy/azure/README.md`](deploy/azure/README.md)); [`HOSTING_GUIDE.md`](deploy/HOSTING_GUIDE.md) explains every command |
| `workspace/` | Rebuilds the whole development environment from this repository: CARE at the pinned commits, both plugins, Docker and the synthetic data ([`workspace/README.md`](workspace/README.md)) |
| `docs/` | The website (`index.html`, served by GitHub Pages; plain HTML, edit it directly); the final presentation and brief; the Phase 2 submission, user guide, research paper, research report, impact analysis and Round 1 kit, each as PDF, DOCX and Markdown; the Round 1 deck and its slide sources (`deck/`); the Sarvam evaluation, its raw results and every translation with its back-translation for native speakers to rate (`evaluation/`); figures, their HTML sources and the demo video |
| `tools/` | The builders: `build_final.py` (the final presentation and brief, from the organisers' templates), `build_docs.py` (DOCX and PDF from Markdown), `build_deck.py` (the deck; needs Chrome), `evaluate_sarvam.py` (reruns the evaluation, fetching only missing results), `analyse_department_data.py` (the department's spreadsheet to aggregates) and `demo-video/` (drives the app in headless Chrome and records it; Remotion adds titles and captions) |
| `.github/workflows/` | GitHub Actions: the engine's tests on every push |

## Data and licence

The prototype's patients are synthetic. [`tools/analyse_department_data.py`](tools/analyse_department_data.py) summarises the department's anonymised spreadsheet into aggregates only ([`poc/data/department_profile.json`](poc/data/department_profile.json)); the spreadsheet itself is excluded by `.gitignore` and never committed.

MIT, the same licence as CARE: see [`LICENSE`](LICENSE).
