#!/usr/bin/env bash
# Rebuild the whole RAD-SMART development environment on a fresh machine (or after deleting the
# local folders): CARE (backend and frontend) at the pinned revisions, the plugin wiring, the
# Docker stack, CARE's fixture users, and the synthetic demonstration data.
#
#   bash workspace/restore.sh [--files-only] [--no-seed]
#
# Run it in Git Bash (Windows), macOS or Linux, from a clone of this repository.
#
#   WORKSPACE=...        where the CARE workspace goes (default: <repo>/../care-workspace/scaffold)
#   PORT_BASE=19100      first of eight consecutive ports (API, care_fe, plugin, Postgres, Redis, MinIO x2, debugger)
#   PROJECT=...          Docker Compose project name (default care_radsmart_dev)
#   SARVAM_API_KEY=...   optional; written to <workspace>/.agent/.env (git-ignored), never printed
#
# --files-only   clone and write the configuration, but do not start Docker
# --no-seed      start the stack but skip fixtures and demonstration data
set -euo pipefail

HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd -- "$HERE/.." && pwd)"
# Docker Desktop on Windows wants C:/... paths, which `cygpath -m` gives; elsewhere pwd is already right.
native() { if command -v cygpath >/dev/null 2>&1; then cygpath -m "$1"; else printf '%s' "$1"; fi; }

FILES_ONLY=0; SEED=1
for arg in "$@"; do
  case "$arg" in
    --files-only) FILES_ONLY=1 ;;
    --no-seed) SEED=0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

# shellcheck source=pins.env
source "$HERE/pins.env"
WORKSPACE="${WORKSPACE:-$(cd -- "$REPO/.." && pwd)/care-workspace/scaffold}"
PORT_BASE="${PORT_BASE:-19100}"
PROJECT="${PROJECT:-care_radsmart_dev}"

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing prerequisite: $1" >&2; exit 1; }; }
need git
if [[ $FILES_ONLY -eq 0 ]]; then
  need docker; need node; need npm
  docker compose version >/dev/null 2>&1 || { echo "Docker Compose (>= 2.24.4) is required" >&2; exit 1; }
fi

# clone <url> <dir> <ref>: fetch only the pinned commit (no history), unless it is already there.
# autocrlf stays off, set before the checkout: CRLF line endings break the shell scripts that
# run inside the containers.
clone() {
  local url="$1" dir="$2" ref="$3"
  if [[ ! -d "$dir/.git" ]]; then
    mkdir -p "$dir"
    git -C "$dir" init -q
    git -C "$dir" remote add origin "$url"
  fi
  git -C "$dir" config core.autocrlf false
  git -C "$dir" cat-file -e "$ref^{commit}" 2>/dev/null || git -C "$dir" fetch -q --depth 1 origin "$ref"
  git -C "$dir" -c advice.detachedHead=false checkout -q "$ref"
}

echo "== CARE sources (pinned)"
clone "$SCAFFOLD_URL" "$WORKSPACE" "$SCAFFOLD_REF"
clone "$CARE_URL" "$WORKSPACE/care" "$CARE_REF"
clone "$CARE_FE_URL" "$WORKSPACE/care_fe" "$CARE_FE_REF"

echo "== Workspace configuration"
WS="$(native "$WORKSPACE")"
RS="$(native "$REPO")"
p() { echo $((PORT_BASE + $1)); }
cat > "$WORKSPACE/care-scaffold.env" <<EOF
# Written by workspace/restore.sh (configure-workspace.py rejects Windows paths); same keys as its output.
WORKSPACE='$WS'
CARE_BE='$WS/care'
CARE_FE='$WS/care_fe'
COMPOSE_PROJECT_NAME='$PROJECT'
CARE_API_PORT='$(p 0)'
CARE_FE_PORT='$(p 1)'
PLUGIN_PORT='$(p 2)'
CARE_DB_PORT='$(p 3)'
CARE_REDIS_PORT='$(p 4)'
CARE_S3_PORT='$(p 5)'
CARE_S3_CONSOLE_PORT='$(p 6)'
CARE_DEBUG_PORT='$(p 7)'
CARE_API_URL='http://localhost:$(p 0)'
CARE_FE_URL='http://localhost:$(p 1)'
BACKUP_DIR='$WS/care/care-backups'
EOF
mkdir -p "$WORKSPACE/.agent"
cp "$HERE"/agent/compose.override.yaml "$HERE"/agent/compose.sh "$HERE"/agent/frontend.sh "$HERE"/agent/plugin.compose.yaml "$WORKSPACE/.agent/"
chmod +x "$WORKSPACE/.agent/compose.sh" "$WORKSPACE/.agent/frontend.sh"
cat > "$WORKSPACE/.agent/paths.env" <<EOF
PLUGIN_BE='$RS/app/care_radsmart'
RADSMART_ENGINE='$RS/poc'
PLUGIN_FE='$RS/app/care_radsmart_fe'
EOF
if [[ -n "${SARVAM_API_KEY:-}" ]]; then
  ( umask 077; printf 'SARVAM_API_KEY=%s\n' "$SARVAM_API_KEY" > "$WORKSPACE/.agent/.env" )
  echo "   Sarvam key written to .agent/.env"
elif [[ ! -f "$WORKSPACE/.agent/.env" ]]; then
  echo "   no SARVAM_API_KEY: messages will be English-only until you put one in $WORKSPACE/.agent/.env"
fi

if [[ $FILES_ONLY -eq 1 ]]; then echo "== Done (--files-only). Workspace: $WORKSPACE"; exit 0; fi

COMPOSE="$WORKSPACE/.agent/compose.sh"
echo "== Docker stack (the first build takes several minutes)"
"$COMPOSE" up -d --build --wait backend celery

if [[ $SEED -eq 1 ]]; then
  echo "== CARE fixture users and facilities"
  "$COMPOSE" exec -T backend python manage.py load_fixtures
  FACILITY="$("$COMPOSE" exec -T backend python manage.py shell -c \
    "from care.facility.models import Facility; print(Facility.objects.get(name='FACILITY WITH PATIENTS').external_id)" | tail -n 1 | tr -d '\r')"
  echo "== Synthetic RAD-SMART demonstration data for facility $FACILITY"
  "$COMPOSE" exec -T backend python manage.py radsmart_demo --facility "$FACILITY" --user care-doctor --census 60
fi

echo "== Frontend dependencies"
( cd "$WORKSPACE/care_fe" && npm install )
( cd "$REPO/app/care_radsmart_fe" && npm install )

cat <<EOF

== Ready. Start the two frontend servers in two terminals:
   1. cd "$REPO/app/care_radsmart_fe" && npm run dev        # the plugin, port $(p 2)
   2. bash "$WORKSPACE/.agent/frontend.sh"                    # care_fe, port $(p 1)
   Then open http://localhost:$(p 1) and sign in as care-doctor (CARE's fixture password).
   After editing the backend plugin: bash "$COMPOSE" restart backend
EOF
