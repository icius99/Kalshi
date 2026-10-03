import unittest
from datetime import date, datetime, timezone

from research.nbm import select_forecast_asof


class NBMSelectionTests(unittest.TestCase):
    def test_latest_runtime_not_after_snapshot(self):
        rows = [
            {
                "runtime": "2026-10-03T12:00:00Z",
                "ftime": "2026-10-04T23:00:00Z",
                "txn": "65",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-03T18:00:00Z",
                "ftime": "2026-10-04T23:00:00Z",
                "txn": "66",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-04T00:00:00Z",
                "ftime": "2026-10-04T23:00:00Z",
                "txn": "67",
                "xnd": "2",
            },
        ]
        selected = select_forecast_asof(
            rows,
            date(2026, 10, 4),
            datetime(2026, 10, 3, 20, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["forecast_high_f"], 66.0)
        self.assertEqual(selected["runtime_utc"].hour, 18)


if __name__ == "__main__":
    unittest.main()
