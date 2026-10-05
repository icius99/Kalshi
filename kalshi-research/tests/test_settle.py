import unittest

from paper.settle import (
    gross_pnl,
    net_pnl,
    score_multiclass_probabilities,
    settlement_yes_from_market,
)


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

    def test_net_pnl_subtracts_entry_fee(self):
        self.assertAlmostEqual(net_pnl("YES", 0.25, 10, 1, 0.14), 7.36)

    def test_multiclass_scores(self):
        probabilities = {
            "A": 0.1,
            "B": 0.7,
            "C": 0.2,
        }
        brier, log_loss = score_multiclass_probabilities(
            probabilities,
            "B",
        )
        self.assertAlmostEqual(
            brier,
            (0.1 ** 2) + ((0.7 - 1.0) ** 2) + (0.2 ** 2),
        )
        self.assertAlmostEqual(log_loss, -__import__("math").log(0.7))


if __name__ == "__main__":
    unittest.main()
