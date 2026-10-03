import unittest
from datetime import date

from historical.settlement_basis import (
    classify_event,
    event_date,
    run_audit,
)


def event_markets():
    event = "KXHIGHNY-26SEP25"
    return [
        {"ticker": f"{event}-T63", "event_ticker": event, "cap_strike": 63, "floor_strike": None, "result": "no"},
        {"ticker": f"{event}-B63.5", "event_ticker": event, "floor_strike": 63, "cap_strike": 64, "result": "no"},
        {"ticker": f"{event}-B65.5", "event_ticker": event, "floor_strike": 65, "cap_strike": 66, "result": "no"},
        {"ticker": f"{event}-B67.5", "event_ticker": event, "floor_strike": 67, "cap_strike": 68, "result": "no"},
        {"ticker": f"{event}-B69.5", "event_ticker": event, "floor_strike": 69, "cap_strike": 70, "result": "yes"},
        {"ticker": f"{event}-T70", "event_ticker": event, "floor_strike": 70, "cap_strike": None, "result": "no"},
    ]


class SettlementBasisTests(unittest.TestCase):
    def test_event_date_supports_old_and_new_prefix(self):
        self.assertEqual(event_date("KXHIGHNY-26SEP25"), date(2026, 9, 25))
        self.assertEqual(event_date("HIGHNY-21AUG06"), date(2021, 8, 6))

    def test_matching_partition(self):
        result = classify_event(event_markets(), 69)
        self.assertTrue(result["usable"])
        self.assertTrue(result["same_bucket"])

    def test_detects_adjacent_bucket_mismatch(self):
        markets = event_markets()
        for market in markets:
            market["result"] = "yes" if market["ticker"].endswith("B67.5") else "no"
        result = classify_event(markets, 69)
        self.assertTrue(result["usable"])
        self.assertFalse(result["same_bucket"])


    def test_rejects_gapped_partition(self):
        markets = event_markets()
        markets = [
            market for market in markets
            if not market["ticker"].endswith("B67.5")
        ]
        result = classify_event(markets, 69)
        self.assertFalse(result["usable"])
        self.assertEqual(result["reason"], "gapped_partition")

    def test_rejects_overlapping_legacy_thresholds(self):
        event = "HIGHNY-22DEC01"
        markets = [
            {
                "ticker": f"{event}-T60",
                "event_ticker": event,
                "cap_strike": 60,
                "floor_strike": None,
                "result": "no",
            },
            {
                "ticker": f"{event}-T65",
                "event_ticker": event,
                "cap_strike": 65,
                "floor_strike": None,
                "result": "yes",
            },
            {
                "ticker": f"{event}-T70",
                "event_ticker": event,
                "cap_strike": 70,
                "floor_strike": None,
                "result": "no",
            },
        ]
        result = classify_event(markets, 64)
        self.assertFalse(result["usable"])

    def test_run_audit_reports_mismatch(self):
        markets = event_markets()
        for market in markets:
            market["result"] = "yes" if market["ticker"].endswith("B67.5") else "no"
        report = run_audit(
            markets,
            {date(2026, 9, 25): 69.0},
            date(2026, 9, 25),
            date(2026, 9, 25),
        )
        self.assertEqual(report["usable_events"], 1)
        self.assertEqual(report["mismatch_events"], 1)
        self.assertEqual(report["same_bucket_rate"], 0.0)


if __name__ == "__main__":
    unittest.main()
