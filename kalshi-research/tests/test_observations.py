import unittest
from datetime import date, datetime, timezone

from research.observations import (
    conservative_minimum_settlement_high,
    fetch_observed_high_asof,
)


class FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {
            "features": [
                {
                    "properties": {
                        "timestamp": "2026-10-04T16:51:00+00:00",
                        "temperature": {"value": 17.0},
                    }
                },
                {
                    "properties": {
                        "timestamp": "2026-10-04T18:51:00+00:00",
                        "temperature": {"value": 20.0},
                    }
                },
                {
                    "properties": {
                        "timestamp": "2026-10-04T19:51:00+00:00",
                        "temperature": {"value": 25.0},
                    }
                },
            ]
        }


class FakeSession:
    def get(self, *args, **kwargs):
        return FakeResponse()


class ObservationTests(unittest.TestCase):
    def test_fetch_high_does_not_look_past_snapshot(self):
        result = fetch_observed_high_asof(
            date(2026, 10, 4),
            datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc),
            session=FakeSession(),
        )
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["observed_high_f"], 68.0)
        self.assertEqual(result["observation_count"], 2)

    def test_future_target_has_no_observation_floor(self):
        result = fetch_observed_high_asof(
            date(2026, 10, 5),
            datetime(2026, 10, 4, 19, 0, tzinfo=timezone.utc),
            session=FakeSession(),
        )
        self.assertIsNone(result)

    def test_conservative_settlement_floor(self):
        self.assertEqual(conservative_minimum_settlement_high(65.8, 1.0), 64)
        self.assertEqual(conservative_minimum_settlement_high(63.0, 1.0), 62)


if __name__ == "__main__":
    unittest.main()
