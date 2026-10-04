import tempfile
import unittest
from pathlib import Path

from historical.sampling import load_bucketed_rows, nearest_bucket


class SamplingTests(unittest.TestCase):
    def test_nearest_bucket(self):
        self.assertEqual(nearest_bucket(25, (12, 24, 36), 5), 24)
        self.assertIsNone(nearest_bucket(30, (12, 24, 36), 5))

    def test_one_forecast_per_target_and_bucket(self):
        csv_text = (
            "target_date,runtime_utc,valid_utc,lead_hours,forecast_high_f,"
            "forecast_sigma_f,actual_high_f,error_f\n"
            "2026-09-25,a,v,19,70,3,69,-1\n"
            "2026-09-25,b,v,25,69,2,69,0\n"
            "2026-09-26,c,v,25,71,2,72,1\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(csv_text, encoding="utf-8")
            rows = load_bucketed_rows(path, (24,), 5)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["lead_hours"], 25.0)
        self.assertEqual(rows[0]["error"], 0.0)

    def test_calendar_high_diagnostics_are_retained(self):
        csv_text = (
            "target_date,runtime_utc,valid_utc,lead_hours,forecast_high_f,"
            "forecast_sigma_f,forecast_source,txn_high_f,txn_error_f,"
            "early_tmp_high_f,actual_high_f,error_f\n"
            "2026-09-25,a,v,25,72,3,early_tmp,68,1,72,69,-3\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(csv_text, encoding="utf-8")
            rows = load_bucketed_rows(path, (24,), 5)

        self.assertEqual(rows[0]["forecast_source"], "early_tmp")
        self.assertEqual(rows[0]["txn_forecast"], 68.0)
        self.assertEqual(rows[0]["txn_error"], 1.0)
        self.assertEqual(rows[0]["early_tmp_forecast"], 72.0)


if __name__ == "__main__":
    unittest.main()
