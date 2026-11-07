"""The public demonstration's front door and its clock, without a database.

Run inside CARE:  python manage.py test care_radsmart.tests.test_tryout
"""

import datetime as dt
from types import SimpleNamespace
from unittest import mock

from django.http import Http404
from django.test import RequestFactory, SimpleTestCase
from django.utils import timezone

from care_radsmart import demo, tryout
from care_radsmart.viewsets import clock


class FakeRefresh(str):
    access_token = "ACCESS.</script><b>"

    @classmethod
    def for_user(cls, user):
        return cls("REFRESH")


class TryoutTest(SimpleTestCase):
    def test_closed_unless_the_demonstration_is_open(self):
        with mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO", True, create=True), \
                mock.patch.object(tryout.plugin_settings, "RADSMART_OPEN_DEMO", False, create=True):
            for view, args in ((tryout.TryPage, ()), (tryout.TryEnter, ("doctor",)), (tryout.TryPatient, ())):
                with self.assertRaises(Http404):
                    view.as_view()(RequestFactory().get("/try/"), *args)

    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO", True, create=True)
    @mock.patch.object(tryout.plugin_settings, "RADSMART_OPEN_DEMO", True, create=True)
    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO_USERS", "doctor:care-doctor", create=True)
    def test_one_click_signs_in_as_the_role_and_opens_its_page(self):
        users = mock.MagicMock()
        users.objects.filter.return_value.first.return_value = SimpleNamespace(username="care-doctor")
        with mock.patch.object(tryout, "get_user_model", return_value=users), \
                mock.patch.object(tryout, "RefreshToken", FakeRefresh), \
                mock.patch.object(tryout, "_facility", return_value=SimpleNamespace(external_id="f-1")):
            page = tryout.TryEnter.as_view()(RequestFactory().get("/try/doctor/"), "doctor").content.decode()
            with self.assertRaises(Http404):      # a role with no account
                tryout.TryEnter.as_view()(RequestFactory().get("/try/reception/"), "reception")
        users.objects.filter.assert_called_with(username="care-doctor", is_active=True)
        self.assertIn('localStorage.setItem(\'care_refresh_token\', "REFRESH")', page)
        self.assertIn('location.replace("/facility/f-1/radsmart/courses/new")', page)
        self.assertNotIn("</script><b>", page)    # a value never closes the script
        with mock.patch.object(tryout, "get_user_model", return_value=users), \
                mock.patch.object(tryout, "RefreshToken", FakeRefresh), \
                mock.patch.object(tryout, "_facility", return_value=SimpleNamespace(external_id="f-1")):
            step = tryout.TryEnter.as_view()(RequestFactory().get("/try/doctor/?to=breakdown"), "doctor").content.decode()
            elsewhere = tryout.TryEnter.as_view()(RequestFactory().get("/try/doctor/?to=//evil.example"), "doctor")
        self.assertIn('location.replace("/facility/f-1/radsmart/breakdown")', step)     # a tour step's page
        self.assertIn('location.replace("/facility/f-1/radsmart/courses/new")', elsewhere.content.decode())

    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO", True, create=True)
    @mock.patch.object(tryout.plugin_settings, "RADSMART_OPEN_DEMO", True, create=True)
    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO_USERS", "reception:care-staff", create=True)
    def test_the_patients_code_goes_on_to_reception_and_nothing_else_does(self):
        users = mock.MagicMock()
        users.objects.filter.return_value.first.return_value = SimpleNamespace(username="care-staff")

        def open_(query):
            with mock.patch.object(tryout, "get_user_model", return_value=users), \
                    mock.patch.object(tryout, "RefreshToken", FakeRefresh), \
                    mock.patch.object(tryout, "_facility", return_value=SimpleNamespace(external_id="f-1")):
                return tryout.TryEnter.as_view()(RequestFactory().get(f"/try/reception/{query}"), "reception").content.decode()

        self.assertIn('location.replace("/facility/f-1/radsmart/checkin?code=K7QX2M")', open_("?to=checkin&code=K7QX2M"))
        for bad in ("k7qx2m", "K7QX2", "K7QX2M%22%3E", "K7QX2M%0A"):      # only six capitals or digits
            self.assertIn('location.replace("/facility/f-1/radsmart/checkin")', open_(f"?to=checkin&code={bad}"))
        self.assertIn('location.replace("/facility/f-1/radsmart/breakdown")', open_("?to=breakdown&code=K7QX2M"))

    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO", True, create=True)
    @mock.patch.object(tryout.plugin_settings, "RADSMART_OPEN_DEMO", True, create=True)
    def test_signing_in_at_care_opens_radsmart_not_care_home(self):
        with mock.patch.object(tryout, "_facility", return_value=SimpleNamespace(external_id="f-1")):
            page = tryout.TrySignIn.as_view()(RequestFactory().get("/try/signin/")).content.decode()
        self.assertIn("localStorage.removeItem('care_refresh_token')", page)     # out of any demonstration account
        # CARE's login takes ?redirect= only as a whole address on its own site.
        self.assertIn("location.replace('/login?redirect=' + encodeURIComponent(location.origin + "
                      '"/facility/f-1/radsmart"));', page)

    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO_USERS",
                       "doctor:care-doctor,reception:care-staff,technologist:care-staff", create=True)
    def test_the_shared_password_names_each_account_once(self):
        self.assertEqual(tryout.logins(), [("Doctor", "care-doctor"), ("Reception and technologist", "care-staff")])
        with mock.patch.object(tryout.plugin_settings, "RADSMART_OPEN_DEMO", False, create=True), \
                mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO_PASSWORD", "x", create=True):
            self.assertEqual(tryout.set_demo_passwords(), [])           # never outside an open demonstration

    @mock.patch.object(tryout.plugin_settings, "RADSMART_DEMO", True, create=True)
    def test_a_fresh_day_runs_the_clock_apart_and_writes_played_out_times_back(self):
        ahead = dt.timedelta(hours=-9, minutes=-20)
        with mock.patch.object(demo, "shift", return_value=ahead):
            _, minutes = clock()
            real = timezone.localtime(timezone.now() + ahead)
            self.assertLessEqual(abs(minutes % 1440 - (real.hour * 60 + real.minute)), 1)
            day = dt.date(2026, 10, 26)
            self.assertEqual(demo._local(day, 630),
                             timezone.make_aware(dt.datetime(2026, 10, 26, 10, 30)) - ahead)
