"""The public demonstration's front door (RADSMART_OPEN_DEMO, on top of RADSMART_DEMO).

    /api/care_radsmart/try/                 two ways in: the demonstration, and real use
    /api/care_radsmart/try/<role>/          one click, signed in as that role's demonstration account
    /api/care_radsmart/try/patient/         a demonstration patient's own page
    /api/care_radsmart/try/signin/          real use: signed out of the demonstration, at CARE's sign-in
    POST /api/care_radsmart/try/restart/    a fresh demonstration day, its clock at a working hour

Synthetic patients and demonstration accounts only: never switch this on where
real patients are treated or real staff sign in.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import threading

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from rest_framework_simplejwt.tokens import RefreshToken

from radsmart.config import fmt

from care.facility.models import Facility

from care_radsmart import messages
from care_radsmart.models import Course
from care_radsmart.settings import plugin_settings

# Where each role starts in the app, under /facility/<id>/.
START = {"doctor": "radsmart/courses/new", "reception": "radsmart/checkin", "technologist": "radsmart"}
DAY_START, DAY_END = 8 * 60, 17 * 60 + 30     # the department's working day, as the demonstration shows it
FRESH_AT = 10 * 60 + 30                       # a fresh day starts here, with the morning played out
BUSY = "care_radsmart:demo_restart"           # a fresh day is being made
RECENT = "care_radsmart:demo_restarted"       # one fresh day per few minutes, whoever asks


def _open() -> None:
    if not (plugin_settings.RADSMART_DEMO and plugin_settings.RADSMART_OPEN_DEMO):
        raise Http404


def _facility() -> Facility:
    fid = plugin_settings.RADSMART_DEMO_FACILITY
    f = (Facility.objects.filter(external_id=fid).first() if fid else
         Facility.objects.filter(id__in=Course.objects.filter(demo=True).values("facility_id")[:1]).first())
    if f is None:
        raise Http404
    return f


def _users() -> dict[str, str]:
    pairs = (p.split(":", 1) for p in plugin_settings.RADSMART_DEMO_USERS.split(",") if ":" in p)
    return {role.strip(): name.strip() for role, name in pairs}


def _script(value) -> str:
    """A value for an inline script: JSON, and never a closing tag."""
    return json.dumps(value).replace("<", "\\u003c")


@method_decorator(csrf_exempt, name="dispatch")
class TryPage(View):
    def get(self, request):
        _open()
        from care_radsmart.viewsets import clock
        day, now = clock()
        ctx = {
            "day": day.strftime("%a %d %b").replace(" 0", " "), "now": fmt(now),
            "under_way": DAY_START <= now < DAY_END, "busy": bool(cache.get(BUSY)),
            "recent": bool(cache.get(RECENT)), "fresh_at": fmt(FRESH_AT),
            "dept": plugin_settings.RADSMART_DEPARTMENT, "telegram": bool(plugin_settings.RADSMART_TELEGRAM_TOKEN),
        }
        r = render(request, "care_radsmart/try.html", ctx)
        r["Cache-Control"] = "no-store"
        return r


class TryEnter(View):
    """Signs the browser in as the role's demonstration account, as CARE's own login
    would (its tokens in this site's local storage), and opens the role's page."""

    def get(self, request, role):
        _open()
        name = _users().get(role)
        if role not in START or not name:
            raise Http404
        user = get_user_model().objects.filter(username=name, is_active=True).first()
        if user is None:
            raise Http404
        refresh = RefreshToken.for_user(user)
        target = f"/facility/{_facility().external_id}/{START[role]}"
        page = (
            "<!doctype html><meta charset=utf-8><meta name=robots content='noindex, nofollow'>"
            "<title>RAD-SMART</title><p style='font:16px system-ui;margin:2em'>Signing in…</p><script>"
            f"localStorage.setItem('care_access_token', {_script(str(refresh.access_token))});"
            f"localStorage.setItem('care_refresh_token', {_script(str(refresh))});"
            f"location.replace({_script(target)});</script>"
        )
        return HttpResponse(page, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


class TrySignIn(View):
    """Real use: CARE's own sign-in, signed out of any demonstration account first."""

    def get(self, request):
        _open()
        page = ("<!doctype html><meta charset=utf-8><meta name=robots content='noindex, nofollow'><title>RAD-SMART</title>"
                "<script>localStorage.removeItem('care_access_token');localStorage.removeItem('care_refresh_token');"
                "location.replace('/login');</script>")
        return HttpResponse(page, headers={"Cache-Control": "no-store"})


class TryPatient(View):
    """A demonstration patient's own page: one still to come today, if there is one."""

    def get(self, request):
        _open()
        from care_radsmart.viewsets import clock
        day, now = clock()
        courses = Course.objects.filter(facility=_facility(), demo=True, status="approved")
        course = (courses.filter(sessions__date=day, sessions__status="scheduled", sessions__today_start__isnull=True,
                                 sessions__planned_start__gt=now + 20).order_by("sessions__planned_start").first()
                  or courses.filter(sessions__date__gt=day).first())
        if course is None:
            raise Http404
        return HttpResponseRedirect(messages.page_url(messages.ensure_link(course), request))


@method_decorator(csrf_exempt, name="dispatch")
class TryRestart(View):
    """A fresh demonstration day: new synthetic patients, and the clock set to a working
    hour (10:30, or `time` between 08:00 and 16:30) until the next morning's reseed."""

    def post(self, request):
        _open()
        start = FRESH_AT
        if request.POST.get("time"):
            try:
                h, m = request.POST["time"].split(":")
                start = int(h) * 60 + int(m)
            except ValueError:
                start = -1
            if not DAY_START <= start <= 16 * 60 + 30:
                return HttpResponse("time: 08:00 to 16:30", status=400)
        if not cache.add(RECENT, 1, timeout=5 * 60):
            return HttpResponseRedirect("../")   # someone has just started one
        facility = _facility()
        doctor = get_user_model().objects.get(username=_users()["doctor"])
        cache.set(BUSY, 1, timeout=15 * 60)
        threading.Thread(target=_fresh_day, args=(facility, doctor, start), daemon=True).start()
        return HttpResponseRedirect("../")


def _fresh_day(facility, doctor, start) -> None:
    from care_radsmart.demo import seed, set_shift
    from care_radsmart.viewsets import clock
    try:
        set_shift(dt.timedelta(0))
        day, _ = clock()
        at = timezone.make_aware(dt.datetime.combine(day, dt.time()) + dt.timedelta(minutes=start))
        set_shift(at - timezone.now())
        seed(facility, doctor, census=int(os.environ.get("RADSMART_CENSUS") or 60), today=day, now=start)
    finally:
        cache.delete(BUSY)
        connection.close()   # this thread's own connection
