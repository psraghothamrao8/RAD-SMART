"""The Telegram bot's safety, without calling Telegram.

Run inside CARE:  python manage.py test care_radsmart.tests.test_telegram
"""

import uuid
from types import SimpleNamespace
from unittest import mock

import requests
from django.http import Http404
from django.test import RequestFactory, SimpleTestCase

from care_radsmart import telegram
from care_radsmart.patient import LABELS


def labels():
    words = {**LABELS, **telegram.TEXT}
    return words | {"bare": words}


@mock.patch.object(telegram.plugin_settings, "RADSMART_TELEGRAM_TOKEN", "123:SECRET-TOKEN", create=True)
class TelegramTest(SimpleTestCase):
    def test_every_button_fits_telegrams_64_bytes(self):
        course = SimpleNamespace(external_id=uuid.uuid4())
        for menu in ("main", "late", "time"):
            for row in telegram._keyboard(course, labels(), menu)["inline_keyboard"]:
                for b in row:
                    self.assertLessEqual(len(b["callback_data"].encode()), 64, b)

    def test_an_error_never_shows_the_token(self):
        with mock.patch.object(telegram.requests, "post",
                               side_effect=requests.ConnectionError("https://api.telegram.org/bot123:SECRET-TOKEN/x")):
            with self.assertRaises(telegram.TelegramError) as caught:
                telegram.call("getMe")
        self.assertNotIn("SECRET-TOKEN", str(caught.exception))
        self.assertIsNone(caught.exception.__cause__)

    @mock.patch.object(telegram.plugin_settings, "RADSMART_TELEGRAM_SECRET", "hook-secret", create=True)
    def test_the_webhook_needs_telegrams_secret(self):
        view = telegram.Webhook.as_view()
        for header in ({}, {"HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN": "wrong"}):
            with self.assertRaises(Http404):
                view(RequestFactory().post("/hook", data="{}", content_type="application/json", **header))
        with mock.patch.object(telegram, "handle") as handle:
            r = view(RequestFactory().post("/hook", data='{"update_id": 1}', content_type="application/json",
                                           HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN="hook-secret"))
        self.assertEqual(r.status_code, 200)
        handle.assert_called_once_with({"update_id": 1})

    def test_a_button_for_a_course_not_linked_to_this_chat_does_nothing(self):
        q = {"id": "q1", "data": f"w:{uuid.uuid4()}:", "message": {"chat": {"id": 42}, "message_id": 7}}
        none = mock.MagicMock()
        none.select_related.return_value.filter.return_value.first.return_value = None
        with mock.patch.object(telegram.Course, "objects", none), \
                mock.patch.object(telegram, "call") as call, \
                mock.patch("care_radsmart.patient.record_reply") as record:
            telegram._button(q)
        record.assert_not_called()
        call.assert_called_once_with("answerCallbackQuery", {"callback_query_id": "q1"})
        self.assertEqual(none.select_related.return_value.filter.call_args.kwargs["telegram_chat"], 42)
