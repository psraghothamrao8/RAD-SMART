# Reseed the demo facility for a recording take. Run inside the CARE backend container:
#   compose.sh exec -T -e FACILITY=<facility id> backend python manage.py shell < seed_demo_tz.py
# The recorder sets the browser to a time zone where it is now a working afternoon (TZ_DEMO,
# default America/Denver), so the demo day's played-out times are written in that zone's wall
# time. Earlier days stay in the server's time zone, so Insights is unchanged.
import datetime as dt
import os
import zoneinfo

from django.contrib.auth import get_user_model
from care.facility.models import Facility
from care_radsmart import demo
from care_radsmart.viewsets import clock

DEN = zoneinfo.ZoneInfo(os.environ.get("TZ_DEMO", "America/Denver"))
day, _ = clock()
now = dt.datetime.now(DEN)
minutes = now.hour * 60 + now.minute - 3
orig = demo._local
demo._local = lambda d, m: (dt.datetime.combine(d, dt.time(), tzinfo=DEN) + dt.timedelta(minutes=float(m))) if d == day else orig(d, m)
f = Facility.objects.get(external_id=os.environ["FACILITY"])
u = get_user_model().objects.get(username=os.environ.get("DOCTOR", "care-doctor"))
print("seed", day, f"{minutes // 60:02d}:{minutes % 60:02d}", demo.seed(f, u, census=60, today=day, now=minutes))
