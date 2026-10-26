# RAD-SMART for CARE

RAD-SMART runs inside [CARE](https://github.com/ohcnetwork/care), the open-source hospital
information system of the Open Healthcare Network, as a pair of plugins. CARE's core stays
unchanged: the plugins use CARE's documented plugin system.

| Folder | What it is |
|---|---|
| [`care_radsmart/`](care_radsmart/) | Backend: a Django app mounted at `/api/care_radsmart/`. Models, permissions, the REST API, the Sarvam AI layer (`sarvam.py`), patient messages (`messages.py`) and the patient's own phone page (`patient.py`). It calls the scheduling engine in [`../poc/radsmart`](../poc/radsmart). |
| [`care_radsmart_fe/`](care_radsmart_fe/) | Frontend: a Vite Module Federation remote loaded by care_fe. Eight pages in the facility (Today, Courses, New course, Breakdown, Messages, Check-in, Insights, and each course), plus a **RADSMART** button on the patient's visit page. |

Every patient shown in the screenshots and the demonstration is synthetic.

For a step-by-step guide with screenshots, and a 5-minute demo script, see the [user guide](../docs/RAD-SMART_User_Guide.pdf). A captioned recording of the app is on the [project website](https://psraghothamrao8.github.io/RAD-SMART/#demo).

## Who uses it, and for what

**Doctor (radiation oncologist)**: enters and approves each course.
1. On the patient's visit page, clicks **RADSMART**. The button shows the patient's standing time once a course is approved.
2. Enters the hospital number, diagnosis, total dose, number of fractions and treatment days (every working day, alternate days, twice daily, twice a week or once a week).
3. Ticks the **priority checklist**, a box for every hard rule and soft goal (hospice bus, public transport, ABC or breast board, a time window, gap-sensitive course, preferred time, paying, inpatient, dormitory, lives nearby). Age and technique tick their own boxes.
4. RAD-SMART proposes a **new-start slot before 17:00** and **one standing slot for every later fraction**, with its reasons and the alternatives. The doctor approves; the patient keeps that slot until the course ends.

**Technologist (RTT)**: runs the day.
1. **Today** shows every machine, the day on a timeline, and the list of patients. The technologist records **Arrived → In room → Out**. Undo is available, and **Not today** adds the missed fraction at the end of the course.
2. When a patient asks for another time, **Find a time** proposes the nearest time that keeps every rule. The slot changes from the chosen date only when someone approves it.
3. When a machine fails, **Report breakdown** takes it offline with the expected downtime (15 minutes to 48 hours). RAD-SMART proposes the response for a technologist or doctor to approve:
   - **up to 60 minutes:** nobody is sent home; everyone is treated today with up to 60 minutes of overtime;
   - **over 60 minutes:** as many patients are sent back as the expected downtime needs, those who have not left home first; a gap-sensitive (RCR category 1) or hospice patient is never sent back automatically; the oncologist decides;
   - patients who have not left home are asked to wait, with a message drafted in their language;
   - patients already waiting are treated first when the machine is back;
   - new starts wait until the machine works, still finishing before 17:00, or move to the next working day.
4. **Back online** ends the breakdown. **Re-plan with this estimate** handles an engineer's revised estimate.
5. **Messages** lists every message drafted after an approval (a new course, a new standing time, a breakdown response), translated into the patient's language by Sarvam AI, with a voice note to **Listen** to. **Open WhatsApp** opens a chat with the text filled in; the technologist presses send there and marks it sent. A translation that drops or changes a time is not used: the patient gets the English text.
6. **Today** shows what patients said on their phone page (on the way, late by about N minutes, cannot come today, wants another time), as a card and as a badge beside the patient.

**Reception**: **Check-in** takes the six-letter code from the patient's phone (a USB barcode scanner types it, the laptop or phone camera reads the QR code, or the patient reads the letters out). The patient is marked arrived on Today's board.

**Patient**: one private link, sent once on WhatsApp from the course page. No app and no login; the page shows the first name only.
- today's time to come, any change after a breakdown, and the next five treatment days;
- the department's messages in their language (Kannada, Malayalam, Hindi, Konkani; Tulu speakers read Kannada script), each with a voice note;
- the check-in QR code on treatment days;
- four buttons: **on my way**, **I will be late** (15-60 min), **I cannot come today**, **I want a different daily time** (this becomes a slot-change request that staff decide; at most six replies a day).

**Doctor, while approving**: **Explain in plain words** asks Sarvam-105B to explain the proposed times from the engine's own reasons, in English and the patient's language. An answer that mentions a time not in the plan is rejected and the engine's reasons are shown instead.

**Both roles**: **Insights** shows the wait from arrival to the treatment room, measured from the times technologists record, against the baseline (90th percentile 108.6 min in the department's records) and the target (25% lower).

### Permissions

| Permission | Who has it | Allows |
|---|---|---|
| `can_view_radsmart` | doctor, nurse, staff, facility admin, admin | the pages and the API's read endpoints |
| `can_operate_radsmart` | doctor, nurse, staff, facility admin, admin | recording times, machine status, breakdown and slot-change approval, approving the day |
| `can_approve_radsmart_course` | doctor, facility admin, admin | entering, approving and cancelling courses |

The checks run on the server; the pages only hide what a role cannot do.

## Run it locally (Windows, Docker Desktop)

To set all of this up in one step, run `bash workspace/restore.sh` from the repository root (see [`../workspace/README.md`](../workspace/README.md)); the steps below explain what it does.

The setup follows the [CARE plugin guide](https://docs.ohc.network/contributing/plugins/) and
[care_scaffold](https://github.com/ohcnetwork/care_scaffold). Below, `WORKSPACE` is a care_scaffold
checkout with `care` and `care_fe` cloned inside it, and `RADSMART` is this repository.

1. **Ports.** This setup uses 19100 (API), 19101 (care_fe), 19102 (this plugin), and 19103-19107 (Postgres, Redis, MinIO and the debugger). Use any free ports; set them in `WORKSPACE/care-scaffold.env`.
2. **Mount and register the backend plugin.** Write `WORKSPACE/.agent/plugin.compose.yaml` (the scaffold's compose wrapper loads it). It mounts `RADSMART/app/care_radsmart` and `RADSMART/poc`, installs both in editable mode when the container starts, and registers the plugin:
   ```yaml
   services:
     backend:
       environment: &plugin_environment
         ADDITIONAL_PLUGS: >-
           [{"name":"care_radsmart","package_name":"/plugins/care_radsmart","version":"",
             "configs":{"RADSMART_DEMO":true,"RADSMART_MACHINES":"VERSA:Versa HD"}}]
       volumes:
         - {type: bind, source: "${PLUGIN_BE}", target: /plugins/care_radsmart}
         - {type: bind, source: "${RADSMART_ENGINE}", target: /plugins/radsmart_engine}
       entrypoint: [bash, -c, "python -m pip install -q -e /plugins/radsmart_engine -e /plugins/care_radsmart && exec bash scripts/start-dev.sh"]
     celery:
       environment: *plugin_environment
       volumes: (the same two mounts)
       entrypoint: [bash, -c, "python -m pip install -q -e /plugins/radsmart_engine -e /plugins/care_radsmart && exec bash scripts/celery-dev.sh"]
   ```
   Put `PLUGIN_BE` and `RADSMART_ENGINE` in `WORKSPACE/.agent/paths.env` with forward slashes, e.g. `C:/Users/you/RAD-SMART/poc`.
3. **Start the backend:** `./.agent/compose.sh up -d --wait backend celery`. The celery start-up runs the migrations (the plugin ships `0001_initial`) and `sync_permissions_roles`.
4. **Synthetic demonstration data** (only when `RADSMART_DEMO` is on):
   ```bash
   ./.agent/compose.sh exec backend python manage.py radsmart_demo --facility <facility id> --user care-doctor --census 60
   ```
   This creates synthetic patients whose courses started over the past seven weeks, each allocated and approved through the engine. Past days, and today up to now, are played out in the digital twin. On a weekend the demonstration clock moves to the next working day.
5. **Start the frontend plugin:** `cd RADSMART/app/care_radsmart_fe && npm install && npm run dev` (build, watch, and serve on 19102).
6. **Start care_fe with the plugin enabled:**
   ```bash
   cd WORKSPACE/care_fe
   REACT_CARE_API_URL=http://localhost:19100 \
   REACT_ENABLED_APPS="ohcnetwork/care_radsmart_fe@localhost:19102/assets/remoteEntry.js" \
     npm run dev -- --host 127.0.0.1 --port 19101 --strictPort
   ```
7. **Sarvam AI (optional).** Put the key in `WORKSPACE/.agent/.env` as `SARVAM_API_KEY=...` (that folder is git-ignored; never commit the key) and pass it to the backend in `plugin.compose.yaml`: `SARVAM_API_KEY: ${SARVAM_API_KEY:-}` under `environment`, and load the file before compose runs (`set -a; . .agent/.env; set +a`, or source it at the top of `.agent/compose.sh`). Without a key, messages go in English and Explain shows the engine's reasons. Plugin settings: `RADSMART_DEPARTMENT` (the name patients see), `RADSMART_PUBLIC_URL` (the address patients' links use, e.g. `https://hospital.example`; defaults to the address staff use), `RADSMART_SARVAM_TIMEOUT` (seconds).
8. Sign in with a care_fe fixture account (e.g. `care-doctor` or `care-staff`). Open a facility; **RAD-SMART** appears in the facility menu.
9. **Telegram, for demonstrations (optional).** WhatsApp's Business API needs a verified business, so for showing the app the server can send messages on Telegram; real use sends them on WhatsApp. Make a bot with @BotFather and put `RADSMART_TELEGRAM_TOKEN=...` and a random `RADSMART_TELEGRAM_SECRET=...` in `WORKSPACE/.agent/.env`. The course page then shows a Telegram QR code: the patient scans it and presses Start, and their chat is linked to the course. Messages get a **Send on Telegram** button, with the voice note, and the patient answers with buttons (on my way, late, cannot come, another time). A local server is not reachable from Telegram, so run `python manage.py radsmart_telegram --poll` in the backend container. A public server uses `--webhook https://<address>`.

To host the demonstration on the internet within an Azure for Students subscription's free services, see [`../deploy/azure/README.md`](../deploy/azure/README.md).

Windows notes:
- Bind-mounted file changes do not reach the container's auto-reloader. After editing the backend, run `./.agent/compose.sh restart backend`.
- `npm run dev` runs a single watch build. A second build in the same process drops the federation manifest.

## API

All endpoints are under `/api/care_radsmart/` and take `?facility=<id>`.

| Endpoint | Purpose |
|---|---|
| `GET config/` | form options, the day's rules, machines, the caller's permissions |
| `GET day/?date=` · `POST day/` | the day's board, and the rule check; approve the day |
| `courses/` (list, create, retrieve, update while draft) | `POST courses/{id}/propose/`, `approve/`, `cancel/`, `GET sessions/`, `POST slot-request/` |
| `slot-requests/` | `POST {id}/approve/` (with an optional `time`), `reject/` |
| `machines/` | `POST machines/{id}/status/` online or offline; offline returns a breakdown proposal |
| `triage/` | `POST` to re-plan with a revised estimate; `POST {id}/approve/`, `reject/` |
| `sessions/{id}/` | `POST arrive/`, `room/`, `done/`, `undo/`, `send-home/` |
| `GET insights/?from=&to=` | measured waits and punctuality |
| `GET patients/?q=` | patients under the facility's care, for the intake form |
| `GET courses/{id}/patient-link/` | the patient's page link, check-in code, QR code (SVG) and a WhatsApp link to send it |
| `POST courses/{id}/explain/` | the proposed times in plain words (Sarvam-105B), optionally in the patient's `language` |
| `messages/?date=&course=&status=` | messages to patients; `POST {id}/sent/`, `cancel/`, `translate/`; `GET {id}/audio/` (MP3 voice note) |
| `replies/?date=&status=` | patients' replies from their page; `POST {id}/done/` |
| `POST checkin/` | `{facility, code}`: marks today's session arrived |
| `GET/POST p/{token}/` | the patient's own page (no login; the token is the key) and `p/{token}/audio/{message}/` |
| `POST demo/seed/` | synthetic demonstration data (demo servers only) |

## Tests

```bash
./.agent/compose.sh exec backend python manage.py test care_radsmart
```

`tests/test_sarvam.py` checks the safety guards without calling Sarvam: times are read in every script (including 12-hour times), a translation that drops or changes a time is thrown away, an explanation that invents a time is rejected, the app falls back to English with no key or when Sarvam is unreachable, rate limits are retried, and demo patients never get a phone number in a WhatsApp link. `tools/evaluate_sarvam.py` measures the real models on every message template (`docs/evaluation/`).

## Limitations

- **Synthetic data only.** No real patient data was used to build or test the plugins. The duration model is trained on the engine's synthetic history until the department's own recorded room-in and room-out times are enough to retrain it.
- **A person presses send.** Messages open in WhatsApp (click-to-chat) for a technologist to send, which needs no paid gateway. Sending automatically, and receiving spoken replies, needs the WhatsApp Business API and is the next phase.
- **Languages.** Sarvam has no Tulu model: Tulu speakers get Kannada script, and staff can record a Tulu voice note. Konkani has text but no Sarvam voice yet. Native speakers at the department still have to rate the translations (`docs/evaluation/sarvam_translations_for_rating.csv`).
- **Sarvam needs the internet and credit.** If Sarvam cannot be reached (or the account is out of credit), messages go in English and Explain shows the engine's reasons; scheduling never depends on Sarvam. Only message text is sent to Sarvam, never names, hospital numbers or phone numbers.
- **One department, one machine in the demonstration.** The engine handles several machines (the PoC's forecast uses Versa HD and Halcyon), but the demonstration registers only the Versa HD.
- **The hospital's own EMR.** CARE is the integration target for the hackathon. The same button-on-the-visit-page pattern applies to the hospital's own EMR, through its own integration route.
- **Not a medical device.** RAD-SMART proposes; a doctor approves every course and a technologist or doctor approves every breakdown response.
