"""The safety checks around Sarvam AI, without calling Sarvam.

Run inside CARE:  python manage.py test care_radsmart.tests.test_sarvam
"""

from types import SimpleNamespace
from unittest import mock

import requests
from django.test import SimpleTestCase

from care_radsmart import messages, sarvam


def course(phone="9876543210", demo=False):
    return SimpleNamespace(demo=demo, patient=SimpleNamespace(phone_number=phone))


def nothing_kept(cls):
    """No kept answers, nothing saved, no spending limit: the database is not used."""
    cls = mock.patch.object(sarvam, "_allow", return_value=True)(cls)
    cls = mock.patch.object(sarvam, "_save")(cls)
    return mock.patch.object(sarvam, "_load", return_value={})(cls)


class TimesTest(SimpleTestCase):
    def test_reads_times_in_any_script(self):
        # Indian scripts join a suffix straight onto the time.
        self.assertEqual(sarvam.times("ಇಂದು 16:27ಕ್ಕೆ ಬನ್ನಿ, 17:05ಕ್ಕೆ ಅಲ್ಲ"), ["16:27", "17:05"])
        self.assertEqual(sarvam.times("आज 19:44 बजे"), ["19:44"])
        self.assertEqual(sarvam.times("ഇന്ന് 21:24-ന് വരിക"), ["21:24"])

    def test_twelve_hour_times_count_as_the_same_time(self):
        self.assertEqual(sarvam.times("come at 4:30 pm or 9.05am"), ["16:30", "09:05"])

    def test_ignores_numbers_that_are_not_times(self):
        self.assertEqual(sarvam.times("fraction 16 of 25, room 123:45"), [])

    def test_same_times_needs_every_time_once(self):
        src = "Please come at 19:44 today, not at 17:02."
        self.assertTrue(sarvam.same_times(src, "ದಯವಿಟ್ಟು 17:02ಕ್ಕೆ ಅಲ್ಲ, 19:44ಕ್ಕೆ ಬನ್ನಿ."))  # order may change
        self.assertFalse(sarvam.same_times(src, "ದಯವಿಟ್ಟು 19:44ಕ್ಕೆ ಬನ್ನಿ."))                # a time dropped
        self.assertFalse(sarvam.same_times(src, "ದಯವಿಟ್ಟು 19:45ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."))  # a time changed


@nothing_kept
class TranslateTest(SimpleTestCase):
    SRC = "Radiotherapy department: please come at 19:44 today, not at 17:02."

    def test_english_patients_get_english(self, *_):
        self.assertEqual(sarvam.translate(self.SRC, "English"), (None, "english", ""))

    @mock.patch.object(sarvam, "enabled", return_value=False)
    def test_without_a_key_the_message_goes_in_english(self, *_):
        local, status, _note = sarvam.translate(self.SRC, "Kannada")
        self.assertEqual((local, status), (None, "english"))

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post", return_value={"translated_text": "ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."})
    def test_a_faithful_translation_is_used(self, *_):
        self.assertEqual(sarvam.translate(self.SRC, "Kannada")[:2], ("ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ.", "ok"))

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post", return_value={"translated_text": "ಇಂದು 7:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."})
    def test_a_translation_that_changes_a_time_is_thrown_away(self, *_):
        local, status, note = sarvam.translate(self.SRC, "Kannada")
        self.assertEqual((local, status), (None, "failed"))
        self.assertIn("changed a time", note)

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post", side_effect=requests.ConnectionError("offline"))
    def test_sarvam_unreachable_falls_back_to_english(self, *_):
        self.assertEqual(sarvam.translate(self.SRC, "Hindi")[:2], (None, "failed"))

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post", return_value={"translated_text": "ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."})
    def test_tulu_is_sent_in_kannada_with_a_note(self, post, *_):
        local, status, note = sarvam.translate(self.SRC, "Tulu")
        self.assertEqual(status, "ok")
        self.assertEqual(post.call_args[0][1]["target_language_code"], "kn-IN")
        self.assertIn("Tulu voice note", note)

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post")
    def test_past_the_spending_limit_nothing_is_sent_to_sarvam(self, post, _enabled, allow, _save, _load):
        allow.return_value = False
        local, status, note = sarvam.translate(self.SRC, "Kannada")
        self.assertEqual((local, status), (None, "failed"))
        self.assertIn("limit", note)
        post.assert_not_called()

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post")
    def test_a_kept_answer_is_not_paid_for_again(self, post, _enabled, allow, _save, load):
        load.side_effect = lambda keys: {k: "ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ." for k in keys}
        self.assertEqual(sarvam.translate(self.SRC, "Kannada")[1], "ok")
        post.assert_not_called()
        allow.assert_not_called()

    @mock.patch.object(sarvam, "enabled", return_value=True)
    @mock.patch.object(sarvam, "_post", return_value={"translated_text": "ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."})
    def test_a_new_answer_is_kept_and_counted(self, _post, _enabled, allow, save, _load):
        sarvam.translate(self.SRC, "Kannada")
        allow.assert_called_once_with(len(self.SRC))
        self.assertEqual(list(save.call_args[0][0].values()), ["ಇಂದು 19:44ಕ್ಕೆ ಬನ್ನಿ, 17:02ಕ್ಕೆ ಅಲ್ಲ."])


class RateLimitTest(SimpleTestCase):
    @mock.patch.object(sarvam.time, "sleep")
    @mock.patch.object(sarvam, "_headers", return_value={})
    def test_too_many_requests_waits_and_retries(self, _headers, sleep):
        busy = mock.Mock(status_code=429, headers={"Retry-After": "2"})
        ok = mock.Mock(status_code=200, headers={})
        ok.json.return_value = {"translated_text": "x"}
        with mock.patch.object(sarvam.requests, "post", side_effect=[busy, ok]) as post:
            self.assertEqual(sarvam._post("/translate", {}, timeout=5), {"translated_text": "x"})
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(2.0)


@nothing_kept
@mock.patch.object(sarvam, "enabled", return_value=True)
class ExplainTest(SimpleTestCase):
    FACTS = {"Every later treatment": "at 15:20, come at 14:35", "Engine's reasons": "public transport"}

    def answer(self, text):
        return mock.patch.object(sarvam, "_post", return_value={"choices": [{"message": {"content": text}}]})

    def test_an_answer_within_the_facts_is_used(self, *_):
        with self.answer("Your treatment is at 15:20, so please come at 14:35.") as post:
            text, why_not = sarvam.explain(self.FACTS)
        self.assertEqual((text, why_not), ("Your treatment is at 15:20, so please come at 14:35.", ""))
        body = post.call_args[0][1]
        self.assertIsNone(body["reasoning_effort"])
        self.assertIn("Never give medical advice", body["messages"][0]["content"])

    def test_an_invented_time_is_rejected(self, *_):
        with self.answer("Please come at 4:46 PM."):
            text, why_not = sarvam.explain(self.FACTS)
        self.assertIsNone(text)
        self.assertIn("not in the plan", why_not)

    def test_reasoning_and_markdown_are_stripped(self, *_):
        with self.answer("<think>draft</think>**Treatment** at 15:20."):
            self.assertEqual(sarvam.explain(self.FACTS)[0], "Treatment at 15:20.")

    def test_an_empty_answer_falls_back(self, *_):
        with self.answer(""):
            self.assertEqual(sarvam.explain(self.FACTS), (None, "Sarvam AI gave no answer."))


class MessagesTest(SimpleTestCase):
    def test_breakdown_messages_carry_both_times(self):
        text = messages.breakdown_text("new_time", "19:44", "17:02")
        self.assertEqual(sarvam.times(text), ["19:44", "17:02"])
        self.assertIn("do not leave home", text)

    def test_every_breakdown_action_has_a_message_or_none(self):
        for action in ("new_time", "do_not_travel", "send_home", "start_next_day"):
            self.assertTrue(messages.breakdown_text(action, "19:44", "17:02"), action)
        self.assertIsNone(messages.breakdown_text("treat", None, "17:02"))

    def test_after_approval_the_day_is_named(self):
        # "the next working day" was once translated as "next week".
        text = messages.breakdown_text("start_next_day", None, "17:02", "2026-10-27", "13:15")
        self.assertIn("Tuesday, 27 October", text)
        self.assertEqual(sarvam.times(text), ["13:15"])
        self.assertIn("on Tuesday, 27 October at your usual time, 17:02",
                      messages.breakdown_text("send_home", None, "17:02", "2026-10-27"))

    @mock.patch.object(messages.plugin_settings, "RADSMART_DEMO", False, create=True)
    def test_whatsapp_link_uses_the_indian_number(self):
        self.assertTrue(messages.whatsapp_url(course("98765 43210"), "Hi").startswith("https://wa.me/919876543210?text=Hi"))

    @mock.patch.object(messages.plugin_settings, "RADSMART_DEMO", False, create=True)
    def test_demo_patients_get_no_number(self):
        self.assertTrue(messages.whatsapp_url(course(demo=True), "Hi").startswith("https://wa.me/?text="))
        self.assertTrue(messages.whatsapp_url(course(phone="123"), "Hi").startswith("https://wa.me/?text="))
