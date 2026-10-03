import tempfile
import unittest
from pathlib import Path

from historical.audit_dataset import raw_audit


class DatasetAuditTests(unittest.TestCase):
    def test_valid_rows_pass_structural_audit(self):
        csv_text = (
            "target_date,runtime_utc,valid_utc,lead_hours,forecast_high_f,"
            "forecast_sigma_f,actual_high_f,error_f\n"
            "2026-09-25,2026-09-24T18:00:00+00:00,"
            "2026-09-26T00:00:00+00:00,25,68,2,69,1\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(csv_text, encoding="utf-8")
            result = raw_audit(path)

        self.assertEqual(result["raw_rows"], 1)
        self.assertEqual(result["structural_errors"], [])

    def test_wrong_valid_time_fails(self):
        csv_text = (
            "target_date,runtime_utc,valid_utc,lead_hours,forecast_high_f,"
            "forecast_sigma_f,actual_high_f,error_f\n"
            "2026-09-25,2026-09-24T18:00:00+00:00,"
            "2026-09-25T12:00:00+00:00,25,55,2,69,14\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "x.csv"
            path.write_text(csv_text, encoding="utf-8")
            result = raw_audit(path)

        self.assertTrue(result["structural_errors"])


if __name__ == "__main__":
    unittest.main()
