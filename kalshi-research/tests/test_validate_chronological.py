import unittest
from datetime import date

from historical.validate_chronological import (
    choose_test_start,
    evaluate_bucket,
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


if __name__ == "__main__":
    unittest.main()
