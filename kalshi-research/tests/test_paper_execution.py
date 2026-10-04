import unittest
from unittest.mock import patch

from paper.execution import fetch_live_execution_markets, revalidate_signals


class PaperExecutionTests(unittest.TestCase):
    @patch("paper.execution.get_orderbook")
    def test_fetch_live_execution_markets_refreshes_quotes(self, get_orderbook):
        get_orderbook.return_value = {
            "yes_dollars": [["0.40", "12"]],
            "no_dollars": [["0.55", "20"]],
        }
        timestamp, markets = fetch_live_execution_markets(
            [
                {
                    "market_ticker": "ABC",
                    "yes_bid": 0.10,
                    "yes_ask": 0.90,
                }
            ]
        )
        self.assertTrue(timestamp.endswith("+00:00"))
        self.assertEqual(markets[0]["yes_bid"], 0.40)
        self.assertEqual(markets[0]["yes_ask"], 0.45)
        self.assertEqual(markets[0]["yes_ask_qty"], 20.0)

    @patch("paper.execution.fetch_live_execution_markets")
    def test_revalidation_drops_edge_that_disappeared(self, fetch_live):
        fetch_live.return_value = (
            "2026-10-04T12:00:00+00:00",
            [
                {
                    "market_ticker": "ABC",
                    "yes_bid": 0.59,
                    "yes_bid_qty": 20,
                    "yes_ask": 0.61,
                    "yes_ask_qty": 20,
                }
            ],
        )
        _, _, signals = revalidate_signals(
            [{"market_ticker": "ABC"}],
            {"ABC": 0.60},
            min_edge=0.05,
            execution_buffer=0.005,
            min_qty=10,
            max_contracts=25,
        )
        self.assertEqual(signals, [])


if __name__ == "__main__":
    unittest.main()
