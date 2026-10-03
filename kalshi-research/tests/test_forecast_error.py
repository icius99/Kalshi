import unittest

from historical.forecast_error import kalshi_bucket_probabilities, nearest_bucket


class ForecastErrorTests(unittest.TestCase):
    def test_nearest_bucket(self):
        self.assertEqual(nearest_bucket(23.5, (12, 24, 36), 5), 24)
        self.assertIsNone(nearest_bucket(30, (12, 24, 36), 5))

    def test_probabilities_sum_to_one(self):
        probs = kalshi_bucket_probabilities(65.0, 0.0, 2.0)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=12)
        self.assertGreater(probs["65-66"], probs[">=71"])


if __name__ == "__main__":
    unittest.main()
