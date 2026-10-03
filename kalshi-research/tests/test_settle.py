import unittest

from paper.settle import gross_pnl, settlement_yes_from_market


class SettlementTests(unittest.TestCase):
    def test_reads_binary_settlement(self):
        self.assertEqual(
            settlement_yes_from_market({"settlement_value_dollars": "1.0000"}), 1
        )
        self.assertEqual(
            settlement_yes_from_market({"settlement_value_dollars": "0.0000"}), 0
        )
        self.assertIsNone(settlement_yes_from_market({}))

    def test_gross_pnl(self):
        self.assertAlmostEqual(gross_pnl("YES", 0.25, 10, 1), 7.5)
        self.assertAlmostEqual(gross_pnl("YES", 0.25, 10, 0), -2.5)
        self.assertAlmostEqual(gross_pnl("NO", 0.30, 10, 0), 7.0)


if __name__ == "__main__":
    unittest.main()
