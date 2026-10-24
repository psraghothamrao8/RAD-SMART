# RAD-SMART for CARE

RAD-SMART runs inside [CARE](https://github.com/ohcnetwork/care), the open-source hospital
information system of the Open Healthcare Network, as a pair of plugins. CARE's core stays
unchanged: the plugins use CARE's documented plugin system.

| Folder | What it is |
|---|---|
| [`care_radsmart/`](care_radsmart/) | Backend: a Django app mounted at `/api/care_radsmart/`. Models, permissions and the REST API. It calls the scheduling engine in [`../poc/radsmart`](../poc/radsmart). |
| [`care_radsmart_fe/`](care_radsmart_fe/) | Frontend: a Vite Module Federation remote loaded by care_fe. Six pages in the facility, plus a **RADSMART** button on the patient's visit page. |

Every patient shown in the screenshots and the demonstration is synthetic.

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

**Both roles**: **Insights** shows the wait from arrival to the treatment room, measured from the times technologists record, against the baseline (90th percentile 108.6 min in the department's records) and the target (25% lower).

### Permissions

| Permission | Who has it | Allows |
|---|---|---|
| `can_view_radsmart` | doctor, nurse, staff, facility admin, admin | the pages and the API's read endpoints |
| `can_operate_radsmart` | doctor, nurse, staff, facility admin, admin | recording times, machine status, breakdown and slot-change approval, approving the day |
| `can_approve_radsmart_course` | doctor, facility admin, admin | entering, approving and cancelling courses |

The checks run on the server; the pages only hide what a role cannot do.

## Run it locally (Windows, Docker Desktop)

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
7. Sign in with a care_fe fixture account (e.g. `care-doctor` or `care-staff`). Open a facility; **RAD-SMART** appears in the facility menu.

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
| `POST demo/seed/` | synthetic demonstration data (demo servers only) |

## Limitations

- **Synthetic data only.** No real patient data was used to build or test the plugins. The duration model is trained on the engine's synthetic history until the department's own recorded room-in and room-out times are enough to retrain it.
- **Messages are drafted, not sent.** Breakdown messages are written in the patient's language; sending them needs the hospital's SMS or WhatsApp gateway.
- **One department, one machine in the demonstration.** The engine handles several machines (the PoC's forecast uses Versa HD and Halcyon), but the demonstration registers only the Versa HD.
- **The hospital's own EMR.** CARE is the integration target for the hackathon. The same button-on-the-visit-page pattern applies to the hospital's own EMR, through its own integration route.
- **Not a medical device.** RAD-SMART proposes; a doctor approves every course and a technologist or doctor approves every breakdown response.
