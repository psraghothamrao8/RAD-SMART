# The RAD-SMART demo video

The video at `docs/media/RAD-SMART_demo.mp4` (and on the [website](https://psraghothamrao8.github.io/RAD-SMART/#demo)) is a real recording of the CARE plugin, made in two steps:

1. **Record.** `scripts/record.mjs` drives the running app in headless Chrome through the five demo steps (the doctor plans a course, the technologist runs the day, a patient changes time, a breakdown, Insights). It saves the screencast frames and a log of pointer moves, clicks, zooms and captions to `public/rec/`.
2. **Edit.** This [Remotion](https://www.remotion.dev) project turns the log into the video: an intro, a title card per step, the recording with a pointer, click ripples, zooms and captions, and an outro. Waits for the server and page loads are sped up (`src/timeline.ts`).

All patients are synthetic. The frames are not committed: record them again to rebuild the video.

## Rebuild

With the CARE stack and the plugins running as in [`app/README.md`](../../app/README.md):

```bash
# 1. fresh demonstration data, played out to a working afternoon in the recording's time zone
./.agent/compose.sh exec -T -e FACILITY=<facility id> backend python manage.py shell < <this folder>/scripts/seed_demo_tz.py

# 2. record (CARE_PW is the CARE development fixture password; the ids are CARE ids)
CARE_PW=... FACILITY=<facility id> PATIENT=<patient id> ENCOUNTER=<encounter id> node scripts/record.mjs public/rec

# 3. preview and render
npm install
npm run dev        # Remotion Studio
npm run render     # writes ../../docs/media/RAD-SMART_demo.mp4
```

The patient should have no active radiotherapy course, because the recording creates one. `TZ_DEMO` (default `America/Denver`) sets the browser's time zone during the recording so the demonstration clock reads a working afternoon whatever the local time. Pick a zone where it is currently about 13:00, and pass the same `TZ_DEMO` to the seed script.

Captions and the order of the steps are in `scripts/record.mjs`; the look of the video is in `src/Demo.tsx`.
