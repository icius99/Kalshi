import unittest
from datetime import date

from historical.walkforward_compare import aggregate, score_fold


class WalkForwardTests(unittest.TestCase):
    def test_score_fold_returns_common_row_losses(self):
        train = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0, "forecast_sigma": 1.0},
            {"forecast": 65.0, "actual": 63.0, "error": -2.0, "forecast_sigma": 2.0},
            {"forecast": 70.0, "actual": 71.0, "error": 1.0, "forecast_sigma": 1.0},
        ]
        test = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0, "forecast_sigma": 1.0},
            {"forecast": 70.0, "actual": 68.0, "error": -2.0, "forecast_sigma": 2.0},
        ]
        result = score_fold(train, test)
        self.assertEqual(result["n"], 2)
        self.assertEqual(
            set(result["losses"]),
            {"empirical", "global_normal", "scaled_xnd"},
        )
        self.assertIn(result["winner"], result["losses"])

    def test_aggregate_is_sample_weighted(self):
        results = [
            {
                "n": 10,
                "winner": "empirical",
                "losses": {
                    "empirical": 2.0,
                    "global_normal": 3.0,
                    "scaled_xnd": 4.0,
                },
            },
            {
                "n": 30,
                "winner": "scaled_xnd",
                "losses": {
                    "empirical": 4.0,
                    "global_normal": 3.0,
                    "scaled_xnd": 2.0,
                },
            },
        ]
        agg = aggregate(results)
        self.assertEqual(agg["n"], 40)
        self.assertAlmostEqual(agg["mean_losses"]["empirical"], 3.5)
        self.assertAlmostEqual(agg["mean_losses"]["scaled_xnd"], 2.5)
        self.assertEqual(agg["wins"]["empirical"], 1)
        self.assertEqual(agg["wins"]["scaled_xnd"], 1)


if __name__ == "__main__":
    unittest.main()
