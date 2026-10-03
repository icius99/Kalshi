import unittest

from research.error_model import ForecastErrorModel


class ErrorModelTests(unittest.TestCase):
    def setUp(self):
        self.model = ForecastErrorModel({"buckets": {
            "12": {"n":100,"bias_f":0.1,"sd_error_f":1.2},
            "24": {"n":100,"bias_f":0.2,"sd_error_f":2.0},
        }})

    def test_nearest(self):
        self.assertEqual(self.model.nearest(21).lead_hours, 24)

    def test_distance_guard(self):
        with self.assertRaises(ValueError):
            self.model.nearest(40, max_distance=8)


if __name__ == "__main__":
    unittest.main()
