"""Keeps the demonstration server inside Azure's free monthly grant.

Azure Container Apps bills every second a replica runs beyond a free grant of
180,000 vCPU-seconds and 360,000 GiB-seconds a month per subscription: 100
hours at this app's 0.5 vCPU and 1 GiB. The app scales to zero when nobody
uses it, but a browser left open on the live board keeps it awake.

    python guard.py           # in the app: count each awake minute, stop when over
    python guard.py --check   # in the daily job: stop or resume by the count

The awake minutes are counted per day in the database. When the last 31 days
(any billing month fits in them) reach RADSMART_AWAKE_HOURS (default 85, which
leaves room for the daily job and for starting up), the app's ingress is made
internal through Azure Resource Manager with the app's managed identity, so
nothing outside reaches it and it scales to zero. The daily job opens it again
once the 31 days are back under the limit. Without RADSMART_APP_ID (a local
run) nothing is counted.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request

import psycopg

TICK = 60
LIMIT = float(os.environ.get("RADSMART_AWAKE_HOURS") or 85) * 3600
APP_ID = os.environ.get("RADSMART_APP_ID", "")
ARM = "https://management.azure.com"
API = "2024-03-01"


def log(msg: str) -> None:
    print(f"guard: {msg}", flush=True)


def awake(conn, add: int = 0) -> int:
    """Add `add` seconds to today and return the last 31 days' total."""
    today = dt.datetime.now(dt.UTC).date()
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS radsmart_awake "
                    "(day date PRIMARY KEY, seconds integer NOT NULL DEFAULT 0)")
        if add:
            cur.execute("INSERT INTO radsmart_awake (day, seconds) VALUES (%s, %s) ON CONFLICT (day) "
                        "DO UPDATE SET seconds = radsmart_awake.seconds + EXCLUDED.seconds", (today, add))
        cur.execute("SELECT coalesce(sum(seconds), 0) FROM radsmart_awake WHERE day > %s",
                    (today - dt.timedelta(days=31),))
        return int(cur.fetchone()[0])


def _arm(method: str, body: dict | None = None) -> dict:
    url = (f"{os.environ['IDENTITY_ENDPOINT']}?resource={ARM}/&api-version=2019-08-01")
    req = urllib.request.Request(url, headers={"X-IDENTITY-HEADER": os.environ["IDENTITY_HEADER"]})
    with urllib.request.urlopen(req, timeout=30) as r:
        token = json.load(r)["access_token"]
    req = urllib.request.Request(f"{ARM}{APP_ID}?api-version={API}", method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    return json.loads(raw) if raw else {}


def set_public(public: bool, app: dict | None = None) -> bool:
    """Make the app's ingress external (public) or internal. True if it changed."""
    ingress = (app or _arm("GET"))["properties"]["configuration"]["ingress"]
    if bool(ingress.get("external")) == public:
        return False
    ingress = {k: v for k, v in ingress.items() if k != "fqdn"}
    ingress["external"] = public
    _arm("PATCH", {"properties": {"configuration": {"ingress": ingress}}})
    return True


def check(conn) -> None:
    """Close the app when over the allowance, open it when back under, unless
    it was paused by hand (deploy.sh pause tags it radsmart-paused=yes)."""
    used, app = awake(conn), _arm("GET")
    paused = (app.get("tags") or {}).get("radsmart-paused") == "yes"
    public = used < LIMIT and not paused
    changed = set_public(public, app)
    log(f"{used / 3600:.1f} of {LIMIT / 3600:.0f} h in 31 days{'; paused by hand' if paused else ''}: "
        f"{'opened' if changed and public else 'closed' if changed else 'left'} "
        f"{'public' if public else 'internal'}")


def run() -> None:
    conn, stopping, n, failed = None, False, 0, 0
    while True:
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=20)
            used = awake(conn, TICK)       # this minute, counted up front
            n, failed = n + 1, 0
            if n % 60 == 1:
                log(f"awake {used / 3600:.1f} of {LIMIT / 3600:.0f} h in the last 31 days")
            if used >= LIMIT and not stopping:
                log("the free allowance is used up: making the app internal")
                set_public(False)
                stopping = True
        except Exception as exc:           # a failed count does not stop the server at once ...
            log(f"{type(exc).__name__}: {exc}")
            conn, failed = None, failed + 1
            if failed >= 60 and not stopping:   # ... but an hour of uncounted time does
                try:
                    log("nothing counted for an hour: making the app internal")
                    set_public(False)
                    stopping = True
                except Exception as exc2:
                    log(f"{type(exc2).__name__}: {exc2}")
        time.sleep(TICK)


if __name__ == "__main__":
    if not APP_ID:
        log("RADSMART_APP_ID is not set; not counting")
        sys.exit(0)
    if "--check" in sys.argv:
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=20) as c:
            check(c)
    else:
        run()
