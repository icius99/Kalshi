import unittest

from research.fees import taker_fee


class FeeTests(unittest.TestCase):
    def test_matches_published_general_table_examples(self):
        self.assertEqual(taker_fee(0.20, 1), 0.02)
        self.assertEqual(taker_fee(0.20, 100), 1.12)
        self.assertEqual(taker_fee(0.50, 1), 0.02)
        self.assertEqual(taker_fee(0.50, 100), 1.75)

    def test_rejects_fractional_contract_count(self):
        with self.assertRaises(ValueError):
            taker_fee(0.50, 1.5)


if __name__ == "__main__":
    unittest.main()
