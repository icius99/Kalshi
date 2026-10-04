import unittest
from datetime import date

from historical.validate_chronological import (
    choose_test_start,
    evaluate_bucket,
    fit_xnd_scale,
    rounded_temperature_probability,
)


class ChronologicalValidationTests(unittest.TestCase):
    def test_auto_split_is_chronological(self):
        rows = [
            {"target_date": date(2026, 1, day)}
            for day in range(1, 9)
        ]
        self.assertEqual(choose_test_start(rows, None, 0.75), date(2026, 1, 7))

    def test_probability_is_positive(self):
        self.assertGreater(rounded_temperature_probability(65, 65, 2), 0)

    def test_evaluate_bucket_uses_train_bias_only(self):
        train = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0},
            {"forecast": 65.0, "actual": 67.0, "error": 2.0},
            {"forecast": 70.0, "actual": 70.0, "error": 0.0},
        ]
        test = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0},
            {"forecast": 70.0, "actual": 71.0, "error": 1.0},
        ]
        stats = evaluate_bucket(train, test)
        self.assertAlmostEqual(stats["train_bias_f"], 1.0)
        self.assertAlmostEqual(stats["test_corrected_bias_f"], 0.0)

    def test_fit_xnd_scale_uses_training_errors_only(self):
        rows = [
            {"error": 2.0, "forecast_sigma": 2.0},
            {"error": -4.0, "forecast_sigma": 2.0},
        ]
        scale, n = fit_xnd_scale(rows)
        self.assertEqual(n, 2)
        self.assertAlmostEqual(scale, (2.5) ** 0.5)

    def test_evaluate_bucket_scores_xnd_holdout(self):
        train = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0, "forecast_sigma": 1.0},
            {"forecast": 65.0, "actual": 63.0, "error": -2.0, "forecast_sigma": 2.0},
            {"forecast": 70.0, "actual": 71.0, "error": 1.0, "forecast_sigma": 1.0},
        ]
        test = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0, "forecast_sigma": 1.0},
            {"forecast": 70.0, "actual": 68.0, "error": -2.0, "forecast_sigma": 2.0},
        ]
        stats = evaluate_bucket(train, test)
        self.assertEqual(stats["xnd_train_n"], 3)
        self.assertEqual(stats["xnd_test_n"], 2)
        self.assertIsNotNone(stats["xnd_scale"])
        self.assertIsNotNone(stats["mean_scaled_xnd_log_loss"])
        self.assertIsNotNone(stats["scaled_xnd_coverage_90"])

    def test_evaluate_bucket_compares_txn_on_holdout(self):
        train = [
            {"forecast": 60.0, "actual": 61.0, "error": 1.0},
            {"forecast": 65.0, "actual": 64.0, "error": -1.0},
            {"forecast": 70.0, "actual": 71.0, "error": 1.0},
        ]
        test = [
            {
                "forecast": 60.0,
                "actual": 61.0,
                "error": 1.0,
                "txn_error": 5.0,
            },
            {
                "forecast": 70.0,
                "actual": 69.0,
                "error": -1.0,
                "txn_error": -4.0,
            },
        ]
        stats = evaluate_bucket(train, test)
        self.assertEqual(stats["test_txn_n"], 2)
        self.assertLess(stats["test_raw_rmse_f"], stats["test_txn_rmse_f"])
        self.assertLess(stats["test_raw_mae_f"], stats["test_txn_mae_f"])


if __name__ == "__main__":
    unittest.main()
