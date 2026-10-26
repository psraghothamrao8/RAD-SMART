#!/bin/bash
# The demonstration container.
#
#   entrypoint.sh            serve: Redis (CARE's cache; nothing is kept), gunicorn with CARE
#                            and the plugin, nginx on port 8080, and the awake-time guard
#   entrypoint.sh reseed     the daily job: fresh demonstration data, then the guard's check
#   entrypoint.sh CMD ...    anything else, e.g. python manage.py shell
set -euo pipefail
cd /app

redis() { redis-server --bind 127.0.0.1 --port 6379 --save "" --appendonly no --dir /tmp --loglevel warning "$@"; }

# CARE loads the plugin's frontend from the address in PlugConfig. It is set to this
# server's address on every start, so a new address needs no new database; CARE's
# cached copy is in the Redis started here, empty until the first request.
register_plugin() {
  python - <<'EOF' || echo "plugin registration failed; CARE keeps the address it had"
import json, os, psycopg
url = os.environ["RADSMART_PUBLIC_URL"].rstrip("/")
meta = {"url": f"{url}/plugins/radsmart/assets/remoteEntry.js", "name": "care_radsmart_fe",
        "package": "ohcnetwork/care_radsmart_fe", "localPath": "/plugins/radsmart"}
with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=20) as conn:
    conn.execute("INSERT INTO users_plugconfig (slug, meta) VALUES ('care_radsmart_fe', %s::jsonb) "
                 "ON CONFLICT (slug) DO UPDATE SET meta = EXCLUDED.meta", (json.dumps(meta),))
EOF
}

case "${1:-serve}" in
  serve)
    register_plugin & registering=$!
    redis &
    gunicorn --config python:config.gunicorn config.wsgi:application --bind 127.0.0.1:9000 --chdir=/app \
      --workers "${GUNICORN_WORKERS:-2}" --worker-class gthread --threads 4 --timeout 90 \
      --access-logfile - --error-logfile - &
    # nginx opens port 8080 only once CARE answers, so Azure holds the request
    # that woke the app until then instead of passing it to a server still starting.
    for _ in $(seq 120); do
      (exec 3<>/dev/tcp/127.0.0.1/9000) 2>/dev/null && break
      sleep 1
    done
    wait "$registering"
    nginx -g "daemon off;" &
    python /srv/guard.py &
    disown        # the guard never stops the container
    wait -n       # any server stopping stops the container, and Azure starts a new one
    ;;
  reseed)
    redis --daemonize yes
    status=0
    python manage.py radsmart_demo --facility "$RADSMART_FACILITY" --user "${RADSMART_DEMO_USER:-care-doctor}" \
      --census "${RADSMART_CENSUS:-60}" || status=$?
    python /srv/guard.py --check || true
    exit "$status"
    ;;
  *)
    exec "$@"
    ;;
esac
