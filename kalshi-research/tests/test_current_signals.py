import unittest
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

from paper.current_signals import lead_hours_to_anchor


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


if __name__ == "__main__":
    unittest.main()
