# RAD-SMART on Microsoft Azure

RAD-SMART runs live on Microsoft Azure, packaged as **one Docker image**: CARE's own production build with both RAD-SMART plugins, nginx and gunicorn. It is served by Azure Container Apps over HTTPS, with Azure Database for PostgreSQL, Azure Container Registry and a daily Container Apps job. One script builds, migrates, deploys and checks the whole system.

The public server is in **demonstration mode**, for judges and the department: the patients are synthetic and the data is renewed every morning. It runs on an **Azure for Students** subscription using only services that subscription gets free, so it spends none of the credit. The same image runs a real department; [From demonstration to pilot](#from-demonstration-to-pilot) lists what changes.

```bash
bash deploy/azure/deploy.sh all       # create, build, init, push, webhook, job
bash deploy/azure/deploy.sh status
```

Run it in Git Bash after `az login`, with the development stack running (`workspace/restore.sh`). The `init` and `webhook` steps use the stack's containers.

After a change to the plugin, update the server in this order. The job migrates the database before the app's new code needs it:

```bash
bash deploy/azure/deploy.sh build job reseed push
```

## Two ways in

The address opens the demonstration's front door, `/try/` ([`tryout.py`](../../app/care_radsmart/care_radsmart/tryout.py), switched on by `RADSMART_OPEN_DEMO`):

- **Demonstration.** One click signs the visitor in as the doctor, reception or the technologist, using that role's demonstration account (`RADSMART_DEMO_USERS`). No password is typed. Another link opens a demonstration patient's own phone page. Everyone shares the same demonstration. Changing a password or setting up two-factor sign-in is refused on this server (nginx answers 403), so one visitor cannot lock out the next.
- **Real use.** CARE's own sign-in page, after signing out of any demonstration account. Each person signs in with their own account, and RAD-SMART checks the role at every step. Reviewers' accounts are in the workspace's `.agent/azure-logins.txt`.

**A fresh day.** Out of hours the department's day is not running. "Start a fresh day" on the front door builds new synthetic patients, in a minute or two on this server (80 to 100 seconds in four tries). It then sets the demonstration's clock to 10:30 (or to `time`, 08:00 to 16:30, when posted to `try/restart/`), with the morning already played out. The clock is an offset from real time in the `DemoClock` table, and it applies only when `RADSMART_DEMO` is on. Times the app shows and records follow the offset, so the board, check-in and the patient's page agree. Fresh days start at most once every five minutes. The daily job sets the offset back to zero.

## What runs where, and why it is free

| Piece | Azure service | Free allowance (Azure for Students) | Used |
|---|---|---|---|
| CARE, the plugin and both frontends, in one container | Container Apps, Consumption profile | 180,000 vCPU-s, 360,000 GiB-s and 2 million requests a month, always free | 0.5 vCPU / 1 GiB, 0 to 1 replica, about 100 h of running a month |
| Database | PostgreSQL Flexible Server | 750 h of Burstable B1ms, 32 GB storage, 32 GB backup a month, 12 months | one B1ms server, 32 GB, no auto-grow, high availability or geo-backup, 7-day backups |
| Image store | Container Registry | 1 Standard registry with 100 GB, 12 months | about 1.5 GB; the newest three images are kept |
| Daily fresh data | Container Apps job | the same grant as the app | about 3 minutes a day |

The free allowances are listed on [Azure for Students](https://azure.microsoft.com/en-us/free/students/).

**Kept out on purpose, because each one is billed:**
- Log Analytics: the environment is created with `--logs-destination none`. Live logs still stream with `az containerapp logs show`.
- Dedicated workload profiles: the environment has only the built-in Consumption profile, so there is no plan management fee.
- Azure-side image builds (`az acr build`): images are built with local Docker and pushed.
- Key Vault, Blob storage and a separate Redis: secrets are Container Apps secrets, CARE's file uploads are not used in the demonstration, and Redis runs inside the container as a cache only.

**The region is UAE North.** Azure for Students allows only a few regions, and Container Apps is not offered in Central India.

## The cost guard

A Container Apps replica is billed for every second it runs beyond the free grant. At 0.5 vCPU and 1 GiB that grant is 100 hours a month. The app scales to zero when nobody uses it, but a browser left open on the live board keeps it awake.

[`guard.py`](guard.py) runs beside the server and counts each minute the app is awake in the database, per day. When the last 31 days reach **85 hours**, it makes the app's ingress internal through Azure Resource Manager, using the app's own managed identity. Nothing outside can reach the app then, so it scales to zero and costs nothing. The daily job opens it again once the 31 days are back under the limit. Any billing month fits inside a 31-day window, and the 15 spare hours cover the daily job and start-up time.

`deploy.sh status` shows the hours used. `pause` and `resume` take the app off the internet by hand; a hand pause is tagged on the app, so the daily job leaves it closed.

Azure for Students has no spending API (Cost Management answers 422), so check the remaining credit at [microsoftazuresponsorships.com](https://www.microsoftazuresponsorships.com/Balance) now and then.

## The container

[`Dockerfile`](Dockerfile) starts from CARE's own production image at the pinned revision, built from a clean `git archive`, so no local key or file goes in. It then adds:

- the engine and the plugin, installed editable as in development, because the engine reads `poc/data/`;
- nginx on port 8080. It serves the CARE frontend at `/` and the plugin's frontend at `/plugins/radsmart/`, and proxies `/api`, `/admin`, `/staticfiles` and the health checks to gunicorn ([`nginx.conf`](nginx.conf));
- Redis, cache only, with nothing saved;
- [`settings.py`](settings.py): CARE's production settings, with Celery tasks run in the request because there is no worker.

The CARE frontend is built in the image's first stage, on Linux as CARE's own Dockerfile does, from a clean export of the pinned care_fe commit. It uses same-origin API calls and no build-time plugins. (A build on Windows does not work: CARE's icon tree-shaking passes a backslash path to glob, finds no files, and every page then fails on a missing icon.) On every start the container registers the plugin's frontend with CARE (`PlugConfig`) at its own address (`RADSMART_PUBLIC_URL`), so neither the image nor the database depends on the address.

**Cold start:** after five quiet minutes the app scales to zero, and the next request wakes it. Azure holds that request until CARE answers: about 15 to 20 seconds (measured 13 s and 20 s on 26 Oct 2026). [`entrypoint.sh`](entrypoint.sh) opens port 8080 only once gunicorn is up, so the first page does not fail.

## The data

`init` builds the database in the local stack, in a separate database `care_azure` with its own Redis database. It runs CARE's migrations and fixtures, the synthetic demonstration data, and the Sarvam answers already kept in development, so the server does not pay for them again. Then `upload` restores it on the server with `pg_restore` and drops the local copy. If the upload fails, run `deploy.sh upload` again on its own: the local copy stays until an upload succeeds. CARE's fixture password is public, so every user gets a new random password. These are written only to the workspace's git-ignored `.agent/azure-logins.txt`.

The local machine can reach the database only while `upload` or `status` runs, through a firewall rule that is removed afterwards. The app reaches it through the "Azure services" rule.

The daily job runs at 05:30 IST. It runs any new migrations, then replaces the demonstration patients with fresh ones and plays the past days out. The live board then moves through the day as it is viewed. Anything a visitor changed, such as a Telegram link or the demonstration clock, is gone the next morning. `deploy.sh reseed` runs the job at once and waits for it.

## Secrets

`deploy.sh` reads the Sarvam key and the Telegram token and secret from the workspace's git-ignored `.agent/.env`. It generates the database password, Django's secret key and the JWT signing key into `.agent/azure.env`. Nothing is printed or committed. In Azure they are Container Apps secrets.

The public server limits Sarvam spending to 6,000 characters a day and 40,000 in all (`RADSMART_SARVAM_DAILY_CHARS`, `RADSMART_SARVAM_TOTAL_CHARS`).

## Telegram

For the demonstration, messages to patients can go out on Telegram, because WhatsApp's Business API needs a verified business. Real use sends them on WhatsApp. `webhook` points the bot at `https://<app>/api/care_radsmart/telegram/`, and Telegram proves each call with the secret token. While the webhook is set, local `radsmart_telegram --poll` does not work. Run `radsmart_telegram --no-webhook` before polling locally.

## From demonstration to pilot

The pilot uses the same image and the same script. Only configuration changes:

| | Demonstration (this server) | Pilot |
|---|---|---|
| Sign-in | One-click roles, no password (`RADSMART_OPEN_DEMO`) | Each person's own CARE account, with CARE's two-factor sign-in; open demonstration off |
| Data | Synthetic patients, renewed every morning (`RADSMART_DEMO`, the daily job) | Real courses, kept; the daily job runs migrations only |
| Where | UAE North, free services | The hospital's own server (Docker Compose, beside its CARE), or an Indian Azure region such as Central India so data stays in India |
| Size | 0.5 vCPU, 1 GiB, scales to zero | Always at least one replica during the department's hours (08:30–01:00); a larger database tier |
| Patient messages | WhatsApp, or Telegram for visitors | The department's WhatsApp |
| Sarvam | 6,000 characters a day | Sized for the department: about ₹5,000–10,000 a year |
| Backups | 7-day automatic database backups | The same, plus the hospital's own retention policy |

Before go-live: the head of department's approval, hospital IT and data-protection sign-off (DPDP Act 2023), ethics committee review, and the patient notice and consent for messaging. The pilot plan is in Section 7 of the [Phase 2 submission](../../docs/Phase2_Submission.pdf).

## Taking it down

`bash deploy/azure/deploy.sh down` deletes the resource group and everything in it, after asking. The 12-month free allowances end a year after the subscription started. Take the server down before then, or it starts using credit.
