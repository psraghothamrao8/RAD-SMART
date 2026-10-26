// What the narrator says, in order. `text` is the caption on screen; `say` (when
// given) is how the voice reads it, for times and numbers a voice reads badly.
// narrate.mjs turns each line into an MP3 with Sarvam Bulbul; record.mjs shows the
// caption and waits for the voice to finish before the next one.
export const INTRO = "This is RAD-SMART, working inside CARE, the hospital's information system. Every patient you will see is synthetic.";
export const OUTRO = "RAD-SMART predicts, plans, tests and tells. A person decides every change.";

export const LINES = {
  visit: { text: "The doctor opens the patient's visit in CARE. RAD-SMART adds one button." },
  newCourse: { text: "The doctor starts a new radiotherapy course." },
  prescription: { text: "The prescription goes in as on the paper form." },
  ticks: { text: "Each tick in the checklist becomes a rule RAD-SMART must keep." },
  older: { text: "Some ticks are automatic: this patient is over 70, so 'older patient' is already ticked.", say: "Some ticks are automatic. This patient is over seventy, so older patient is already ticked." },
  save: { text: "Saving asks RAD-SMART to propose a time." },
  proposal: { text: "It proposes a first day before 17:00, and one standing time for the whole course.", say: "It proposes a first day before five in the evening, and one standing time for the whole course." },
  explain: { text: "Explain in plain words asks Sarvam AI to explain the time, in English and in Kannada, the patient's language." },
  guard: { text: "An explanation that mentions a time not in the plan is thrown away." },
  approve: { text: "The doctor approves. The patient keeps this time every day until the course ends." },
  link: { text: "The patient gets one private link on WhatsApp. No app, and no login." },
  tgLink: { text: "For this demonstration, the patient can also scan this code and get the messages on Telegram." },

  phone: { text: "On the patient's phone, the page is in Kannada: the first day, the time to come, and the days after." },
  voice: { text: "The department's message comes with a voice note, for patients who read little." },
  treatDay: { text: "On a treatment day, the page shows the time to come and a code for reception." },
  tap: { text: "One tap tells the department: on my way, running late, cannot come, or want another time." },

  scan: { text: "At reception, a scanner reads the code from the patient's phone." },
  checkedIn: { text: "The patient is checked in. The technologist's board shows them waiting." },

  board: { text: "Today's board: the machine, a check that every rule holds, and the day on a timeline." },
  blocks: { text: "Each block is one patient. Green is a new start, blue a standing time. The red line is now." },
  replies: { text: "Patients' replies arrive here: who is on the way, and who will be late." },
  taps: { text: "When the patient goes in and comes out, the technologist taps In room, then Out. That measures the real wait." },

  fault: { text: "The machine fails. The technologist reports it, with the engineer's estimate." },
  replan: { text: "In seconds, RAD-SMART re-plans the day under the department's own breakdown rules." },
  who: { text: "Who gets a new time, who comes another day, and why. Patients still at home are asked to wait." },
  approveFault: { text: "Nothing changes until a person approves. Then RAD-SMART drafts every patient's message." },
  messages: { text: "Sarvam AI translates each message. If a translation changes any time, it is not used." },
  listen: { text: "The technologist can listen to the voice note," },
  whatsapp: { text: "then opens WhatsApp with the message filled in, and presses send." },
  // With Telegram (record.mjs TELEGRAM=1), in place of `whatsapp`:
  telegram: { text: "and send it. Here it goes on Telegram, to a real phone." },
  tgPhone: { text: "The patient gets it in their own language, with the voice note, and can answer with one tap." },
  whatsappReal: { text: "In real use, the same message opens in WhatsApp, filled in and ready to send." },
  online: { text: "When the engineer fixes the machine, one tap brings it back online." },

  insights: { text: "Insights compares the measured waits with today's baseline of 109 minutes, and the target, 25% lower.", say: "Insights compares the measured waits with today's baseline of 109 minutes, and the target, 25 percent lower." },
};
