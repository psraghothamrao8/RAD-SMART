# Rebuild the development environment

Everything needed to get back to a running RAD-SMART after deleting the local folders is in this repository. The one thing not in it is the CARE database, which `restore.sh` fills again.

## From nothing to a running app

You need Git (Git Bash on Windows), Docker Desktop (Compose 2.24.4 or newer), and Node.js 20 or newer. About 15 GB of disk space and 10 minutes, most of it the first Docker build.

```bash
git clone https://github.com/psraghothamrao8/RAD-SMART.git
cd RAD-SMART
SARVAM_API_KEY=your-key bash workspace/restore.sh      # the key is optional
```

For the Telegram demonstration, also pass `RADSMART_TELEGRAM_TOKEN=...` and `RADSMART_TELEGRAM_SECRET=...`. Each key given replaces only its own line in `.agent/.env`, so running it again with one key keeps the others.

`restore.sh` does this, in order:

1. Fetches CARE's backend, CARE's frontend and care_scaffold at the exact commits in [`pins.env`](pins.env), next to the repository in `../care-workspace/scaffold`. Line-ending conversion is switched off for them, because CRLF breaks the shell scripts that run inside the containers.
2. Writes `care-scaffold.env` (ports 19100-19107, project `care_radsmart_dev`) and `.agent/paths.env`, and copies in the four files in [`agent/`](agent/): the compose wrapper, its port overrides, the plugin registration and the care_fe launcher. A Sarvam key or Telegram keys, if you pass them, go to `.agent/.env`, which is git-ignored and never printed.
3. Builds and starts the stack (`backend`, `celery`, Postgres, Redis, MinIO). Celery's start-up runs the migrations, including the plugin's.
4. Loads CARE's fixture users and facilities, then fills the facility *FACILITY WITH PATIENTS* with the synthetic RAD-SMART demonstration data (`radsmart_demo`, 60 patients).
5. Runs `npm install` for care_fe and for the frontend plugin.

On the first build Docker prints `pull access denied for <project>_backend`. It is harmless: Compose tries to pull the image, finds none, and builds it.

Then start the two frontend servers, in two terminals (the script prints the exact lines):

```bash
cd app/care_radsmart_fe && npm run dev                 # the plugin, port 19102
bash ../care-workspace/scaffold/.agent/frontend.sh     # care_fe, port 19101
```

Open <http://localhost:19101> and sign in as `care-doctor` (CARE's development fixture password).

| Option | Effect |
|---|---|
| `WORKSPACE=...` | put the CARE workspace somewhere else |
| `PORT_BASE=19200` `PROJECT=name` | use other ports and another Compose project, to run next to an existing stack |
| `--files-only` | fetch the sources and write the configuration, but do not start Docker |
| `--no-seed` | start the stack without fixtures or demonstration data |

After editing the backend plugin, run `bash ../care-workspace/scaffold/.agent/compose.sh restart backend`: bind-mounted file changes do not reach the container's auto-reloader on Windows.

## Other things that rebuild from this repository

| What | How |
|---|---|
| Website, deck, user guide, papers | already in `docs/`; `tools/build_docs.py`, `tools/build_deck.py` rebuild the PDFs. Python dependencies: `pip install -r poc/requirements.txt` |
| Demo video | [`tools/demo-video/README.md`](../tools/demo-video/README.md). The narration audio is committed, so no Sarvam credit is needed. `tools/demo-video/scripts/ids.py` prints the three ids the recording needs, and `prep_take.py` frees the recording patient before another take |
| Phase 2 submission slides | `python tools/build_submission.py` (needs the organisers' template, see below) |
| Public demonstration server | `bash deploy/azure/deploy.sh all` with this stack running (see [`deploy/azure/README.md`](../deploy/azure/README.md)). Its secrets and logins stay in `.agent/azure.env` and `.agent/azure-logins.txt` |

## What is deliberately not in GitHub

| Item | Why | If you lost it |
|---|---|---|
| Sarvam API key (`.agent/.env`) | a secret | create a new key in the Sarvam dashboard and pass it to `restore.sh`, or put `SARVAM_API_KEY=...` in `.agent/.env` |
| `additional_details.docx`, the department's spreadsheet, `RAD-SMART.pdf` | the department's private material and contact details | ask the team leader for the originals; none is needed to run the app |
| `docs/Health-a-thon 2026 Submission Template.pptx` | the organisers' file | download it again from the organisers; only `tools/build_submission.py` needs it, and the finished `docs/RAD-SMART_Phase2_Submission.pptx` is committed |
| The CARE database (Docker volume `care_radsmart_dev_postgres-data`) | it only holds fixtures and synthetic data | `restore.sh` recreates it; anything typed into the app by hand is lost |
| Screencast frames (`tools/demo-video/public/rec/`) | large and rebuilt | record again; the finished video is committed |
| The pitch-deck master on claude.ai | not a file | `docs/deck/src/` holds the slides |

## Pinned versions

| Repository | Commit |
|---|---|
| ohcnetwork/care_scaffold | `a3ecf5e` |
| ohcnetwork/care | `2bae933` |
| ohcnetwork/care_fe | `4ad8f01` |

`restore.sh` was run end to end from empty folders on spare ports (19200-19207) on 25 Oct 2026: the stack came up healthy, the plugin's API answered, and the demonstration data gave 96 courses and 10 users. The fixtures give their patients new random names each time; the video scripts (`ids.py`, `prep_take.py`) find the recording patient by role, not by name.

Tested with Docker 29.6, Compose 5.2, Node 24.18, Python 3.12 on Windows 11.
