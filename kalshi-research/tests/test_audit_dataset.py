import unittest
from datetime import date

from historical.audit_dataset import audit


class HistoricalAuditTests(unittest.TestCase):
    def test_audit_accepts_consistent_rows(self):
        rows = [
            {
                "target_date": date(2026, 9, 25),
                "runtime_utc": "2026-09-24T18:00:00+00:00",
                "valid_utc": "2026-09-26T00:00:00+00:00",
                "lead_hours": 25.0,
                "forecast_high_f": 70.0,
                "forecast_sigma_f": 3.0,
                "actual_high_f": 69.0,
                "error_f": -1.0,
            }
        ]
        result = audit(rows, tolerance=5.0)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["by_lead"][24]["n"], 1)

    def test_audit_catches_error_mismatch(self):
        rows = [
            {
                "target_date": date(2026, 9, 25),
                "runtime_utc": "2026-09-24T18:00:00+00:00",
                "valid_utc": "2026-09-26T00:00:00+00:00",
                "lead_hours": 25.0,
                "forecast_high_f": 70.0,
                "forecast_sigma_f": 3.0,
                "actual_high_f": 69.0,
                "error_f": 5.0,
            }
        ]
        result = audit(rows, tolerance=5.0)
        self.assertTrue(any("error mismatch" in issue for issue in result["issues"]))

    def test_off_horizon_raw_cycle_is_not_structural_error(self):
        rows = [
            {
                "target_date": date(2026, 3, 14),
                "runtime_utc": "2026-03-11T21:00:00+00:00",
                "valid_utc": "2026-03-15T00:00:00+00:00",
                "lead_hours": 66.0,
                "forecast_high_f": 55.0,
                "forecast_sigma_f": 3.0,
                "actual_high_f": 57.0,
                "error_f": 2.0,
            }
        ]
        result = audit(rows, tolerance=5.0)
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["unbucketed_raw_rows"], 1)
        self.assertEqual(result["unbucketed_leads"], {66.0: 1})


if __name__ == "__main__":
    unittest.main()
