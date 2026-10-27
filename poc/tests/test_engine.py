"""Quick checks of the scheduling engine, on synthetic patients.

    cd poc && python -m unittest discover -s tests -v      # under a minute
"""

import datetime as dt
import unittest
from dataclasses import replace

from radsmart.config import hm
from radsmart.courses import Course, SlotAllocator, SlotBook, treatment_dates
from radsmart.duration_model import LookupPredictor, QuantileGBMPredictor, evaluate
from radsmart.scheduler import DayScheduler, check_plan
from radsmart.synth import Patient, make_day, make_history


class DurationModelTest(unittest.TestCase):
    def test_learned_model_beats_a_table_of_averages(self):
        hist = make_history(n_sessions=3000)
        train, test = hist[:2500], hist[2500:]
        lookup = LookupPredictor().fit(train)
        ml = QuantileGBMPredictor().fit(train)
        ev = evaluate([lookup, ml], test)
        self.assertLess(ev[ml.name]["mae_min"], ev[lookup.name]["mae_min"])


class DayPlanTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.predictor = LookupPredictor().fit(make_history(n_sessions=3000))

    def plan(self, n_patients):
        day = make_day(seed=7, n_patients=n_patients)
        return day, DayScheduler().solve(day, self.predictor)

    def test_busy_day_keeps_every_hard_rule(self):
        day, schedule = self.plan(87)
        check = check_plan(day, schedule)
        self.assertGreater(check["rules_checked"], 0)
        self.assertEqual(check["violations"], [])

    def test_everyone_gets_a_time(self):
        day, schedule = self.plan(60)
        self.assertEqual(schedule.unscheduled(), [])


def _patient(pid, **kw):
    return Patient(**{**dict(pid=pid, technique="3DCRT", site="THORAX", machine="VERSA", fraction_no=2,
                             total_fx=20, new_start=False, complex=False, accessories=[], mobility="walking",
                             imaging="kv", age=50, eligible=["VERSA"]), **kw})


class TimeBandTest(unittest.TestCase):
    """Morning, afternoon or evening: asked at intake, offered when slots free up."""
    START = dt.date(2026, 11, 2)

    def course(self, book, pid, at, fractions=20, **kw):
        dates = treatment_dates(self.START, fractions)
        c = Course(_patient(pid, **kw), self.START, fractions, dates=dates, first=("VERSA", at),
                   first_minutes=20, slots=[(dates[1], "VERSA", at, None)], minutes=10)
        book.add_course(c)
        return c

    def morning_with_one_gap(self, book):
        """The whole morning booked except 10:00-10:10, on every date."""
        for date in treatment_dates(self.START, 20):
            book.hold("busy", "VERSA", date, hm("08:30"), 90)
            book.hold("busy", "VERSA", date, hm("10:10"), 110)

    def test_band_costs_only_outside_it(self):
        sch = DayScheduler()
        p = _patient("p", band="morning", age=75)
        inside = sch._soft_cost(p, hm("09:00"), hm("09:10"), None, standing=True)
        outside = sch._soft_cost(p, hm("18:00"), hm("18:10"), None, standing=True)
        self.assertLess(inside, 0.1)
        self.assertGreater(outside, 10)
        # a stated band replaces "older patients earlier": an evening band costs nothing in the evening
        evening = replace(p, band="evening")
        self.assertLess(sch._soft_cost(evening, hm("18:00"), hm("18:10"), None, standing=True), 0.1)

    def test_offers_a_freed_slot_inside_the_band(self):
        book = SlotBook()
        self.morning_with_one_gap(book)
        c = self.course(book, "evening-now", hm("19:00"), band="morning")
        alloc = SlotAllocator(book, None)
        found = alloc.better_time(c, c.dates[5])
        self.assertIsNotNone(found)
        machine, start, _ = found
        self.assertEqual((machine, start), ("VERSA", hm("10:00")))
        # no offer once that gap is taken on even one remaining date
        book.hold("other", "VERSA", c.dates[-1], hm("10:00"), 10)
        self.assertIsNone(alloc.better_time(c, c.dates[5]))

    def test_a_short_reserve_is_never_made_shorter(self):
        """The afternoon is full, so the new-start reserve is already short: a
        move may take a morning gap too small for a new start, not a big one."""
        book = SlotBook()
        for date in treatment_dates(self.START, 20):
            book.hold("busy", "VERSA", date, hm("08:30"), 60)        # free 09:30-09:50: too small for a new start
            book.hold("busy", "VERSA", date, hm("09:50"), 130)       # free 12:00-12:40: one new start fits
            book.hold("busy", "VERSA", date, hm("12:40"), 260)
        c = self.course(book, "evening-now", hm("19:00"), band="morning")
        self.assertEqual(SlotAllocator(book, None).better_time(c, c.dates[5])[1], hm("09:30"))
        afternoon = self.course(book, "evening-too", hm("19:20"), band="afternoon")
        self.assertIsNone(SlotAllocator(book, None).better_time(afternoon, afternoon.dates[5]))

    def test_no_offer_for_the_last_few_fractions_or_inside_the_band(self):
        book = SlotBook()
        c = self.course(book, "nearly-done", hm("19:00"), band="morning")
        alloc = SlotAllocator(book, None)
        self.assertIsNone(alloc.better_time(c, c.dates[-3]))
        self.assertIsNotNone(alloc.better_time(c, c.dates[-4]))
        inside = self.course(book, "happy", hm("09:00"), band="morning")
        self.assertIsNone(alloc.better_time(inside, inside.dates[5]))

    def test_one_slot_goes_to_one_patient(self):
        book = SlotBook()
        self.morning_with_one_gap(book)
        a = self.course(book, "general", hm("19:00"), band="morning")
        b = self.course(book, "paying", hm("19:20"), band="morning", paying=True)
        offers = SlotAllocator(book, None).better_times([a, b], lambda c: c.dates[5])
        self.assertEqual([(c.pid, st) for c, _, st, _, _ in offers], [("paying", hm("10:00"))])


if __name__ == "__main__":
    unittest.main()
