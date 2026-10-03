import unittest

from research.signals import evaluate_markets


class SignalTests(unittest.TestCase):
    def test_rejects_signal_without_required_top_of_book_quantity(self):
        markets = [
            {
                "market_ticker": "KXHIGHNY-26OCT04-T63",
                "floor_strike": None,
                "cap_strike": 63,
                "yes_bid": 0.05,
                "yes_bid_qty": 100,
                "yes_ask": 0.10,
                "yes_ask_qty": 20,
            },
            {
                "market_ticker": "KXHIGHNY-26OCT04-B63.5",
                "floor_strike": 63,
                "cap_strike": 64,
                "yes_bid": 0.20,
                "yes_bid_qty": 100,
                "yes_ask": 0.25,
                "yes_ask_qty": 20,
            },
            {
                "market_ticker": "KXHIGHNY-26OCT04-B65.5",
                "floor_strike": 65,
                "cap_strike": 66,
                "yes_bid": 0.20,
                "yes_bid_qty": 100,
                "yes_ask": 0.25,
                "yes_ask_qty": 5,
            },
            {
                "market_ticker": "KXHIGHNY-26OCT04-B67.5",
                "floor_strike": 67,
                "cap_strike": 68,
                "yes_bid": 0.10,
                "yes_bid_qty": 100,
                "yes_ask": 0.15,
                "yes_ask_qty": 20,
            },
            {
                "market_ticker": "KXHIGHNY-26OCT04-B69.5",
                "floor_strike": 69,
                "cap_strike": 70,
                "yes_bid": 0.05,
                "yes_bid_qty": 100,
                "yes_ask": 0.10,
                "yes_ask_qty": 20,
            },
            {
                "market_ticker": "KXHIGHNY-26OCT04-T70",
                "floor_strike": 70,
                "cap_strike": None,
                "yes_bid": 0.01,
                "yes_bid_qty": 100,
                "yes_ask": 0.02,
                "yes_ask_qty": 20,
            },
        ]

        _, signals = evaluate_markets(
            markets,
            65.5,
            1.0,
            min_edge=0.05,
            execution_buffer=0.01,
            min_qty=10,
        )

        self.assertFalse(
            any(
                signal.market_ticker.endswith("B65.5") and signal.side == "YES"
                for signal in signals
            )
        )


if __name__ == "__main__":
    unittest.main()
