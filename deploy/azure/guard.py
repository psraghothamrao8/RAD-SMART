"""Keeps the demonstration server's Azure bill inside a monthly budget.

Azure Container Apps bills a replica by the second, in vCPU-seconds and
GiB-seconds, beyond a free grant of 180,000 vCPU-s and 360,000 GiB-s a month
per subscription: 100 hours at this app's 0.5 vCPU and 1 GiB. A replica that
runs because the app keeps a minimum of one ("warm") pays the idle vCPU rate,
an eighth of the active one, for the seconds it is idle (no requests, under
0.01 vCPU, under 1,000 bytes a second in). Memory costs the same either way.
A replica woken by a visit, with a minimum of zero, pays the active rate for
every second.

    python guard.py           # in the app: count each awake minute, act on the count
    python guard.py --check   # in the daily job: the same decisions, once
    python guard.py --status  # deploy.sh status: this month's count and estimate

Each minute the guard adds the minute's vCPU-seconds, active or idle, and
GiB-seconds to the day's row in the database. Activity is sampled every five
seconds from the container's CPU and network counters. The calendar month (UTC,
the subscription's billing month) is priced at the Consumption rates, with only
85% of the free grant counted. That leaves room for the daily job and for
starting up, which are not counted.

- Until RADSMART_WARM_UNTIL (a UTC date), the month may cost
  RADSMART_BUDGET_USD. From 05:30 (the daily job) to 23:00 IST, while the
  month is at least $1 under that budget, the app keeps one replica warm, so
  nobody waits for it to start. Otherwise it scales to zero when nobody uses it.
- From that date on, the budget is nothing: the app scales to zero and lives on
  the free grant.
- When the month costs more than the budget, the app's ingress is made internal,
  so nothing outside reaches it and it scales to zero. The daily job opens it
  again in the next month.

Changes go through Azure Resource Manager with the app's managed identity.
Without RADSMART_APP_ID (a local run) nothing is counted.
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request

import psycopg

TICK, SAMPLE = 60, 5
APP_ID = os.environ.get("RADSMART_APP_ID", "")
BUDGET = float(os.environ.get("RADSMART_BUDGET_USD") or 0)
WARM_UNTIL = dt.date.fromisoformat(os.environ.get("RADSMART_WARM_UNTIL") or "2000-01-01")
RESERVE = 1.0                        # dollars kept back from warming, for visits once it stops
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
WARM_HOURS = range(5, 23)            # 05:00 to 23:00 IST; the daily job runs at 05:30

# Consumption rates (UAE North, Nov 2026) and the monthly free grant, of which 85% is counted.
CPU_ACTIVE, CPU_IDLE, MEMORY = 0.000024, 0.000003, 0.000003     # $ per vCPU-s, vCPU-s, GiB-s
GRANT_CPU, GRANT_MEMORY, SHARE = 180_000, 360_000, 0.85

ARM = "https://management.azure.com"
API = "2024-03-01"


def log(msg: str) -> None:
    print(f"guard: {msg}", flush=True)


def today() -> dt.date:
    return dt.datetime.now(dt.UTC).date()


def budget() -> float:
    return BUDGET if today() < WARM_UNTIL else 0.0


# ------------------------------------------------------------------ counting
def prepare(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("CREATE TABLE IF NOT EXISTS radsmart_awake "
                    "(day date PRIMARY KEY, seconds integer NOT NULL DEFAULT 0)")
        for col in ("cpu_active", "cpu_idle", "memory"):
            cur.execute(f"ALTER TABLE radsmart_awake ADD COLUMN IF NOT EXISTS {col} "
                        "double precision NOT NULL DEFAULT 0")
        # Days counted before the guard priced them: woken by visits, at 0.5 vCPU and 1 GiB.
        cur.execute("UPDATE radsmart_awake SET cpu_active = seconds * 0.5, memory = seconds "
                    "WHERE memory = 0 AND seconds > 0")


def add(conn, seconds: int, cpu_active: float, cpu_idle: float, memory: float) -> None:
    with conn.cursor() as cur:
        cur.execute("INSERT INTO radsmart_awake AS a (day, seconds, cpu_active, cpu_idle, memory) "
                    "VALUES (%s, %s, %s, %s, %s) ON CONFLICT (day) DO UPDATE SET "
                    "seconds = a.seconds + EXCLUDED.seconds, cpu_active = a.cpu_active + EXCLUDED.cpu_active, "
                    "cpu_idle = a.cpu_idle + EXCLUDED.cpu_idle, memory = a.memory + EXCLUDED.memory",
                    (today(), seconds, cpu_active, cpu_idle, memory))


def month(conn) -> tuple[float, float, float, float]:
    """This month's awake seconds, active and idle vCPU-seconds, and GiB-seconds."""
    with conn.cursor() as cur:
        cur.execute("SELECT coalesce(sum(seconds), 0), coalesce(sum(cpu_active), 0), "
                    "coalesce(sum(cpu_idle), 0), coalesce(sum(memory), 0) FROM radsmart_awake "
                    "WHERE day >= %s", (today().replace(day=1),))
        return tuple(float(v) for v in cur.fetchone())


def price(cpu_active: float, cpu_idle: float, memory: float) -> float:
    """The month's bill in dollars. The grant is spent on idle seconds first: the dearer guess."""
    grant = GRANT_CPU * SHARE
    idle, grant = max(0.0, cpu_idle - grant), max(0.0, grant - cpu_idle)
    active = max(0.0, cpu_active - grant)
    return active * CPU_ACTIVE + idle * CPU_IDLE + max(0.0, memory - GRANT_MEMORY * SHARE) * MEMORY


def cost(conn) -> float:
    return price(*month(conn)[1:])


def _cpu_seconds() -> float | None:
    """CPU time the container has used: cgroup v2 or v1 (Azure gives v1)."""
    try:
        with open("/sys/fs/cgroup/cpu.stat") as f:
            return next(int(l.split()[1]) / 1e6 for l in f if l.startswith("usage_usec"))
    except (OSError, StopIteration):
        pass
    try:
        with open("/sys/fs/cgroup/cpuacct/cpuacct.usage") as f:
            return int(f.read()) / 1e9
    except OSError:
        return None


def _bytes_in() -> int | None:
    try:
        with open("/proc/net/dev") as f:
            rows = [l.split(":", 1) for l in f if ":" in l]
        return sum(int(v.split()[0]) for k, v in rows if k.strip() != "lo")
    except OSError:
        return None


def measure() -> int:
    """Wait one tick and return how many of its seconds were active by Azure's idle rule."""
    active = 0
    cpu, net = _cpu_seconds(), _bytes_in()
    for _ in range(TICK // SAMPLE):
        time.sleep(SAMPLE)
        cpu2, net2 = _cpu_seconds(), _bytes_in()
        if None in (cpu, cpu2, net, net2) or cpu2 - cpu > 0.01 * SAMPLE or net2 - net > 1000 * SAMPLE:
            active += SAMPLE
        cpu, net = cpu2, net2
    return active


# ----------------------------------------------------------------- the app
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


def set_warm(warm: bool, app: dict | None = None) -> bool:
    """Keep one replica (warm) or none. The scale is part of the template, so Azure
    starts a new revision, and this container is replaced. True if it changed."""
    template = (app or _arm("GET"))["properties"]["template"]
    if bool(template["scale"].get("minReplicas")) == warm:
        return False
    template = {k: v for k, v in template.items() if k != "revisionSuffix"}
    template["scale"] = {**template["scale"], "minReplicas": int(warm)}
    _arm("PATCH", {"properties": {"template": template}})
    return True


def want_warm(spent: float, public: bool) -> bool:
    return public and today() < WARM_UNTIL and spent + RESERVE <= budget() \
        and dt.datetime.now(IST).hour in WARM_HOURS


def size(app: dict) -> tuple[float, float, bool]:
    """vCPU, GiB, and whether a replica is kept warm (Azure then bills idle seconds as idle)."""
    tpl = app["properties"]["template"]
    res = tpl["containers"][0]["resources"]
    return float(res["cpu"]), float(str(res["memory"]).rstrip("Gi")), bool(tpl["scale"].get("minReplicas"))


def check(conn) -> None:
    """Open or close the app and warm it or not by this month's cost, unless it
    was paused by hand (deploy.sh pause tags it radsmart-paused=yes)."""
    spent, app = cost(conn), _arm("GET")
    paused = (app.get("tags") or {}).get("radsmart-paused") == "yes"
    public = spent <= budget() and not paused
    opened = set_public(public, app)
    warm = want_warm(spent, public)
    warmed = set_warm(warm, app)
    log(f"${spent:.2f} of ${budget():.2f} this month{'; paused by hand' if paused else ''}: "
        f"{'opened' if opened and public else 'closed' if opened else 'left'} {'public' if public else 'internal'}, "
        f"{'now ' if warmed else ''}{'warm' if warm else 'scaling to zero'}")


def run() -> None:
    try:
        app = _arm("GET")
        cpu, memory, warm = size(app)
        public = bool(app["properties"]["configuration"]["ingress"].get("external")) \
            and (app.get("tags") or {}).get("radsmart-paused") != "yes"
    except Exception as exc:               # count as a woken replica: the dearer guess
        log(f"reading the app: {type(exc).__name__}: {exc}")
        cpu, memory, warm, public = 0.5, 1.0, False, False
    log(f"{cpu} vCPU, {memory} GiB, {'warm' if warm else 'scales to zero'}")
    conn, stopping, n, failed, tried = None, False, 0, 0, 0.0
    while True:
        active = measure()                 # one tick
        if not warm:                       # a woken replica pays the active rate throughout
            active = TICK
        try:
            if conn is None or conn.closed:
                conn = psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=20)
                prepare(conn)
            add(conn, TICK, cpu * active, cpu * (TICK - active), memory * TICK)
            spent = cost(conn)
            n, failed = n + 1, 0
            if n % 60 == 1:
                log(f"${spent:.2f} of ${budget():.2f} this month")
            if spent > budget() and not stopping:
                log("the month's budget is spent: making the app internal")
                set_public(False)
                set_warm(False)
                stopping = True
            elif not stopping and want_warm(spent, public) != warm and time.time() - tried > 600:
                tried = time.time()        # Azure replaces this container once it takes
                log("keeping a replica warm" if not warm else "letting the app scale to zero")
                set_warm(not warm)
        except Exception as exc:           # a failed count does not stop the server at once ...
            log(f"{type(exc).__name__}: {exc}")
            conn, failed = None, failed + 1
            if failed >= 60 and not stopping:   # ... but an hour of uncounted time does
                try:
                    log("nothing counted for an hour: making the app internal")
                    set_public(False)
                    set_warm(False)
                    stopping = True
                except Exception as exc2:
                    log(f"{type(exc2).__name__}: {exc2}")


def status(conn) -> None:
    seconds, cpu_active, cpu_idle, memory = month(conn)
    until = f"warm 05:30-23:00 IST until {WARM_UNTIL}" if today() < WARM_UNTIL else "free grant only"
    print(f"{seconds / 3600:.1f} h awake this month, about ${price(cpu_active, cpu_idle, memory):.2f} "
          f"of ${budget():.2f} ({until})")


if __name__ == "__main__":
    if "--status" in sys.argv:
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=20) as c:
            prepare(c)
            status(c)
        sys.exit(0)
    if not APP_ID:
        log("RADSMART_APP_ID is not set; not counting")
        sys.exit(0)
    if "--check" in sys.argv:
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, connect_timeout=20) as c:
            prepare(c)
            check(c)
    else:
        run()
