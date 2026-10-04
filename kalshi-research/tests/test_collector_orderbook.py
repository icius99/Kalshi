import unittest

from collector import get_best_prices


class CollectorOrderbookTests(unittest.TestCase):
    def test_matches_kalshi_documented_orderbook_math(self):
        book = {
            "yes_dollars": [
                ["0.0100", "200.00"],
                ["0.4100", "10.00"],
                ["0.4200", "13.00"],
            ],
            "no_dollars": [
                ["0.0100", "100.00"],
                ["0.4500", "20.00"],
                ["0.5600", "17.00"],
            ],
        }
        yes_bid, yes_bid_qty, yes_ask, yes_ask_qty = get_best_prices(book)
        self.assertEqual(yes_bid, 0.42)
        self.assertEqual(yes_bid_qty, 13.0)
        self.assertEqual(yes_ask, 0.44)
        self.assertEqual(yes_ask_qty, 17.0)


if __name__ == "__main__":
    unittest.main()
