#!/usr/bin/env bash
# All stack operations must use this wrapper, including build, exec, logs and down.
set -euo pipefail
STACK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$STACK_DIR/../care-scaffold.env"
# Load this workspace's independent plugin repository paths.
if [[ -f "$STACK_DIR/paths.env" ]]; then
  source "$STACK_DIR/paths.env"
fi
# Secrets kept out of every repository (e.g. SARVAM_API_KEY).
if [[ -f "$STACK_DIR/.env" ]]; then
  source "$STACK_DIR/.env"
fi
set +a
compose_version="$(docker compose version --short)"
if [[ ! "$compose_version" =~ ^v?([0-9]+)\.([0-9]+)\.([0-9]+) ]]; then
  echo "Cannot determine Docker Compose version: $compose_version" >&2
  exit 1
fi
major=${BASH_REMATCH[1]} minor=${BASH_REMATCH[2]} patch=${BASH_REMATCH[3]}
if (( major < 2 || (major == 2 && minor < 24) || (major == 2 && minor == 24 && patch < 4) )); then
  echo "Docker Compose >= 2.24.4 is required for isolated port overrides." >&2
  exit 1
fi
if [[ -f "$STACK_DIR/plugin.compose.yaml" ]]; then
  set -- -f "$STACK_DIR/plugin.compose.yaml" "$@"
fi
exec docker compose \
  --project-name "$COMPOSE_PROJECT_NAME" \
  --project-directory "$CARE_BE" \
  --env-file "$STACK_DIR/../care-scaffold.env" \
  -f "$CARE_BE/docker-compose.yaml" \
  -f "$CARE_BE/docker-compose.local.yaml" \
  -f "$STACK_DIR/compose.override.yaml" "$@"
