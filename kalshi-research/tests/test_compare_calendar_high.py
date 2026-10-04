import unittest

from historical.compare_calendar_high import summarize


class CalendarHighComparisonTests(unittest.TestCase):
    def test_hybrid_improvement_is_measured_on_same_rows(self):
        rows = [
            {
                "error": 1.0,
                "txn_error": 5.0,
                "forecast_source": "early_tmp",
            },
            {
                "error": -1.0,
                "txn_error": -1.0,
                "forecast_source": "txn",
            },
        ]
        stats = summarize(rows)
        self.assertEqual(stats["n"], 2)
        self.assertEqual(stats["early_tmp_n"], 1)
        self.assertLess(stats["hybrid_rmse"], stats["txn_rmse"])
        self.assertLess(stats["hybrid_mae"], stats["txn_mae"])


if __name__ == "__main__":
    unittest.main()
