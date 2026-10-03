import unittest
from datetime import datetime, timezone

from historical.price_backtest import (
    best_trade,
    decimal_close,
    prior_error_counts,
    quote_at,
    settle_trade,
)


class PriceBacktestTests(unittest.TestCase):
    def test_decimal_close_supports_live_and_historical_shapes(self):
        self.assertEqual(decimal_close({"close_dollars": "0.42"}), 0.42)
        self.assertEqual(decimal_close({"close": "0.43"}), 0.43)

    def test_quote_at_never_uses_future_candle(self):
        candles = [
            {
                "end_period_ts": 1000,
                "yes_bid": {"close": "0.40"},
                "yes_ask": {"close": "0.45"},
            },
            {
                "end_period_ts": 2000,
                "yes_bid": {"close": "0.50"},
                "yes_ask": {"close": "0.55"},
            },
        ]
        asof = datetime.fromtimestamp(1500, tz=timezone.utc)
        quote = quote_at(candles, asof, max_staleness_hours=1)
        self.assertEqual(quote["yes_ask"], 0.45)
        self.assertEqual(quote["end_period_ts"], 1000)

    def test_prior_error_counts_excludes_not_yet_completed_day(self):
        rows = {
            24: [
                {"target_date": datetime(2026, 9, 23).date(), "error": -1.0},
                {"target_date": datetime(2026, 9, 24).date(), "error": 2.0},
            ]
        }
        asof = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
        counts = prior_error_counts(rows, 24, asof)
        self.assertEqual(counts[-1], 1)
        self.assertEqual(counts[2], 0)

    def test_best_trade_uses_ask_fees_and_buffer(self):
        markets = [
            {
                "ticker": "KXHIGHNY-X-B65.5",
                "result": "yes",
            }
        ]
        probabilities = {"KXHIGHNY-X-B65.5": 0.70}
        quotes = {
            "KXHIGHNY-X-B65.5": {
                "yes_bid": 0.49,
                "yes_ask": 0.50,
                "end_period_ts": 1,
            }
        }
        trade = best_trade(
            markets,
            probabilities,
            quotes,
            min_edge=0.05,
            execution_buffer=0.01,
        )
        self.assertIsNotNone(trade)
        self.assertEqual(trade["side"], "YES")
        self.assertGreater(trade["edge"], 0.05)

    def test_settlement_subtracts_fee_and_execution_buffer(self):
        trade = {
            "side": "YES",
            "entry_price": 0.50,
            "fee": 0.02,
        }
        settled = settle_trade(
            trade,
            {"result": "yes"},
            execution_buffer=0.01,
        )
        self.assertAlmostEqual(settled["net_pnl"], 0.47)


if __name__ == "__main__":
    unittest.main()
