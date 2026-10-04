import unittest

from paper.audit_quotes import price_delta


class QuoteAuditTests(unittest.TestCase):
    def test_price_delta(self):
        self.assertAlmostEqual(price_delta(0.40, 0.42), 0.02)
        self.assertIsNone(price_delta(None, 0.42))
        self.assertIsNone(price_delta(0.40, None))


if __name__ == "__main__":
    unittest.main()
