"""Quick checks of the scheduling engine, on synthetic patients.

    cd poc && python -m unittest discover -s tests -v      # under a minute
"""

import unittest

from radsmart.duration_model import LookupPredictor, QuantileGBMPredictor, evaluate
from radsmart.scheduler import DayScheduler, check_plan
from radsmart.synth import make_day, make_history


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


if __name__ == "__main__":
    unittest.main()
