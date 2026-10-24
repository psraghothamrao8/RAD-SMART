"""Fill a facility with synthetic RAD-SMART demonstration data.

    python manage.py radsmart_demo --facility <facility external id> --user care-doctor [--census 60] [--time HH:MM]
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from care.facility.models import Facility

from care_radsmart.demo import seed
from care_radsmart.viewsets import clock


class Command(BaseCommand):
    help = "Synthetic patients, courses and today's events for a demonstration facility"

    def add_arguments(self, parser):
        parser.add_argument("--facility", required=True)
        parser.add_argument("--user", required=True, help="username recorded as the approving doctor")
        parser.add_argument("--census", type=int, default=60)
        parser.add_argument("--time", default=None, help="play today out up to this time (HH:MM; default now)")

    def handle(self, *args, **opts):
        try:
            facility = Facility.objects.get(external_id=opts["facility"])
            user = get_user_model().objects.get(username=opts["user"])
        except (Facility.DoesNotExist, get_user_model().DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        day, now = clock()
        if opts["time"]:
            h, m = opts["time"].split(":")
            now = int(h) * 60 + int(m)
        out = seed(facility, user, census=opts["census"], today=day, now=now)
        self.stdout.write(self.style.SUCCESS(str(out)))
