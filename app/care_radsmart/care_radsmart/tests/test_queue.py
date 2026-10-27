"""The Today board's live queue: who to call next, and out-of-turn records.

Run inside CARE:  python manage.py test care_radsmart.tests.test_queue
"""

import datetime as dt

from django.test import SimpleTestCase

from radsmart.config import hm
from radsmart.courses import SlotBook

from care_radsmart.engine import _free_but, live_queue, turn_detail


def row(pid, start, status="scheduled", machine="VERSA", arrived=None, **kw):
    return {"id": pid, "machine": machine, "start": hm(start), "minutes": 10, "status": status,
            "new_start": False, "pelvic": False, "complex": False, "mhrc": False, "accessories": [],
            "arrived": hm(arrived) if arrived else None, "in_room": None, **kw}


class LiveQueueTest(SimpleTestCase):
    def test_calls_the_first_in_plan_order_who_is_here(self):
        rows = [row("a", "10:00"), row("b", "10:10", "arrived", arrived="09:50"),
                row("c", "10:20", "arrived", arrived="09:40")]
        q = live_queue(rows, hm("10:05"))
        self.assertEqual(q["machines"]["VERSA"]["next"], "b")       # a is not here: skipped, not waited for
        self.assertEqual(q["sessions"]["a"]["late_by"], 5)
        self.assertEqual(q["machines"]["VERSA"]["not_here"], 1)

    def test_a_pelvic_patient_waits_for_the_bladder(self):
        rows = [row("p", "10:00", "arrived", arrived="09:50", pelvic=True),
                row("q", "10:10", "arrived", arrived="09:40")]
        q = live_queue(rows, hm("10:05"))
        self.assertEqual(q["machines"]["VERSA"]["next"], "q")
        self.assertIn("bladder ready at 10:20", q["sessions"]["p"]["cautions"][0])
        self.assertEqual(live_queue(rows, hm("10:20"))["machines"]["VERSA"]["next"], "p")

    def test_hospice_patients_first_from_four(self):
        rows = [row("x", "15:50", "arrived", arrived="15:30"),
                row("h", "16:10", "arrived", arrived="15:45", mhrc=True)]
        self.assertEqual(live_queue(rows, hm("15:55"))["machines"]["VERSA"]["next"], "x")
        self.assertEqual(live_queue(rows, hm("16:00"))["machines"]["VERSA"]["next"], "h")

    def test_warns_about_senior_staff_and_a_shared_accessory(self):
        rows = [row("c", "10:30", "arrived", arrived="09:00", complex=True),
                row("b", "09:40", "arrived", arrived="09:10", accessories=["ABC"]),
                row("o", "09:30", "in_room", machine="HALCYON", accessories=["ABC"])]
        q = live_queue(rows, hm("09:35"))
        self.assertEqual(q["sessions"]["c"]["cautions"], ["complex: senior staff from 10:00"])
        self.assertEqual(q["sessions"]["b"]["cautions"], ["ABC in use on Halcyon"])
        self.assertIsNone(q["machines"]["VERSA"]["next"])        # a suggestion only: both can still be taken in
        self.assertEqual(q["machines"]["HALCYON"]["in_room"], "o")

    def test_running_behind_is_the_wait_past_their_time(self):
        rows = [row("e", "09:20", "in_room", in_room=hm("09:40")),
                row("f", "09:30", "arrived", arrived="09:15"),        # on time: kept 15 min
                row("g", "09:35", "arrived", arrived="09:42"),        # came late: kept 3 min
                row("h", "10:30", "arrived", arrived="09:20")]        # early: not kept yet
        self.assertEqual(live_queue(rows, hm("09:45"))["machines"]["VERSA"]["behind_min"], 15)
        self.assertEqual(live_queue(rows[:1], hm("09:45"))["machines"]["VERSA"]["behind_min"], 0)

    def test_out_of_turn_names_who_was_skipped(self):
        rows = [row("a", "10:00"), row("b", "10:10", "arrived"), row("x", "09:50", "done"),
                row("h", "09:00", machine="HALCYON")]
        self.assertEqual(turn_detail(rows, row("c", "10:20", "arrived")),
                         (True, "ahead of 2: 1 not here, 1 waiting"))
        self.assertEqual(turn_detail(rows, row("first", "09:55")), (False, ""))
        later = rows + [row("d", "10:15")]
        self.assertEqual(turn_detail(later, row("c", "10:20", "arrived"), now=hm("10:05")),
                         (True, "ahead of 3: 1 late, 1 waiting, 1 not due yet"))


class OpenOfferTest(SimpleTestCase):
    def test_an_open_offer_keeps_its_time_from_the_next_pass(self):
        day = dt.date(2026, 11, 2)
        b = SlotBook(machines=["VERSA"])
        b.hold("a", "VERSA", day, hm("09:00"), 10)
        self.assertTrue(_free_but(b, "a", "VERSA", day, hm("09:04"), 10))    # overlaps only a's own slot
        self.assertFalse(_free_but(b, "b", "VERSA", day, hm("09:04"), 10))
        b.hold("b#open", "VERSA", day, hm("09:30"), 10)                     # b was offered 09:30
        self.assertFalse(_free_but(b, "c", "VERSA", day, hm("09:30"), 10))   # so c is not
        self.assertTrue(_free_but(b, "c", "VERSA", day, hm("09:40"), 10))
