import sqlite3
import unittest
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from paper.current_signals import (
    PaperEvaluationSkip,
    enforce_entry_window,
    latest_event,
    lead_hours_to_anchor,
    snapshot_age_minutes,
)


NY = ZoneInfo("America/New_York")


class CurrentSignalsLeadTests(unittest.TestCase):
    def test_model_lead_uses_forecast_runtime_not_market_snapshot(self):
        anchor = datetime.combine(date(2026, 10, 4), time(15), tzinfo=NY)
        nbm_runtime = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
        market_snapshot = datetime(2026, 10, 4, 18, 18, tzinfo=timezone.utc)

        model_lead = lead_hours_to_anchor(anchor, nbm_runtime)
        market_lead = lead_hours_to_anchor(anchor, market_snapshot)

        self.assertAlmostEqual(model_lead, 7.0)
        self.assertAlmostEqual(market_lead, 0.7)
        self.assertGreater(model_lead, market_lead)

    def test_snapshot_age_minutes(self):
        snapshot = datetime(2026, 10, 4, 18, 0, tzinfo=timezone.utc)
        now = datetime(2026, 10, 4, 18, 17, tzinfo=timezone.utc)
        self.assertAlmostEqual(snapshot_age_minutes(snapshot, now), 17.0)

    def test_entry_window_rejects_late_same_day_market(self):
        with self.assertRaises(PaperEvaluationSkip):
            enforce_entry_window(0.7, 3.0, 15)

    def test_entry_window_allows_early_market(self):
        enforce_entry_window(6.0, 3.0, 15)

    def test_auto_event_selection_advances_after_today_window_closes(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE market_snapshots (
                series_ticker TEXT,
                event_ticker TEXT,
                timestamp_utc TEXT
            )
            """
        )
        snapshot = "2026-10-05T02:17:06+00:00"
        conn.executemany(
            "INSERT INTO market_snapshots VALUES (?,?,?)",
            [
                ("KXHIGHNY", "KXHIGHNY-26OCT04", snapshot),
                ("KXHIGHNY", "KXHIGHNY-26OCT05", snapshot),
            ],
        )

        event, timestamp = latest_event(
            conn,
            explicit=None,
            anchor_hour=15,
            min_market_lead_hours=3.0,
        )
        self.assertEqual(event, "KXHIGHNY-26OCT05")
        self.assertEqual(timestamp, snapshot)
        conn.close()

    def test_explicit_event_is_not_auto_advanced(self):
        conn = sqlite3.connect(":memory:")
        conn.execute(
            """
            CREATE TABLE market_snapshots (
                series_ticker TEXT,
                event_ticker TEXT,
                timestamp_utc TEXT
            )
            """
        )
        snapshot = "2026-10-05T02:17:06+00:00"
        conn.execute(
            "INSERT INTO market_snapshots VALUES (?,?,?)",
            ("KXHIGHNY", "KXHIGHNY-26OCT04", snapshot),
        )
        event, _ = latest_event(
            conn,
            explicit="KXHIGHNY-26OCT04",
            anchor_hour=15,
            min_market_lead_hours=3.0,
        )
        self.assertEqual(event, "KXHIGHNY-26OCT04")
        conn.close()


if __name__ == "__main__":
    unittest.main()
