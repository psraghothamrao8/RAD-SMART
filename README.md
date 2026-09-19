# RAD-SMART: Health-a-thon 2026 entry

**Radiotherapy AI-assisted Dynamic Scheduling, Machine Allocation and Resource Tracking.** Cancer track, use case 04: Clinic Operations & Patient Flow. Doctor partner: Dr Akshay Dinesan, Manipal.

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
| `poc/` | Working proof of concept in Python on synthetic data (see `poc/README.md`) |
| `tools/build_docs.py` | Rebuilds the DOCX and PDF from the Markdown: `python tools/build_docs.py docs/<file>.md` |
| `docs/index.html` | Interactive results page (the Round 1 prototype link), served by GitHub Pages. Built from `docs/web/page_template.html` and the PoC output; `docs/web/rad-smart-prototype.html` is the same page for Claude artifacts |
| `docs/deck/` | Pitch deck: `RAD-SMART_Pitch_Deck.pdf`, the web version `index.html`, and the 14 slide sources in `src/` |
| `tools/build_deck.py` | Rebuilds the web deck and its PDF from `docs/deck/src/` (needs Google Chrome): `python tools/build_deck.py` |
| `tools/build_results_page.py` | Rebuilds both copies of the results page after a PoC run: `python tools/build_results_page.py` |

## Key dates

- **Round 1 submission closes 25 Sep 2026, 23:59.** Aim to submit by 23 Sep.
- Shortlisting runs 26 Sep – 3 Oct, the build sprint 5 Oct – 8 Nov, and the Top 30 are announced by 14 Nov.
- The grand finale is at IIT Bombay on 28 Nov 2026.

## Headline PoC results (synthetic, 300 simulated days)

- Median wait from arrival to the treatment room fell from 71 to 19 minutes, and the 90th percentile from 227 to 52 minutes.
- Patients treated within ±15 minutes of their time rose from 16% to 62%, with no extra overtime and no broken rules.
- After a 30-minute machine fault, the day is re-planned in about 4 seconds and the median wait is 19 minutes instead of 93.
- Two-machine new-start planning keeps peak load at 100% on both machines, instead of 156% on one.
