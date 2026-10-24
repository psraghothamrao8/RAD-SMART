# RAD-SMART User Guide

**How to use the app in the department, and how to show it in a demo**

Health-a-thon 2026, Cancer track · Manipal · 25 October 2026

---

RAD-SMART plans the radiotherapy machine's day. It gives every course one fixed daily time that keeps all the department's rules, and it re-plans in seconds when the machine breaks down. It runs inside CARE, the hospital information system, as an extra button and six pages. **RAD-SMART only suggests. A doctor or technologist approves every change.**

> **Watch the demo first.** A 2¾-minute recording of the real app, with captions, is on the project website: [psraghothamrao8.github.io/RAD-SMART](https://psraghothamrao8.github.io/RAD-SMART/#demo). The file is also in the repository as `docs/media/RAD-SMART_demo.mp4`. Every patient in the video and in this guide is synthetic.

## Who does what

| Person | Uses RAD-SMART to | Pages |
|---|---|---|
| **Doctor** (radiation oncologist) | enter a course and approve its time | RADSMART button, New course, Courses |
| **Technologist** (RTT) | run the day: arrivals, time changes, breakdowns | Today, Courses, Breakdown |
| **Both** | see whether waits are falling | Insights |

A technologist can do everything except enter or approve a course. Only a doctor can do that.

## Part A · Everyday use

The five steps below follow one patient and one working day. They are the same five steps as the demo video.

### 1. The doctor plans a new course

1. Open the patient's visit in CARE and click the green **RADSMART** button at the top. The button shows the patient's daily time once a course is approved.

![The patient's visit page in CARE. RAD-SMART adds the RADSMART button.](figures/app0_visit_header.png){width=6.2}

2. The button opens the patient's radiotherapy courses. Click **New course**.
3. Fill in the prescription, as on the paper form: hospital number, diagnosis, total dose, number of fractions, treatment days, technique and site.
4. In the **priority checklist**, tick what matters for this patient: public transport, hospice bus, ABC or breast board, a time window, gap-sensitive course, preferred time, and so on. **Hard constraints** are always kept. **Soft goals** are met where possible. Some boxes tick themselves: age 70 or over ticks *older patient*, and the technique ticks its accessories.

![The intake form: prescription and priority checklist.](figures/app2_intake.png){width=5.4}

5. Click **Save and propose slots**. Within seconds RAD-SMART proposes a **first day** (always finishing before 17:00) and **one standing time** for every later fraction. It lists its reasons and offers alternatives.
6. Pick the recommended time or an alternative, and click **Approve course and slots**. The patient keeps this time every day until the course ends. To start on a different date, use **Try another start date** and **Propose again**.

![RAD-SMART's proposal, waiting for the doctor's approval.](figures/app3_proposal.png){width=6.2}

### 2. The technologist runs the day

Open **RAD-SMART → Today**. The page shows four things:

- **The machine card:** sessions, new starts, how many are after 17:00, when the day will finish, and the free time left for new starts.
- **The rule check:** a green bar means every hard rule holds for the patients still to be treated. **Approve the plan** records that a technologist or doctor has checked the day.
- **The timeline:** one block per patient. Green is a new start, blue is a standing slot, orange was moved today, violet is an added fraction. The red line is *now*.
- **The patient list:** each patient's time, reporting time, needs and status.

![Today's board: the machine, the rule check, the timeline and the patient list.](figures/app1_today.png){width=6.2}

For each patient, tap **Arrived** when they come, **In room** when they go in, and **Out** when they come out. These three taps measure the real waiting time. The other buttons:

- **Undo** corrects a wrong tap.
- **Not today** sends a patient home for the day, and adds the missed fraction at the end of the course.

![Recording arrivals: one patient waiting, one in the room, the next ones still to come.](figures/app6_arrivals.png){width=6.2}

### 3. A patient asks for another time

1. Open **Courses**, search for the patient by name or hospital number, and open the course.
2. Under **The patient asks for another time**, enter the date it should start from, the time the patient asks for, and the reason (for example, bus timing).
3. Click **Find a time**. RAD-SMART shows the nearest time that keeps every rule, for this patient and for everyone else.
4. Choose a time and click **Approve**, or **Keep** the current time. Nothing changes until someone approves.

![A slot change: the patient asked for 16:00, and RAD-SMART offers 15:20.](figures/app7_slot_change.png){width=6.2}

### 4. The machine breaks down

1. On **Today**, click **Report breakdown**. Enter when the fault started, the engineer's estimate of the downtime (15 minutes to 48 hours) and a short note. Then click **Take offline and propose**.
2. Within seconds RAD-SMART proposes a new plan that follows the department's rules:
   - **Up to 1 hour:** nobody is sent home. Everyone is treated today, with up to an hour of overtime.
   - **Longer than 1 hour:** only as many patients are sent back as the downtime needs, starting with patients who have not yet left home. Their missed fraction is added at the end of the course. A gap-sensitive or hospice patient is never sent back automatically: the doctor decides.
   - **Patients still at home** are asked to come later, with a message drafted in their own language.
   - **New starts** wait for the machine and still finish before 17:00, or move to the next working day.
3. Read the summary and the list of affected patients, then click **Approve and notify**, or **Reject**.
4. If the engineer changes the estimate, choose the new time and click **Re-plan with this estimate**. When the machine works again, click **Back online**.

![A two-hour breakdown: the proposal waits for approval.](figures/app5_breakdown.png){width=6.2}

### 5. Check that it is working

**Insights** shows the measured waits for any date range:

- the long wait (90th percentile) and the typical (median) wait, from arrival to the treatment room;
- the share of patients treated on time, and the share more than an hour late;
- patients sent back, new starts postponed, and fractions added at the end of courses.

The chart compares each day with the department's baseline (108.6 minutes) and the pilot target (25% lower).

![Insights: measured waits against the baseline and the target.](figures/app8_insights.png){width=6.2}

### What RAD-SMART never does

- It never decides **whether** or **how** a patient is treated, only **when**.
- It never changes a time, sends a patient back or messages anyone without a person's approval.
- It never sends names or hospital numbers to an AI service.

<!-- pagebreak -->

## Part B · Showing it in a demo

### Before the demo (15 minutes)

1. Start the app as described in [app/README.md](https://github.com/psraghothamrao8/RAD-SMART/blob/main/app/README.md): the CARE backend, the RAD-SMART plugin and care_fe.
2. **Refresh the demonstration data** so today's board is played out up to the current time (command below). On a weekend or a holiday, the demo shows the next working day.
3. Open two browser windows, one normal and one private:
   - sign in as **care-doctor** in one, and open a patient's visit page;
   - sign in as **care-staff** in the other, and open **RAD-SMART → Today**.
4. Keep the demo video open in a third tab as a backup.
5. Pick a patient with no radiotherapy course, so the RADSMART button starts a new course.

The refresh command, run in the CARE workspace:

```
./.agent/compose.sh exec backend python manage.py radsmart_demo --facility <facility id> --user care-doctor --census 60
```

### The 5-minute demo

| Time | Screen (who) | What to do | What to say |
|---|---|---|---|
| 0:00 | Visit page (doctor) | Point to **RADSMART**, click it, then **New course** | "RAD-SMART lives inside the hospital system. The doctor starts from the patient's visit." |
| 0:30 | New course | Fill in the prescription, then tick *public transport* and *gap-sensitive* | "The doctor fills the form as on paper. Each tick becomes a rule the computer must keep." |
| 1:15 | Proposal | Click **Save and propose slots**, point to the first day and the standing time, then **Approve** | "One time for the whole course, with the reasons. The doctor stays in charge." |
| 2:00 | Today (technologist) | Show the green rule check and the timeline; tap **Arrived**, **In room**, **Out** for one patient | "Every rule holds. These taps measure the real wait." |
| 2:45 | Course (technologist) | Patient asks for 16:00: **Find a time**, then **Approve** | "The nearest time that keeps every rule, for everyone." |
| 3:30 | Breakdown | **Report breakdown**, 2 hours: show the summary and the list, then **Approve and notify** | "A new plan in seconds, under the department's own rules. Patients at home are told to come later." |
| 4:30 | Insights | Point to the long wait against the baseline and the target | "This is how the department will know if it works: 109 minutes today, target 25% lower." |

### If something goes wrong

- **A page is slow or fails:** switch to the video tab and keep talking over it. The video shows the same five steps.
- **The day looks finished or empty:** run the refresh command again (step 2 above).
- **A rule warning appears:** say so. It shows that RAD-SMART checks every plan. Then refresh the data after the demo.

### Questions the panel may ask

- **"Is this real patient data?"** No. All patients are synthetic. The department's records were used only as anonymised totals.
- **"What if the AI is wrong?"** The plan comes from an optimiser that cannot break a hard rule. A rule checker re-checks every plan, and a person approves every change.
- **"Does it work without internet?"** Planning, the rule check and the board run on the hospital's own server. Sending messages needs the SMS or WhatsApp gateway. If the language model is unavailable, staff still see the reasons and the fixed message templates still work.
- **"What does staff have to do extra?"** Three taps per patient. The doctor fills in one form per course, which replaces the paper booking.

---

*RAD-SMART proposes; a doctor or technologist decides. It is not a medical device. The demo uses synthetic data on a local copy of CARE.*
