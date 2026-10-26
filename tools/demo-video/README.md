# The RAD-SMART demo video

The video at `docs/media/RAD-SMART_demo.mp4` (and on the [website](https://psraghothamrao8.github.io/RAD-SMART/#demo)) is a real recording of the CARE plugin, narrated, made in three steps:

1. **Narrate.** `scripts/script.mjs` holds every line the narrator says (the caption on screen, and how the voice should read times and numbers). `scripts/narrate.mjs` voices each line once with Sarvam Bulbul v3 (Indian English) into `public/narration/`, named after the text, so changing one line re-voices only that line. The whole script is about 2,500 characters, about ₹8 at Sarvam's list price. `--dry` estimates the lengths without calling Sarvam, for test recordings.
2. **Record.** `scripts/record.mjs` drives the running app in headless Chrome through six steps: the doctor plans a course, the patient's phone (recorded at phone size), reception check-in, the technologist's day, a breakdown with the translated messages, and Insights. It waits for each narration line to finish before the next one, saves the voice notes the app plays, and writes the screencast frames and a log of pointer moves, clicks, zooms, captions and audio to `public/rec/`.
3. **Edit.** This [Remotion](https://www.remotion.dev) project turns the log into the video: an intro, a title card per step, the recording with a pointer, click ripples, zooms, captions and the narration, the patient's chapter inside a phone, and an outro. Waits for the server and page loads are sped up, but never while the narrator speaks (`src/timeline.ts`).

All patients are synthetic. The narration MP3s are committed, so the video can be rebuilt without voicing it again; the frames are not: record them again to rebuild the video.

## Rebuild

The recording is made against the public demonstration on Azure ([`deploy/azure/`](../../deploy/azure/README.md)), signed in with its one-click role entries, so no password is needed:

```bash
# 1. voice the narration (only new or changed lines are sent to Sarvam)
node scripts/narrate.mjs --env-file <scaffold>/.agent/.env

# 2. record: a fresh demonstration day at 14:30, and one patient's message sent to Telegram
FRESH=14:30 TELEGRAM=1 node scripts/record.mjs public/rec

# 3. preview and render
npm install
npm run dev        # Remotion Studio
npm run render     # writes ../../docs/media/RAD-SMART_demo.mp4
```

`FRESH` starts a fresh demonstration day first (new synthetic patients, the department clock at that time) and waits until it is ready. The recorder takes a patient over 70 with no active course for the doctor's step, cancelling an earlier take's course for that patient.

`TELEGRAM=1` sends one later patient's message to the Telegram app on the recording machine (Unigram, from the Microsoft Store, signed in to Telegram) and shows it arriving beside the app. The recorder sets Unigram's window to a phone's shape at the screen's edge, opens the bot's chat, and captures only that window (ffmpeg 8 or later, for its Windows Graphics Capture filter). The first time on each fresh day, it opens the patient's link in the bot's chat, which links that patient to this Telegram account. Unigram sends the link's `/start` itself when the bot's chat is already there; in a new chat the recorder presses START (with UI Automation). If neither works, it asks for START to be pressed by hand and waits. Close other chats first: only the bot's chat should be open. Unigram's window is put back as it was afterwards.

To record a local CARE stack instead, as in [`app/README.md`](../../app/README.md):

```bash
./.agent/compose.sh exec -T -e FACILITY=<facility id> backend python manage.py shell < <this folder>/scripts/seed_demo_tz.py
./.agent/compose.sh exec -T backend python manage.py shell < scripts/prep_take.py
./.agent/compose.sh exec -T backend python manage.py shell < scripts/ids.py     # FACILITY, PATIENT, ENCOUNTER
# (CARE_PW is the CARE development fixture password; the ids are CARE ids)
CARE_PW=... HOST=http://localhost:19101 API=http://localhost:19100 TZ_DEMO=America/Denver \
  FACILITY=<facility id> PATIENT=<patient id> ENCOUNTER=<encounter id> PATIENT_NAME=<name> node scripts/record.mjs public/rec
```

`TZ_DEMO` sets the browser's time zone during the recording (default `Asia/Kolkata`, the Azure server's). For a local stack, pick a zone where it is currently about 13:00 so the demonstration clock reads a working afternoon, and pass the same `TZ_DEMO` to the seed script. The backend needs `SARVAM_API_KEY` for the translated messages, voice notes and Explain to appear.

The narration is in `scripts/script.mjs`, the order of the steps in `scripts/record.mjs`; the look of the video is in `src/Demo.tsx`.
