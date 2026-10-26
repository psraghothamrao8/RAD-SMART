"""Sarvam AI spending, and the kept answers.

    python manage.py radsmart_sarvam --usage
    python manage.py radsmart_sarvam --from-redis           # answers cached before they were kept in the database
    python manage.py radsmart_sarvam --export answers.jsonl
    python manage.py radsmart_sarvam --import answers.jsonl  # e.g. into a new server, so nothing is paid for twice

The kept answers hold translations of the department's messages and labels and
their voice notes; nothing that names a patient is sent to Sarvam.
"""

import base64
import json

from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db.models import Sum

from care_radsmart import sarvam
from care_radsmart.models import SarvamResult, SarvamUsage
from care_radsmart.settings import plugin_settings


class Command(BaseCommand):
    help = "Show Sarvam usage, or move the kept Sarvam answers between servers"

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--usage", action="store_true")
        group.add_argument("--from-redis", action="store_true")
        group.add_argument("--export", metavar="FILE")
        group.add_argument("--import", dest="import_", metavar="FILE")

    def handle(self, *args, **opts):
        if opts["usage"]:
            for u in SarvamUsage.objects.order_by("day"):
                self.stdout.write(f"{u.day}  {u.chars:>8} characters  {u.calls:>5} calls")
            total = SarvamUsage.objects.aggregate(n=Sum("chars"))["n"] or 0
            self.stdout.write(f"total {total} characters; limits: {plugin_settings.RADSMART_SARVAM_DAILY_CHARS or 'none'}"
                              f" a day, {plugin_settings.RADSMART_SARVAM_TOTAL_CHARS or 'none'} in all; "
                              f"{SarvamResult.objects.count()} answers kept")
        elif opts["from_redis"]:
            keys = list(cache.iter_keys("radsmart:sarvam:*"))
            found = sarvam._load(keys)          # reading moves them into the database
            self.stdout.write(self.style.SUCCESS(f"{len(found)} of {len(keys)} cached answers kept"))
        elif opts["export"]:
            with open(opts["export"], "w", encoding="utf-8") as f:
                for r in SarvamResult.objects.order_by("created").iterator():
                    audio = base64.b64encode(bytes(r.audio)).decode() if r.audio is not None else None
                    f.write(json.dumps({"key": r.key, "text": r.text, "audio": audio}, ensure_ascii=False) + "\n")
            self.stdout.write(self.style.SUCCESS(f"{SarvamResult.objects.count()} answers written"))
        else:
            with open(opts["import_"], encoding="utf-8") as f:
                rows = [json.loads(line) for line in f if line.strip()]
            sarvam._save({r["key"]: base64.b64decode(r["audio"]) if r["audio"] else r["text"] for r in rows})
            self.stdout.write(self.style.SUCCESS(f"{len(rows)} answers read; {SarvamResult.objects.count()} kept"))
