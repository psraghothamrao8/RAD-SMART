# RAD-SMART: Round 1 Submission Kit

Health-a-thon 2026 · Cancer track · Use case 04: Clinic Operations & Patient Flow

> **Deadline: Thursday 25 September 2026, 23:59.** There is no late lane, and a draft that is never submitted is not judged. Any team member can edit and submit, and the last version saved before the deadline is the one evaluated. **Aim to submit by Wednesday 23 September**, then keep improving until the deadline.

> **Updated 24 October 2026, for the build sprint.** We were shortlisted. On 24 October the department described its roles, standing slots, breakdown rules and the screens it needs, and we built them into the engine and into a working application inside CARE, the Open Healthcare Network's hospital information system (`app/`, report Section 6.10). A separate impact analysis compares each dataset with and without RAD-SMART (`docs/RAD-SMART_Impact_Analysis.pdf`): on the department's own 55 days the 90th-percentile wait falls from 108.6 to 70.4 minutes (−35%), and over 12 synthetic weeks with standing slots from 82 to 49 minutes (−40%). The answers below are as submitted for Round 1, with figures that have since changed updated; the deck now has 9 slides, and a short research paper (`docs/RAD-SMART_Research_Paper.pdf`) sums up the method and results.

This kit contains ready-to-paste answers for the five Round 1 sections, the outline of our deck, a 3-minute video script, likely jury questions, and a checklist. The deck and the project website are already built and published (sections 2.5 and 2.6). Each answer comes in a **full version** and a **short version** in case the form limits length. Replace the text in [square brackets] before submitting.

---

## 1. Checklist

| # | Task | Owner | By |
|---|---|---|---|
| 1 | Confirm Dr Akshay's registration shows the **Cancer** track and the right solution focus. Round 1 reads these from the doctor's registration | Dr Akshay | 21 Sep |
| 2 | Confirm the team (2–5 members, one practising doctor, one technical lead) is formed on the platform | Tech lead | 21 Sep |
| 3 | On the entry, set the use case to **Clinic Operations & Patient Flow** (it is the one field the team may adjust) | Tech lead | 21 Sep |
| 4 | Dr Akshay reviews the answers below, and the report's Appendix B, which now records the department's answers of 21 Sep and the few items still open | Dr Akshay | 22 Sep |
| 5 | Dr Akshay confirms with the head of department that aggregates of the anonymised arrival and treatment records (medians, percentages, hourly profiles) may appear in the deck, report and public page. The spreadsheet itself is never shared or committed | Dr Akshay | 23 Sep |
| 6 | Team names and roles are on deck slide 1, in section 2.3 and in report Section 9.5. Add a line on each member's background if the form asks | All | 24 Sep |
| 7 | Open the published deck (section 2.5) and download it as PDF | Tech team | 23 Sep |
| 8 | Optional: record the 3-minute video walkthrough (section 4) | Tech team + Dr Akshay | 23 Sep |
| 9 | Optional: paste the website link as the prototype link, and the code repository link if asked (section 2.6) | Tech lead | 23 Sep |
| 10 | Optional: attach the supporting document `RAD-SMART_Research_Report.pdf` | Tech lead | 23 Sep |
| 11 | Paste the answers, upload the files and **submit** | Tech lead | **23 Sep** |
| 12 | Final proofread; check who last edited the entry; re-save if needed | All | 25 Sep, before 23:59 |

**Rules to double-check before submitting:**
- Use only fake or fully anonymised data: no patient data on the platform, with mentors or in demos. The prototype's patients are synthetic, and the department's anonymised records appear only as aggregates (medians, percentages, hourly profiles). The spreadsheet stays out of the deck, the video and the repository.
- Keep to "assistive, not diagnostic" wording throughout, with human override and an audit trail.
- One entry per team.

---

## 2. Answers to the five Round 1 sections

### 2.1 The exact problem you are solving, and what changes if you solve it

**Full version**

A radiotherapy machine treats 70–90 patients a day, and most of them come every weekday for 1–7 weeks. Our Versa HD runs from 08:30 until about 01:00 in three RTT shifts, with a ceiling of 90 patients a day. Radiation therapy technologists give out appointment times by hand, without knowing how many machine-minutes each patient needs. Too many patients are told to come at the same time and other hours sit under-used, so patients wait long and unpredictably every day of their course, often with a family member who has taken the day off.

The department's own records (55 days, October–December 2024, 3,137 patient-days) show the result. One patient in ten waits more than 109 minutes from arrival to treatment, 22% are treated more than an hour after their appointment and only 29% within 15 minutes of it. Delays build through the day: the median wait is about 19 minutes for patients arriving before 10:00 and about 66 minutes after 19:00, so evening patients now come about 32 minutes early to protect their place. Volume is rising, from 54 patients a weekday in October to 67 in December, and busy days are worse.

The department must also:

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

Deciding how many new patients to start each day is also subjective today. The department records appointment, arrival and treatment-start times, but not how long each session takes.

If we solve it, patients arrive close to their real treatment time and are told about delays before they leave home. RTTs stop juggling times by hand. Complex cases always get supervision. New starts are planned two days ahead from real machine load, and both machines are used evenly. We tested our prototype under the department's own rules on a synthetic 87-patient day, 10 more patients than the busiest recorded day, simulated 300 times in a digital twin calibrated on the records. Against the department's busiest recorded days, the 90th-percentile wait fell from 130 to 76 minutes, the share treated more than an hour late from 27% to 6%, and the share treated within 15 minutes of their time rose from 30% to 53%. The median wait stays about the same (36 against 38 minutes), because every patient is asked to arrive 20 minutes early (45 for pelvic patients) to prepare. Waits no longer build up in the evening. Every hard rule held. The pilot target is a 90th-percentile wait at least 25% lower within 90 days (109 minutes in the records).

**Short version**

Radiotherapy patients come daily for weeks, yet times are allocated by hand, without knowing each patient's machine-minutes. The department's records show one patient in ten waiting more than 109 minutes and 22% treated over an hour late, worst in the evening. Staff juggle new starts by 17:00, supervised complex cases, the blood-irradiation slot, one breast board and one ABC unit shared with the CT simulator, the 17:00 MHRC bus, public-transport patients who must be home by 21:00, urgent patients, TBI and machine faults. Solving it gives patients predictable times, staff a plan they can trust, and the department balanced machines. Under the department's own rules, on a synthetic day busier than any recorded, our prototype cut the 90th-percentile wait from 130 to 76 minutes against the busiest recorded days, and lateness of over an hour from 27% to 6%. The pilot target is a 90th-percentile wait at least 25% lower in 90 days.

### 2.2 What you are building, and what you are building it with

**Full version**

RAD-SMART is an assistive operations layer between the patient list and the treatment machines. It has four AI parts, and a person approves everything:

1. **Predict.** A gradient-boosting model predicts each session's machine-minutes (expected and cautious P80) from operational tags: technique, fraction number, imaging, mobility and accessories. The department records arrival and treatment-start times but not session lengths, so the model starts from the department's own estimate table and learns once room entry and exit are captured.
2. **Optimise.** A constraint-optimisation engine (OR-Tools CP-SAT; HiGHS MILP in our prototype) builds the evening-before plan for each machine. Hard rules cannot be broken, and an independent checker re-verifies them. They include new starts by 17:00, complex cases in 10:00–17:00, the blood slot, MHRC slots before the 17:00 bus, public transport home by 21:00, and accessory limits including CT-simulator bookings and reservations. When a delay, fault, no-show, imaging hold or urgent patient occurs, it re-plans the rest of the day in seconds under the department's downtime rules. It treats patients already waiting first and moves as few others as possible.
3. **Simulate.** A digital twin, calibrated on the department's records of appointment and arrival times, stress-tests every plan against late arrivals, overruns and faults. It also produces a three-week load forecast that plans around TBI courses, and two-day-ahead advice on how many new patients each machine can take, balanced by minutes rather than head-count.
4. **Explain and converse.** A copilot on Sarvam AI (Sarvam-105B with tool calling via LangGraph) explains every placement ("why was this patient moved?") and turns rule changes written in plain language into versioned, validated configuration. Bulbul, Saaras and Sarvam Translate send patients and caregivers their reporting time and live updates by WhatsApp, SMS or voice call in Kannada, Malayalam, Hindi or English, and understand spoken "I'm running late" replies. Tulu, which no Sarvam model covers yet, gets Kannada-script text with a voice note recorded by Tulu-speaking staff. The LLM never makes a scheduling decision.

It works with what the clinic already has (an Excel list, a photo of the paper register read by Sarvam Vision OCR, QR check-in and WhatsApp) and runs on a hospital server. It now runs inside CARE as a plugin (Python and Django on the server, React in the browser), with a RADSMART button on the patient's visit page.

**Short version**

An assistive scheduling layer with four parts. Machine learning predicts each session's machine-minutes. A constraint optimiser (OR-Tools / HiGHS) builds and live-repairs the plan with hard rules guaranteed. A digital twin tests plans and forecasts new-start capacity two days ahead. A Sarvam AI copilot explains decisions, edits rules from plain language and messages patients by WhatsApp, SMS or voice in their language, with recorded voice notes for Tulu. The doctor approves every course and its standing slot, and a technologist or doctor approves every breakdown response. It runs inside CARE, the open-source hospital information system, and works from Excel, paper (OCR) and QR check-in, on an on-premise server.

### 2.3 Why yours is the right team to build it

**Full version**

- **The problem owner is on the team.** Dr Akshay Dinesan (Manipal) wrote the problem statement from daily experience in a working radiotherapy department that runs a Versa HD and is adding a second machine in early 2027. The department has already answered our detailed questions on its rules, from the MHRC bus to accessory reservations and downtime, and they are built into the prototype. Dr Akshay has a path to a real pilot and the RTT team who will use it.
- **We have already built it.** In the Round 1 window we built a working prototype. It generates realistic synthetic departments under the department's own rules. It predicts session durations and solves an 87-patient day to a proven optimum in 7–31 seconds on a laptop. It re-plans machine faults in 10–14 seconds under the department's downtime rules, and forecasts new-start capacity for two machines around a TBI course. We tested it over 300 simulated days in a digital twin calibrated on the department's own arrival and treatment records, and compared it with those records.
- **Doctors and engineers together.** Dr Akshay Dinesan is the team leader and doctor partner. Abhinand T M is the technical lead and P S Raghotham Rao the lead engineer. Dr Shirley Lewis Salins and Dr Umesh Velu are doctor partners, so three of the five members are practising doctors. Together we cover operations research, machine learning, Indian-language AI, product building and clinical practice.
- **We designed for the guardrails from day one.** The system is assistive, not diagnostic: human approval, audit trail, synthetic patients, the department's records used only as anonymised aggregates, no clinical inputs, and no personal identifiers sent to AI models.

**Short version**

Dr Akshay Dinesan owns the problem in a working radiotherapy department (a Versa HD, with a second machine arriving in early 2027), has given us the department's rules, and can take it to a real pilot. Dr Akshay leads a five-member team: Abhinand T M (technical lead), P S Raghotham Rao (lead engineer), and Dr Shirley Lewis Salins and Dr Umesh Velu (doctor partners). Together they cover optimisation, machine learning, Indian-language AI, full-stack development and clinical practice. It has already built a working prototype that plans an 87-patient day under the department's rules, re-plans machine faults in seconds, and was tested over 300 simulated days against the department's own records.

### 2.4 Does any part of it already exist?

**Full version**

Some pieces exist separately. None is a solution to this problem in an Indian department.

- **Oncology information systems** (for example MOSAIQ and ARIA) hold appointment calendars and record treatment times. As far as we know, they do not build a minute-level plan from predicted durations with guaranteed operational rules, re-plan live, balance a mixed-vendor fleet, or message patients in Indian languages. A department adding a second machine, possibly from another vendor, needs a vendor-neutral layer.
- **Academic research** shows that optimisation works for radiotherapy scheduling. A MILP scheduler implemented in two Dutch centres cut schedule preparation from 1.5 days to minutes, and automated scheduling at a Belgian centre reduced waits for treatment start by 80%. These systems mostly decide the start *day* in large, fully digital European centres, and are not products Indian departments can adopt.
- **Duration-prediction models** have been published, but they are not connected to live scheduling and patient communication.
- **We reuse open components:** OR-Tools and HiGHS (optimisation), scikit-learn (ML), Sarvam AI APIs (language, speech, OCR) and LangGraph (tool orchestration).
- **What we built ourselves (September 2026):** the prototype scheduling engine, duration model, simulator and capacity forecaster, running on synthetic patients, with the simulator calibrated on the department's anonymised records. What is new is combining prediction, guaranteed optimisation, simulation and multilingual communication in one light-integration, human-approved workflow.

**Short version**

OIS calendars (MOSAIQ, ARIA) and academic schedulers exist. The academic ones mostly choose start days in large European centres. Neither builds a minute-level, rule-guaranteed daily plan with live re-planning and multilingual patient messaging for a mixed-vendor Indian department. We reuse OR-Tools, HiGHS, scikit-learn, Sarvam AI and LangGraph. The scheduling engine, duration model, simulator and forecaster are our own prototype, built in September 2026 on synthetic patients and calibrated on the department's records.

### 2.5 Deck

The deck (now 9 slides) is built and published at https://claude.ai/artifact/LhSJi3g5j23xLHxTRYiSgw (section 3 lists the slides). Before uploading:

1. Check the names and roles on slide 1.
2. Download the deck as PDF from the page, and upload the PDF.

The link is private to its owner. Share it from the page's Share menu before anyone else, such as Dr Akshay, can open it.

A copy is also on GitHub: the PDF at `docs/deck/RAD-SMART_Pitch_Deck.pdf` and a public web version at https://psraghothamrao8.github.io/RAD-SMART/deck/. After editing the deck, copy the changed slides into `docs/deck/src/` and run `python tools/build_deck.py` to update both.

### 2.6 Optional items

- **Supporting document:** `docs/RAD-SMART_Research_Report.pdf`, the full research report and implementation plan (45 pages), `docs/RAD-SMART_Impact_Analysis.pdf`, the four-page analysis with and without RAD-SMART on both datasets, and `docs/RAD-SMART_Research_Paper.pdf`, the eight-page research paper.
- **Prototype link:** the project website at https://psraghothamrao8.github.io/RAD-SMART/, hosted on GitHub Pages and open to anyone: a one-page summary with simple charts (the problem, how it works, the app in CARE, results with and without RAD-SMART, breakdowns and the pilot) and links to every document. Its source is `docs/index.html`; edit it, commit and push, and the page updates within a few minutes.
- **Code:** https://github.com/psraghothamrao8/RAD-SMART (public). It holds the PoC, the documents and the page source. Its patients are synthetic, and the department's records appear only as aggregates (`poc/data/department_profile.json`); the spreadsheet is never committed.
- **Video walkthrough:** the script is in section 4.

---

## 3. Deck outline (9 slides)

The deck is written for a panel that is not all technical: one point per slide, large numbers, and simple bar charts drawn on the slide. The footers name the sources. The deck has four sections: the problem, the solution, the evidence and the plan.

| # | Slide title | Key message | Visual |
|---|---|---|---|
| 1 | RAD-SMART | The right patient, on the right machine, at a predictable time | Title; the five team members and their roles |
| 2 | One machine, 70–90 patients a day, long waits | One patient in ten waits over 109 min; 22% are treated over an hour late; the wait grows from 19 min in the morning to 66 in the evening | Two big numbers + a two-bar chart |
| 3 | It is not just booking appointments | Sessions differ, rules must hold, the day changes; each patient keeps one slot for the whole course | Three cards |
| 4 | We compared five ways; a hybrid scored best | Templates 3.1, LLM alone 2.6, optimisation alone 3.6, reinforcement learning 2.5, hybrid 4.85 out of 5 | Bar chart of scores |
| 5 | Four steps, and a person decides | Predict, plan, test, tell; the doctor approves each course, a technologist or doctor every change on the day | Four step cards + approval band |
| 6 | One button on the patient's page | The working app in CARE: doctor, technologist, breakdown | Two screenshots |
| 7 | Long waits fall by more than a third | Department's 55 days replayed: 109 → 70 min (−35%); 12 simulated weeks: 82 → 49 min (−40%); over an hour late 22% → 6%; the trade-off: a later evening | Two before/after bar pairs + three tiles |
| 8 | A new plan in seconds, not a lost day | Typical wait after a 2½-hour breakdown 104 → 39 min, after 45 minutes 53 → 37; the department's breakdown rules | Two bar pairs + rules card |
| 9 | Safe by design, then a 90-day pilot | Measure, shadow, live; target 25% shorter long waits; four guardrails; the ask | Timeline + two cards |

Earlier, longer versions of the deck (with the day Gantt and the wait curves) are in the repository's git history.

## 4. Video walkthrough script (3 minutes)

| Time | On screen | Voice-over |
|---|---|---|
| 0:00–0:20 | Dr Akshay on camera (or an illustration of a waiting area) | "Every weekday, about eighty people come to our radiotherapy machine, many for six or seven weeks. They all have appointments, yet our own records show one in ten waiting almost two hours, and the evening waits longest, because times are given by hand, without knowing how long each treatment will take." |
| 0:20–0:45 | The constraint table | "It isn't simple booking. New patients must finish by five. Complex treatments need senior staff. There's a blood-irradiation slot, one breast board and one breathing-control unit shared with the CT simulator, a hospital bus at five, patients who must catch their bus home by nine, urgent patients, and machine faults. Soon there'll be a second machine." |
| 0:45–1:15 | Architecture figure, highlighting each layer | "RAD-SMART is an assistive operations layer. Machine learning predicts each patient's machine-minutes. An optimiser builds the day's plan, and hard rules can't be broken. A digital twin tests the plan. A copilot on Sarvam AI explains every decision and messages patients in their own language." |
| 1:15–1:45 | Optimised-day Gantt, then the wait chart | "We tested it on a synthetic eighty-seven-patient day, busier than any in our records, under our own rules, three hundred times. The longest waits fell from a hundred and thirty minutes to seventy-six, only six percent were treated more than an hour late instead of twenty-seven, and every hard rule held." |
| 1:45–2:10 | Fault chart; phone mock-up receiving a message in Kannada | "When the machine fails, RAD-SMART re-plans the rest of the day in seconds, following our department's downtime rules. Patients already waiting go first. It moves as few people as possible and tells only those who can still act, by WhatsApp, SMS or a voice call, even in Tulu." |
| 2:10–2:30 | Forecast chart | "Two days ahead, it advises how many new patients each machine can start, balanced by minutes, not head-count, and it plans around total body irradiation. That keeps both machines at capacity instead of overloading one." |
| 2:30–2:50 | Guardrails slide | "It is assistive, not diagnostic. It never decides treatment. The doctor approves every course, a technologist or doctor approves every breakdown response, every change is logged, and no personal data goes to the AI models." |
| 2:50–3:00 | Pilot timeline and team | "Our 90-day pilot aims to cut the longest waits by at least a quarter. RAD-SMART: the right patient, on the right machine, at a predictable time." |

---

## 5. Likely jury questions

**Is the data real?**
The prototype's patients are synthetic. The rules are the department's (its answers of 21 September and 24 October 2026), and its anonymised arrival and treatment records for 55 days (October–December 2024, 3,137 patient-days) calibrate the digital twin: how appointment times are spread over the day and how early patients arrive. We quote today's figures from those records, not from our model, and publish only aggregates (medians, percentages and hourly profiles). The spreadsheet never leaves the team.

**Why doesn't the median wait fall?**
Every patient is asked to arrive 20 minutes early (45 for pelvic patients) to change and prepare, so a short wait is built in. What RAD-SMART removes is the long, unpredictable wait. On a day busier than any recorded, one patient in ten waits 76 minutes or more instead of 130, only 6% are treated more than an hour late instead of 27%, and evening patients no longer wait three times as long as morning ones. Morning patients wait a little longer than today, mostly that preparation time.

**Why does one patient in the prototype move from 08:50 to 19:24?**
That happens only in the single-day test, which plans each day from scratch and draws each patient's current time from the department's recorded booking pattern. Since 24 October RAD-SMART gives each course a standing slot, as the department does: a new start before 17:00, then one time for every later fraction, kept until the course ends unless the patient asks to change it. A patient's time no longer moves from day to day.

**What happens when the machine breaks down for hours?**
The department's rules of 24 October are built in. Up to 60 minutes, nobody is sent home and everyone is treated with overtime. Over 60 minutes, RAD-SMART sends back only as many patients as the expected downtime needs, those who have not left home first, and never a gap-sensitive course or a hospice patient without the oncologist. New starts wait for the machine, patients at home are told to postpone travel, and a technologist or doctor approves before anyone is told. A missed fraction is added at the end of the course.

**Does it work inside our hospital system?**
It runs inside CARE, the Open Healthcare Network's open-source hospital information system, as a plugin with a RADSMART button on the patient's visit page. The same pattern applies to the hospital's own EMR through its integration route.

**Isn't this clinical decision support?**
No. RAD-SMART decides only *when* and *on which machine* a session happens. Urgency, technique and machine eligibility are entered by clinicians and physicists, and it reads no diagnoses, doses, images or notes. Its only prediction is how many minutes a session will take.

**Why not just ask an LLM to make the schedule?**
An LLM cannot guarantee rules such as "no new start after 17:00", is weak at packing minutes, and can give different answers to the same input. We use the LLM for what it is good at, which is explaining, editing rules and talking to patients in their language. A solver produces the plan.

**What if patients don't have smartphones or can't read?**
Voice calls in their language (Sarvam Bulbul), plain SMS, and a copy to a caregiver. Reception staff can still print the list. The simulation already assumes 15% of patients do not act on updates.

**Where do treatment durations come from if you don't have OIS data?**
The department records arrival and treatment-start times but not how long sessions take, so we start from its own estimate table. The prototype shows that averages alone deliver most of the benefit (a 90th-percentile wait of 82 minutes with averages, 76 with machine learning). A tablet tap at room entry and exit then collects real durations, and the model learns weekly.

**Is prioritising paying patients fair?**
The department asked for paying patients to get their preferred time as far as possible. Every priority is an explicit, visible weight that the department sets, and the MHRC bus and public-transport limits are hard rules. The dashboard reports waits by group (elderly, transport-dependent, language, paying versus non-paying), and any group getting worse is flagged for review.

**Your patients speak Tulu. Does Sarvam support it?**
Not yet. Sarvam's speech models cover 11 languages (Bulbul v3) and the 22 scheduled languages plus English (Saaras v3), and Tulu is not among them. Tulu speakers get the text in Kannada script, which is how Tulu is usually written, with a short voice note recorded by Tulu-speaking staff for each approved template. If a Tulu model appears, it replaces the recordings.

**Why does the day end later with RAD-SMART?**
Two reasons. On the 87-patient test day, the plan holds 40 minutes for same-day urgent starts and imaging re-treatments: the last patient finishes at about 01:03, and holding nothing ends the day at 00:49, with a 90th-percentile wait of 88 minutes instead of 76. With standing slots, patients are spread out instead of being given the same time, and 150 minutes before 17:00 are kept for new starts, so over 12 weeks the last patient finishes at about 00:07 instead of 21:55, still inside the department's hours. Both are settings the department chooses.

**What happens when the internet or WhatsApp is down?**
Planning runs on the hospital server over the LAN. Messages fall back to SMS or a voice call, and a printed list is always available.

**How is this different from the scheduling module in MOSAIQ or ARIA?**
Those are calendars that record appointments. RAD-SMART computes the plan from predicted minutes and rules, repairs it live, forecasts new-start capacity, and speaks Indian languages. It is vendor-neutral, which matters for a department running Elekta and Varian machines side by side.

**How will you prove it works?**
Two weeks adding room entry and exit taps to the arrival and treatment times the department already records, to refresh the baseline, then three weeks of shadow mode and eight weeks live on one machine. The primary KPI is the 90th-percentile wait (109 minutes in the records; target at least 25% lower), reported as an interrupted time series. Secondary measures are punctuality (over an hour late: 22% → 10% or fewer), the median wait, which must not rise, and balancing measures (throughput, overtime, equity, override rate).
