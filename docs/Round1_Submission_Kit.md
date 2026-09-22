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
| 4 | Dr Akshay reviews the answers below, and the report's Appendix B, which now records the department's answers of 21 Sep and the few items still open | Dr Akshay | 22 Sep |
| 5 | Team names are in section 2.3, report Section 9.5 and deck slides 1 and 14. Add a line on each member's background if the form asks | All | 22 Sep |
| 6 | Open the published deck (section 2.5) and download it as PDF | Tech team | 23 Sep |
| 7 | Optional: record the 3-minute video walkthrough (section 4) | Tech team + Dr Akshay | 23 Sep |
| 8 | Optional: paste the public results page link as the prototype link, and the code repository link if asked (section 2.6) | Tech lead | 23 Sep |
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

A radiotherapy machine treats 70–90 patients a day, and most of them come every weekday for 1–7 weeks. Our Versa HD runs from 08:30 until about 01:00 in three RTT shifts, with a ceiling of 90 patients a day. Radiation therapy technologists give out appointment times by hand, without knowing how many machine-minutes each patient needs. Too many patients are told to come at the same time and other hours sit under-used, so patients wait long and unpredictably every day of their course, often with a family member who has taken the day off. The department must also:

- finish new starts by 17:00;
- keep complex procedures (SBRT, SRT, TBI, CSI) inside 10:00–17:00, while senior staff are present;
- keep 13:30–14:00 for blood irradiation;
- share one breast board and one ABC unit with the CT simulator;
- treat MHRC patients in time for the 17:00 hospital bus;
- get public-transport patients home by 21:00;
- treat same-day urgent patients before 18:00;
- run TBI courses;
- recover from machine faults;
- prepare for a second machine arriving in early 2027.

Deciding how many new patients to start each day is also subjective today, and no workflow timestamps are recorded.

If we solve it, patients arrive close to their real treatment time and are told about delays before they leave home. RTTs stop juggling times by hand. Complex cases always get supervision. New starts are planned two days ahead from real machine load, and both machines are used evenly. Our prototype was tested under the department's own rules on a synthetic 87-patient day, simulated 300 times. It cut the median wait from arrival to treatment from 100 to 33 minutes, and the 90th-percentile wait from 173 to 62 minutes, including the 20- or 45-minute preparation time. Every hard rule held. The pilot target is at least a 40% lower median wait within 90 days.

**Short version**

Radiotherapy patients come daily for weeks, yet times are allocated by hand, without knowing each patient's machine-minutes. Patients wait long and unpredictably while staff juggle new starts by 17:00, supervised complex cases, the blood-irradiation slot, one breast board and one ABC unit shared with the CT simulator, the 17:00 MHRC bus, public-transport patients who must be home by 21:00, urgent patients, TBI and machine faults. Solving it gives patients predictable times, staff a plan they can trust, and the department balanced machines. Under the department's own rules, our prototype cut the median wait from 100 to 33 minutes on synthetic data. The pilot target is at least 40% lower in 90 days.

### 2.2 What you are building, and what you are building it with

**Full version**

RAD-SMART is an assistive operations layer between the patient list and the treatment machines. It has four AI parts, and a person approves everything:

1. **Predict.** A gradient-boosting model predicts each session's machine-minutes (expected and cautious P80) from operational tags: technique, fraction number, imaging, mobility and accessories. The department has no timestamps yet, so it starts from the department's own estimate table and learns once check-in and room timestamps are captured.
2. **Optimise.** A constraint-optimisation engine (OR-Tools CP-SAT; HiGHS MILP in our prototype) builds the evening-before plan for each machine. Hard rules cannot be broken, and an independent checker re-verifies them. They include new starts by 17:00, complex cases in 10:00–17:00, the blood slot, MHRC slots before the 17:00 bus, public transport home by 21:00, and accessory limits including CT-simulator bookings and reservations. When a delay, fault, no-show, imaging hold or urgent patient occurs, it re-plans the rest of the day in seconds under the department's downtime rules. It treats patients already waiting first and moves as few others as possible.
3. **Simulate.** A digital twin stress-tests every plan against late arrivals, overruns and faults. It also produces a three-week load forecast that plans around TBI courses, and two-day-ahead advice on how many new patients each machine can take, balanced by minutes rather than head-count.
4. **Explain and converse.** A copilot on Sarvam AI (Sarvam-105B with tool calling via LangGraph) explains every placement ("why was this patient moved?") and turns rule changes written in plain language into versioned, validated configuration. Bulbul, Saaras and Sarvam Translate send patients and caregivers their reporting time and live updates by WhatsApp, SMS or voice call in Kannada, Malayalam, Hindi or English, and understand spoken "I'm running late" replies. Tulu, which no Sarvam model covers yet, gets Kannada-script text with a voice note recorded by Tulu-speaking staff. The LLM never makes a scheduling decision.

It works with what the clinic already has (an Excel list, a photo of the paper register read by Sarvam Vision OCR, QR check-in and WhatsApp) and runs on a hospital server. The stack is Python, FastAPI, PostgreSQL and a tablet web app.

**Short version**

An assistive scheduling layer with four parts. Machine learning predicts each session's machine-minutes. A constraint optimiser (OR-Tools / HiGHS) builds and live-repairs the plan with hard rules guaranteed. A digital twin tests plans and forecasts new-start capacity two days ahead. A Sarvam AI copilot explains decisions, edits rules from plain language and messages patients by WhatsApp, SMS or voice in their language, with recorded voice notes for Tulu. A senior RTT or oncologist approves every change. It works from Excel, paper (OCR) and QR check-in, on an on-premise server.

### 2.3 Why yours is the right team to build it

**Full version**

- **The problem owner is on the team.** Dr Akshay Dinesan (Manipal) wrote the problem statement from daily experience in a working radiotherapy department that runs a Versa HD and is adding a second machine in early 2027. The department has already answered our detailed questions on its rules, from the MHRC bus to accessory reservations and downtime, and they are built into the prototype. Dr Akshay has a path to a real pilot and the RTT team who will use it.
- **We have already built it.** In the Round 1 window we built a working prototype. It generates realistic synthetic departments under the department's own rules. It predicts session durations and solves an 87-patient day to a proven optimum in about 20 seconds. It re-plans machine faults in 4–26 seconds under the department's downtime rules, and forecasts new-start capacity for two machines around a TBI course. We tested it over 300 simulated days against a model of current practice.
- **Doctors and engineers together.** Dr Akshay Dinesan leads the team. Abhinand T M is the technical lead, with P S Raghotham Rao on the build. Dr Shirley Lewis Salins and Dr Umesh Velu complete the team, so three of the five members are doctors. Together we cover operations research, machine learning, Indian-language AI, product building and clinical practice.
- **We designed for the guardrails from day one.** The system is assistive, not diagnostic: human approval, audit trail, synthetic data only, no clinical inputs, and no personal identifiers sent to AI models.

**Short version**

Dr Akshay Dinesan owns the problem in a working radiotherapy department (a Versa HD, with a second machine arriving in early 2027), has given us the department's rules, and can take it to a real pilot. Dr Akshay leads a five-member team: Abhinand T M (technical lead), P S Raghotham Rao, Dr Shirley Lewis Salins and Dr Umesh Velu. Together they cover optimisation, machine learning, Indian-language AI, full-stack development and clinical practice. It has already built a working prototype that plans an 87-patient day under the department's rules, re-plans machine faults in seconds, and was tested over 300 simulated days.

### 2.4 Does any part of it already exist?

**Full version**

Some pieces exist separately. None is a solution to this problem in an Indian department.

- **Oncology information systems** (for example MOSAIQ and ARIA) hold appointment calendars and record treatment times. As far as we know, they do not build a minute-level plan from predicted durations with guaranteed operational rules, re-plan live, balance a mixed-vendor fleet, or message patients in Indian languages. A department adding a second machine, possibly from another vendor, needs a vendor-neutral layer.
- **Academic research** shows that optimisation works for radiotherapy scheduling. A MILP scheduler implemented in two Dutch centres cut schedule preparation from 1.5 days to minutes, and automated scheduling at a Belgian centre reduced waits for treatment start by 80%. These systems mostly decide the start *day* in large, fully digital European centres, and are not products Indian departments can adopt.
- **Duration-prediction models** have been published, but they are not connected to live scheduling and patient communication.
- **We reuse open components:** OR-Tools and HiGHS (optimisation), scikit-learn (ML), Sarvam AI APIs (language, speech, OCR) and LangGraph (tool orchestration).
- **What we built ourselves (September 2026):** the prototype scheduling engine, duration model, simulator and capacity forecaster, all running on synthetic data. What is new is combining prediction, guaranteed optimisation, simulation and multilingual communication in one light-integration, human-approved workflow.

**Short version**

OIS calendars (MOSAIQ, ARIA) and academic schedulers exist. The academic ones mostly choose start days in large European centres. Neither builds a minute-level, rule-guaranteed daily plan with live re-planning and multilingual patient messaging for a mixed-vendor Indian department. We reuse OR-Tools, HiGHS, scikit-learn, Sarvam AI and LangGraph. The scheduling engine, duration model, simulator and forecaster are our own prototype, built in September 2026 on synthetic data.

### 2.5 Deck

The 14-slide deck is built and published at https://claude.ai/artifact/LhSJi3g5j23xLHxTRYiSgw (section 3 lists the slides). Before uploading:

1. Check the names on slides 1 and 14.
2. Download the deck as PDF from the page, and upload the PDF.

The link is private to its owner. Share it from the page's Share menu before anyone else, such as Dr Akshay, can open it.

A copy is also on GitHub: the PDF at `docs/deck/RAD-SMART_Pitch_Deck.pdf` and a public web version at https://psraghothamrao8.github.io/RAD-SMART/deck/. After editing the deck, copy the changed slides into `docs/deck/src/` and run `python tools/build_deck.py` to update both.

### 2.6 Optional items

- **Supporting document:** `docs/RAD-SMART_Research_Report.pdf`, the full research report and implementation plan (36 pages).
- **Prototype link:** the interactive results page at https://psraghothamrao8.github.io/RAD-SMART/, hosted on GitHub Pages and open to anyone. It shows the wait curves, the optimised day with a reason for every session, the trade-off of holding capacity for urgent starts, both downtime re-plans and the two-machine forecast with TBI, all from the PoC on synthetic data. After re-running the PoC, run `python tools/build_results_page.py`, commit and push; the page updates within a few minutes.
- **Code:** https://github.com/psraghothamrao8/RAD-SMART (public). It holds the PoC, the documents and the page source. Everything in it is synthetic data only.
- **Video walkthrough:** the script is in section 4.

---

## 3. Deck outline (14 slides, published)

Each slide makes one point with large numbers, uses the figures from `docs/figures/`, and carries the footer "Assistive, not diagnostic · synthetic data". The deck has four sections: the problem, the solution, the evidence and the plan.

| # | Slide title | Key message | Visual |
|---|---|---|---|
| 1 | RAD-SMART | The right patient, on the right machine, at a predictable time | Title; doctor partner and team; Cancer track, use case 04 |
| 2 | Every weekday, 80 patients wait for one machine | Daily treatment for weeks; hand-allocated times; unpredictable waits. India: about 0.6 machines per million people, and 69% of centres have one machine | Big numbers and a strip of one day's sessions |
| 3 | Allocation under hard rules and soft priorities | Hard rules (new starts by 17:00, 10:00–17:00 complex window, blood slot, one breast board and one ABC, MHRC bus, public transport by 21:00, urgent by 18:00) versus soft priorities (paying patients' times, older patients, flexible patients in the evening) | Two rule cards |
| 4 | We compared five ways to build it | Rules, LLM-only, static optimisation, deep RL, hybrid. The hybrid wins at 4.85/5 | Decision table |
| 5 | How RAD-SMART works | Predict, optimise, simulate, explain, with people approving every step | Architecture diagram |
| 6 | Automation proposes; people decide | Two days ahead, evening before, during the day, after the day | Four-step daily loop |
| 7 | AI where each technique is strongest | ML for minutes; the optimiser guarantees rules; the twin tests; the Sarvam copilot explains and speaks Kannada, Malayalam, Hindi and English, with recorded Tulu voice notes | Four tiles; Sarvam components |
| 8 | One optimised day, with every rule held | 87 patients from 08:30 to 00:45, all 7 hard rules re-checked, a reason for every placement | `fig3` day Gantt |
| 9 | Waits fall by two-thirds | Median wait 100 → 33 min; 90th percentile 173 → 62 min; within ±15 min 10% → 73%; the department chooses how much to hold for urgent starts | `fig1` wait curves + KPI numbers |
| 10 | It recovers when the machine fails, by the department's rules | 45-min fault: everyone treated today, median wait 144 → 40 min. 150-min fault: new starts to the next day, median wait 216 → 35 min | `fig4b` waiting room |
| 11 | New starts balanced by minutes, not head-count | Two machines and a TBI week: peak load 154% → 98%; TBI days fitted exactly | `fig5` capacity forecast |
| 12 | Safe by design | A senior RTT or oncologist approves every plan; one-tap override, audit trail; no clinical inputs; no identifiers to AI; DPDP-aligned; works from Excel, paper and WhatsApp | Guardrail checklist |
| 13 | 90 days on the Versa HD, one primary KPI | Baseline 2 weeks, shadow 3 weeks, live 8 weeks. Primary KPI: median wait (target −40%). About ₹2–3 lakh | Timeline + success criteria |
| 14 | From prototype to pilot | Team; roadmap to the finale and the pilot. Ask: pilot support, Sarvam credits, NCG introductions | Team, roadmap and ask cards |

---

## 4. Video walkthrough script (3 minutes)

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Dr Akshay on camera (or an illustration of a waiting area) | "Every weekday, about eighty people come to our radiotherapy machine, many for six or seven weeks. They all have appointments, and many still wait for hours, because times are given by hand, without knowing how long each treatment will take." |
| 0:20–0:45 | The constraint table | "It isn't simple booking. New patients must finish by five. Complex treatments need senior staff. There's a blood-irradiation slot, one breast board and one breathing-control unit shared with the CT simulator, a hospital bus at five, patients who must catch their bus home by nine, urgent patients, and machine faults. Soon there'll be a second machine." |
| 0:45–1:15 | Architecture figure, highlighting each layer | "RAD-SMART is an assistive operations layer. Machine learning predicts each patient's machine-minutes. An optimiser builds the day's plan, and hard rules can't be broken. A digital twin tests the plan. A copilot on Sarvam AI explains every decision and messages patients in their own language." |
| 1:15–1:45 | Optimised-day Gantt, then the wait chart | "On a synthetic eighty-seven-patient day under our department's own rules, simulated three hundred times, the median wait fell from 100 minutes to 33, and every hard rule held." |
| 1:45–2:10 | Fault chart; phone mock-up receiving a message in Kannada | "When the machine fails, RAD-SMART re-plans the rest of the day in seconds, following our department's downtime rules. Patients already waiting go first. It moves as few people as possible and tells only those who can still act, by WhatsApp, SMS or a voice call, even in Tulu." |
| 2:10–2:30 | Forecast chart | "Two days ahead, it advises how many new patients each machine can start, balanced by minutes, not head-count, and it plans around total body irradiation. That keeps both machines at capacity instead of overloading one." |
| 2:30–2:50 | Guardrails slide | "It is assistive, not diagnostic. It never decides treatment. A senior technologist or oncologist approves every plan with one tap, every change is logged, and no personal data goes to the AI models." |
| 2:50–3:00 | Pilot timeline and team | "Our 90-day pilot targets a forty-percent shorter wait. RAD-SMART: the right patient, on the right machine, at a predictable time." |

---

## 5. Likely jury questions

**Isn't this clinical decision support?**
No. RAD-SMART decides only *when* and *on which machine* a session happens. Urgency, technique and machine eligibility are entered by clinicians and physicists, and it reads no diagnoses, doses, images or notes. Its only prediction is how many minutes a session will take.

**Why not just ask an LLM to make the schedule?**
An LLM cannot guarantee rules such as "no new start after 17:00", is weak at packing minutes, and can give different answers to the same input. We use the LLM for what it is good at, which is explaining, editing rules and talking to patients in their language. A solver produces the plan.

**What if patients don't have smartphones or can't read?**
Voice calls in their language (Sarvam Bulbul), plain SMS, and a copy to a caregiver. Reception staff can still print the list. The simulation already assumes 15% of patients do not act on updates.

**Where do treatment durations come from if you don't have OIS data?**
The department records no timestamps today, so we start from its own estimate table. The prototype shows that averages alone deliver most of the benefit (100 → 35 minutes). QR check-in and a tablet tap at room entry and exit then collect real durations, and the model learns weekly.

**Is prioritising paying patients fair?**
The department asked for paying patients to get their preferred time as far as possible. Every priority is an explicit, visible weight that the department sets, and the MHRC bus and public-transport limits are hard rules. The dashboard reports waits by group (elderly, transport-dependent, language, paying versus non-paying), and any group getting worse is flagged for review.

**Your patients speak Tulu. Does Sarvam support it?**
Not yet. Sarvam's speech models cover 11 languages (Bulbul v3) and the 22 scheduled languages plus English (Saaras v3), and Tulu is not among them. Tulu speakers get the text in Kannada script, which is how Tulu is usually written, with a short voice note recorded by Tulu-speaking staff for each approved template. If a Tulu model appears, it replaces the recordings.

**Why does the day end later with RAD-SMART?**
Because the plan holds 40 minutes for same-day urgent starts and imaging re-treatments. That keeps waits short, but the last patient finishes at 00:53 instead of 00:29. Holding nothing ends the day at 00:17, earlier than today, with a 43-minute median wait. It is one setting, and the department chooses.

**What happens when the internet or WhatsApp is down?**
Planning runs on the hospital server over the LAN. Messages fall back to SMS or a voice call, and a printed list is always available.

**How is this different from the scheduling module in MOSAIQ or ARIA?**
Those are calendars that record appointments. RAD-SMART computes the plan from predicted minutes and rules, repairs it live, forecasts new-start capacity, and speaks Indian languages. It is vendor-neutral, which matters for a department running Elekta and Varian machines side by side.

**How will you prove it works?**
Two weeks of timestamp capture and baseline measurement (the department records none today), three weeks of shadow mode, then eight weeks live on one machine. We will report daily median wait as an interrupted time series, alongside balancing measures (throughput, overtime, equity, override rate).
