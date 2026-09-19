# RAD-SMART: Round 1 Submission Kit

Health-a-thon 2026 · Cancer track · Use case 04: Clinic Operations & Patient Flow

> **Deadline: Thursday 25 September 2026, 23:59.** There is no late lane, and a draft that is never submitted is not judged. Any team member can edit and submit, and the last version saved before the deadline is the one evaluated. **Aim to submit by Wednesday 23 September**, then keep improving until the deadline.

This kit contains ready-to-paste answers for the five Round 1 sections, the outline of our 14-slide deck, a 3-minute video script, likely jury questions, and a checklist. The deck and an interactive results page are already built and published (sections 2.5 and 2.6). Each answer comes in a **full version** and a **short version** in case the form limits length. Replace the text in [square brackets] before submitting.

---

## 1. Checklist

| # | Task | Owner | By |
|---|---|---|---|
| 1 | Confirm Dr Akshay's registration shows the **Cancer** track and the right solution focus. Round 1 reads these from the doctor's registration | Dr Akshay | 21 Sep |
| 2 | Confirm the team (2–5 members, one practising doctor, one technical lead) is formed on the platform | Tech lead | 21 Sep |
| 3 | On the entry, set the use case to **Clinic Operations & Patient Flow** (it is the one field the team may adjust) | Tech lead | 21 Sep |
| 4 | Dr Akshay reviews the answers below and the open questions in the report (Appendix B) | Dr Akshay | 22 Sep |
| 5 | Fill in team names and bios (section 2.3 below and report Section 9.5) | All | 22 Sep |
| 6 | Open the published deck (section 2.5), replace [names] on slides 1 and 14, and download it as PDF | Tech team | 23 Sep |
| 7 | Optional: record the 3-minute video walkthrough (section 4) | Tech team + Dr Akshay | 23 Sep |
| 8 | Optional: share the published results page from its Share menu and paste its link as the prototype link (section 2.6) | Tech lead | 23 Sep |
| 9 | Optional: attach the supporting document `RAD-SMART_Research_Report.pdf` | Tech lead | 23 Sep |
| 10 | Paste the answers, upload the files and **submit** | Tech lead | **23 Sep** |
| 11 | Final proofread; check who last edited the entry; re-save if needed | All | 25 Sep, before 23:59 |

**Rules to double-check before submitting:**
- Use only synthetic data. No real patient data may appear in the deck, the video or the repository.
- Keep to "assistive, not diagnostic" wording throughout, with human override and an audit trail.
- One entry per team.

---

## 2. Answers to the five Round 1 sections

### 2.1 The exact problem you are solving, and what changes if you solve it

**Full version**

A radiotherapy machine treats 70–90 patients a day, and most of them come every weekday for 1–7 weeks. In our department, radiation therapy technologists give out appointment times by hand, without knowing how many machine-minutes each patient needs. Too many patients are told to come at the same time and other hours sit under-used, so patients wait long and unpredictably every day of their course, often with a family member who has taken the day off. The department must also fit new starts before 5 PM, complex procedures (SBRT, SRT, TBI, CSI) while senior staff are present, a fixed blood-irradiation slot, breast boards and ABC devices shared with the CT simulator, same-day urgent palliative patients, machine faults, and soon a second machine with different capabilities (Versa HD and Halcyon). Deciding how many new patients to start each day is also subjective today.

If we solve it, patients arrive close to their real treatment time and are told about delays before they leave home. RTTs stop juggling times by hand. Complex cases always get supervision. New starts are planned two days ahead from real machine load, and both machines are used evenly. On a synthetic 67-patient day simulated 300 times, our prototype cut the median wait from arrival to treatment from 71 to 19 minutes and the 90th-percentile wait from 227 to 52 minutes, with no extra overtime and no broken rules. The pilot target is at least a 40% lower median wait within 90 days.

**Short version**

Radiotherapy patients come daily for weeks, yet times are allocated by hand, without knowing each patient's machine-minutes. Patients wait long and unpredictably while staff juggle new starts before 5 PM, supervised complex cases, a blood-irradiation slot, shared accessories, urgent patients and machine faults. Solving it gives patients predictable times, staff a plan they can trust, and the department balanced machines. Our prototype cut the median wait from 71 to 19 minutes on synthetic data. The pilot target is at least 40% lower in 90 days.

### 2.2 What you are building, and what you are building it with

**Full version**

RAD-SMART is an assistive operations layer between the patient list and the treatment machines. It has four AI parts, and a person approves everything:

1. **Predict.** A quantile gradient-boosting model predicts each session's machine-minutes (typical P50 and cautious P80) from operational tags: technique, fraction number, imaging, mobility and accessories. It starts from the department's average tables and learns from daily timestamps.
2. **Optimise.** A constraint-optimisation engine (OR-Tools CP-SAT; HiGHS MILP in our prototype) builds the evening-before plan for each machine. Hard rules cannot be broken: new starts before 5 PM, complex cases in the senior-staff window, the blood slot, accessory limits including CT-simulator bookings. When a delay, fault, no-show or urgent patient occurs, it re-plans the rest of the day in seconds while moving as few patients as possible.
3. **Simulate.** A digital twin stress-tests every plan against late arrivals, overruns and faults. It also produces a three-week load forecast and two-day-ahead advice on how many new patients each machine can take, balanced by minutes rather than head-count.
4. **Explain and converse.** A copilot on Sarvam AI (Sarvam-105B with tool calling via LangGraph) explains every placement ("why was this patient moved?") and turns rule changes written in plain language into versioned, validated configuration. Bulbul, Saaras and Sarvam Translate send patients and caregivers their time and live updates by WhatsApp, SMS or voice call in their own language, and understand spoken "I'm running late" replies. The LLM never makes a scheduling decision.

It works with what the clinic already has (an Excel list, a photo of the paper register read by Sarvam Vision OCR, QR check-in and WhatsApp) and runs on a hospital server. The stack is Python, FastAPI, PostgreSQL and a tablet web app.

**Short version**

An assistive scheduling layer with four parts. Machine learning predicts each session's machine-minutes. A constraint optimiser (OR-Tools / HiGHS) builds and live-repairs the plan with hard rules guaranteed. A digital twin tests plans and forecasts new-start capacity two days ahead. A Sarvam AI copilot explains decisions, edits rules from plain language and messages patients by WhatsApp, SMS or voice in their language. RTTs approve every change. It works from Excel, paper (OCR) and QR check-in, on an on-premise server.

### 2.3 Why yours is the right team to build it

**Full version**

- **The problem owner is on the team.** Dr Akshay Dinesan (Manipal) wrote the problem statement from daily experience in a working radiotherapy department that runs a Versa HD and is adding a Halcyon. Dr Akshay can validate every rule and has a path to a real pilot and the RTT team who will use it.
- **We have already built it.** In the Round 1 window we built a working prototype. It generates realistic synthetic departments, predicts session durations, solves a 67-patient day to a proven optimum in 2–8 seconds, re-plans a machine fault in about 4 seconds, and forecasts new-start capacity for two machines. We tested it over 300 simulated days against a model of current practice.
- **Skills match the architecture.** [Tech lead name]: [e.g. software engineering / ML background]. [Member 2]: [optimisation / data]. [Member 3]: [full-stack / mobile / messaging]. Together we cover operations research, machine learning, Indian-language AI and product building.
- **We designed for the guardrails from day one.** The system is assistive, not diagnostic: human approval, audit trail, synthetic data only, no clinical inputs, and no personal identifiers sent to AI models.

**Short version**

Dr Akshay Dinesan owns the problem in a working radiotherapy department (Versa HD, adding Halcyon) and can take it to a real pilot. The tech team [names] covers optimisation, machine learning, Indian-language AI and full-stack development. It has already built a working prototype that plans a 67-patient day with guaranteed rules, re-plans a machine fault in about 4 seconds, and was tested over 300 simulated days.

### 2.4 Does any part of it already exist?

**Full version**

Some pieces exist separately. None is a solution to this problem in an Indian department.

- **Oncology information systems** (for example MOSAIQ and ARIA) hold appointment calendars and record treatment times. As far as we know, they do not build a minute-level plan from predicted durations with guaranteed operational rules, re-plan live, balance a mixed-vendor fleet, or message patients in Indian languages. A department with an Elekta Versa HD and a Varian Halcyon needs a vendor-neutral layer.
- **Academic research** shows that optimisation works for radiotherapy scheduling. A MILP scheduler implemented in two Dutch centres cut schedule preparation from 1.5 days to minutes, and automated scheduling at a Belgian centre reduced waits for treatment start by 80%. These systems mostly decide the start *day* in large, fully digital European centres, and are not products Indian departments can adopt.
- **Duration-prediction models** have been published, but they are not connected to live scheduling and patient communication.
- **We reuse open components:** OR-Tools and HiGHS (optimisation), scikit-learn (ML), Sarvam AI APIs (language, speech, OCR) and LangGraph (tool orchestration).
- **What we built ourselves (September 2026):** the prototype scheduling engine, duration model, simulator and capacity forecaster, all running on synthetic data. What is new is combining prediction, guaranteed optimisation, simulation and multilingual communication in one light-integration, human-approved workflow.

**Short version**

OIS calendars (MOSAIQ, ARIA) and academic schedulers exist. The academic ones mostly choose start days in large European centres. Neither builds a minute-level, rule-guaranteed daily plan with live re-planning and multilingual patient messaging for a mixed-vendor Indian department. We reuse OR-Tools, HiGHS, scikit-learn, Sarvam AI and LangGraph. The scheduling engine, duration model, simulator and forecaster are our own prototype, built in September 2026 on synthetic data.

### 2.5 Deck

The 14-slide deck is built and published at https://claude.ai/artifact/LhSJi3g5j23xLHxTRYiSgw (section 3 lists the slides). Before uploading:

1. Replace [names] on slide 1 and the team placeholders on slide 14.
2. Download the deck as PDF from the page, and upload the PDF.

The link is private to its owner. Share it from the page's Share menu before anyone else, such as Dr Akshay, can open it.

### 2.6 Optional items

- **Supporting document:** `docs/RAD-SMART_Research_Report.pdf`, the full research report and implementation plan (27 pages).
- **Prototype link:** the interactive results page at https://claude.ai/artifact/MiqA2wgSu8FcHJ4e5276eZ. It shows the wait curves, the optimised day with a reason for every session, the fault re-plan and the two-machine forecast, all from the PoC on synthetic data. The page is private until shared: open its Share menu and allow anyone with the link to view it, then paste the link. To rebuild it after re-running the PoC, run `python tools/build_results_page.py`, which writes `docs/web/rad-smart-prototype.html`.
- **Code (optional):** a repository containing the `poc/` folder, which is synthetic data only and safe to share. It could be on GitHub, public or shared with the organisers.
- **Video walkthrough:** the script is in section 4.

---

## 3. Deck outline (14 slides, published)

Each slide makes one point with large numbers, uses the figures from `docs/figures/`, and carries the footer "Assistive, not diagnostic · synthetic data". The deck has four sections: the problem, the solution, the evidence and the plan.

| # | Slide title | Key message | Visual |
|---|---|---|---|
| 1 | RAD-SMART | The right patient, on the right machine, at a predictable time | Title; doctor partner and team; Cancer track, use case 04 |
| 2 | Every weekday, 80 patients wait for one machine | Daily treatment for weeks; hand-allocated times; unpredictable waits. India: about 0.6 machines per million people, and 69% of centres have one machine | Big numbers and a strip of one day's sessions |
| 3 | Allocation under hard rules and soft priorities | Hard rules (5 PM new starts, senior-staff window, blood slot, shared accessories) versus soft priorities (elderly, transport, inpatients) | Two rule cards |
| 4 | We compared five ways to build it | Rules, LLM-only, static optimisation, deep RL, hybrid. The hybrid wins at 4.85/5 | Decision table |
| 5 | How RAD-SMART works | Predict, optimise, simulate, explain, with people approving every step | Architecture diagram |
| 6 | Automation proposes; people decide | Two days ahead, evening before, during the day, after the day | Four-step daily loop |
| 7 | AI where each technique is strongest | ML for minutes; the optimiser guarantees rules; the twin tests; the Sarvam copilot explains and speaks 10+ languages | Four tiles; Sarvam components |
| 8 | One optimised day, with every rule held | 67 patients, proven optimum in seconds, a reason for every placement | `fig3` day Gantt |
| 9 | Waits fall by about three-quarters | Median wait 71 → 19 min; 90th percentile 227 → 52 min; within ±15 min 16% → 62%; no extra overtime | `fig1` wait curves + KPI numbers |
| 10 | It recovers when the machine fails | 30-min fault: re-planned in 4 s, 17 patients messaged, median wait 93 → 19 min | `fig4b` waiting room |
| 11 | New starts balanced by minutes, not head-count | Two machines: peak load 156% → 100% | `fig5` capacity forecast |
| 12 | Safe by design | Human approval, one-tap override, audit trail; no clinical inputs; no identifiers to AI; DPDP-aligned; works from Excel, paper and WhatsApp | Guardrail checklist |
| 13 | 90 days on the Versa HD, one primary KPI | Baseline 2 weeks, shadow 3 weeks, live 8 weeks. Primary KPI: median wait (target −40%). About ₹2–3 lakh | Timeline + success criteria |
| 14 | From prototype to pilot | Team; roadmap to the finale and the pilot. Ask: pilot support, Sarvam credits, NCG introductions | Team, roadmap and ask cards |

---

## 4. Video walkthrough script (3 minutes)

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Dr Akshay on camera (or an illustration of a waiting area) | "Every weekday, about eighty people come to our radiotherapy machine, many for six or seven weeks. They all have appointments, and many still wait for hours, because times are given by hand, without knowing how long each treatment will take." |
| 0:20–0:45 | The constraint table | "It isn't simple booking. New patients must finish before five. Complex treatments need senior staff. There's a blood-irradiation slot, accessories shared with the CT simulator, urgent patients, and machine faults. Soon there'll be a second machine." |
| 0:45–1:15 | Architecture figure, highlighting each layer | "RAD-SMART is an assistive operations layer. Machine learning predicts each patient's machine-minutes. An optimiser builds the day's plan, and hard rules can't be broken. A digital twin tests the plan. A copilot on Sarvam AI explains every decision and messages patients in their own language." |
| 1:15–1:45 | Optimised-day Gantt, then the wait chart | "On a synthetic 67-patient day, simulated three hundred times, the median wait fell from seventy-one minutes to nineteen, with no extra overtime, and every new start finished before five." |
| 1:45–2:10 | Fault chart; phone mock-up receiving a message in Kannada | "When the machine fails for thirty minutes, RAD-SMART re-plans the rest of the day in about four seconds. It moves as few people as possible and tells only those who can still act, by WhatsApp, SMS or a voice call." |
| 2:10–2:30 | Forecast chart | "Two days ahead, it advises how many new patients each machine can start, balanced by minutes, not head-count. That keeps both machines at capacity instead of overloading one." |
| 2:30–2:50 | Guardrails slide | "It is assistive, not diagnostic. It never decides treatment. Technologists approve every plan with one tap, every change is logged, and no personal data goes to the AI models." |
| 2:50–3:00 | Pilot timeline and team | "Our 90-day pilot targets a forty-percent shorter wait. RAD-SMART: the right patient, on the right machine, at a predictable time." |

---

## 5. Likely jury questions

**Isn't this clinical decision support?**
No. RAD-SMART decides only *when* and *on which machine* a session happens. Urgency, technique and machine eligibility are entered by clinicians and physicists, and it reads no diagnoses, doses, images or notes. Its only prediction is how many minutes a session will take.

**Why not just ask an LLM to make the schedule?**
An LLM cannot guarantee rules such as "no new start after 5 PM", is weak at packing minutes, and can give different answers to the same input. We use the LLM for what it is good at, which is explaining, editing rules and talking to patients in their language. A solver produces the plan.

**What if patients don't have smartphones or can't read?**
Voice calls in their language (Sarvam Bulbul), plain SMS, and a copy to a caregiver. Reception staff can still print the list. The simulation already assumes 15% of patients do not act on updates.

**Where do treatment durations come from if you don't have OIS data?**
At first, the department's own average table. The prototype shows that averages alone deliver most of the benefit (71 → 22 minutes). QR check-in and a tablet tap at room entry and exit then collect real durations, and the model learns weekly.

**Is prioritising paying patients fair?**
Every priority is an explicit, visible weight that the department sets, and transport constraints are hard rules. The dashboard reports waits by group (elderly, transport-dependent, language, paying versus non-paying), and any group getting worse is flagged for review.

**What happens when the internet or WhatsApp is down?**
Planning runs on the hospital server over the LAN. Messages fall back to SMS or a voice call, and a printed list is always available.

**How is this different from the scheduling module in MOSAIQ or ARIA?**
Those are calendars that record appointments. RAD-SMART computes the plan from predicted minutes and rules, repairs it live, forecasts new-start capacity, and speaks Indian languages. It is vendor-neutral, which matters for a department running Elekta and Varian machines side by side.

**How will you prove it works?**
Two weeks of baseline measurement, three weeks of shadow mode, then eight weeks live on one machine. We will report daily median wait as an interrupted time series, alongside balancing measures (throughput, overtime, equity, override rate).
