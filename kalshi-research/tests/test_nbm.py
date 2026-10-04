import unittest
from datetime import date, datetime, timezone

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

    def test_early_morning_tmp_can_override_txn_for_calendar_day(self):
        rows = [
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-04T06:00:00Z",
                "tmp": "56",
                "tsd": "3",
            },
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-04T09:00:00Z",
                "tmp": "52",
                "tsd": "2",
            },
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-05T00:00:00Z",
                "txn": "42",
                "xnd": "7",
            },
        ]
        forecasts = extract_daily_high_forecasts(
            rows,
            "America/New_York",
            15,
        )
        self.assertEqual(len(forecasts), 1)
        forecast = forecasts[0]
        self.assertEqual(forecast["target_date"], date(2022, 2, 4))
        self.assertEqual(forecast["forecast_high_f"], 56.0)
        self.assertEqual(forecast["forecast_sigma_f"], 3.0)
        self.assertEqual(forecast["forecast_source"], "early_tmp")
        self.assertEqual(forecast["txn_high_f"], 42.0)

    def test_tmp_before_local_midnight_is_not_used(self):
        rows = [
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-04T03:00:00Z",
                "tmp": "60",
                "tsd": "2",
            },
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-04T06:00:00Z",
                "tmp": "40",
                "tsd": "2",
            },
            {
                "runtime": "2022-02-03T00:00:00Z",
                "ftime": "2022-02-05T00:00:00Z",
                "txn": "42",
                "xnd": "4",
            },
        ]
        forecasts = extract_daily_high_forecasts(
            rows,
            "America/New_York",
            15,
        )
        self.assertEqual(forecasts[0]["forecast_high_f"], 42.0)
        self.assertEqual(forecasts[0]["forecast_source"], "txn")


if __name__ == "__main__":
    unittest.main()
