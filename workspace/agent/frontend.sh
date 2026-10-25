#!/usr/bin/env bash
# Start the host frontend (care_fe) with the RAD-SMART plugin enabled.
set -euo pipefail
STACK_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
set -a
source "$STACK_DIR/../care-scaffold.env"
set +a
cd "$CARE_FE"
export REACT_CARE_API_URL="http://localhost:${CARE_API_PORT}"
export REACT_ENABLED_APPS="ohcnetwork/care_radsmart_fe@localhost:${PLUGIN_PORT}/assets/remoteEntry.js"
exec npm run dev -- --host 127.0.0.1 --port "$CARE_FE_PORT" --strictPort
