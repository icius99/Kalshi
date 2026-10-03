import unittest
from datetime import date, datetime, timedelta, timezone

from historical.build_nbm_history import extract_daily_high_forecasts
from research.nbm import select_forecast_asof


class NBMSelectionTests(unittest.TestCase):
    def test_latest_runtime_not_after_snapshot(self):
        rows = [
            {
                "runtime": "2026-10-03T12:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
                "txn": "65",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-03T18:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
                "txn": "66",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-04T00:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
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
        self.assertEqual(selected["target_date"], date(2026, 10, 4))

    def test_publication_lag_blocks_too_fresh_cycle(self):
        rows = [
            {
                "runtime": "2026-10-03T12:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
                "txn": "65",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-03T18:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
                "txn": "66",
                "xnd": "2",
            },
        ]
        selected = select_forecast_asof(
            rows,
            date(2026, 10, 4),
            datetime(2026, 10, 3, 18, 30, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["runtime_utc"].hour, 12)

        selected = select_forecast_asof(
            rows,
            date(2026, 10, 4),
            datetime(2026, 10, 3, 19, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["runtime_utc"].hour, 18)

    def test_12z_txn_is_minimum_and_ignored(self):
        rows = [
            {
                "runtime": "2026-10-03T00:00:00Z",
                "ftime": "2026-10-04T12:00:00Z",
                "txn": "55",
                "xnd": "2",
            },
            {
                "runtime": "2026-10-03T00:00:00Z",
                "ftime": "2026-10-05T00:00:00Z",
                "txn": "66",
                "xnd": "2",
            },
        ]
        forecasts = extract_daily_high_forecasts(
            rows,
            "America/New_York",
            15,
        )
        self.assertEqual(len(forecasts), 1)
        self.assertEqual(forecasts[0]["forecast_high_f"], 66.0)
        self.assertEqual(forecasts[0]["target_date"], date(2026, 10, 4))


if __name__ == "__main__":
    unittest.main()
