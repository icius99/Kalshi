import unittest
from statistics import NormalDist

from research.temperature import TemperatureBucket, bucket_from_market, probabilities_for_markets


class TemperatureBucketTests(unittest.TestCase):
    def test_kalshi_tail_and_bounded_buckets(self):
        lo = bucket_from_market("KXHIGHNY-26OCT04-T63", None, 63)
        mid = bucket_from_market("KXHIGHNY-26OCT04-B65.5", 65, 66)
        hi = bucket_from_market("KXHIGHNY-26OCT04-T70", 70, None)
        self.assertEqual((lo.label, lo.upper), ("<=62", 62))
        self.assertEqual((mid.label, mid.lower, mid.upper), ("65-66", 65, 66))
        self.assertEqual((hi.label, hi.lower), (">=71", 71))

    def test_partition_probability_sums_to_one(self):
        markets = [
            {"market_ticker":"KXHIGHNY-26OCT04-T63","floor_strike":None,"cap_strike":63},
            {"market_ticker":"KXHIGHNY-26OCT04-B63.5","floor_strike":63,"cap_strike":64},
            {"market_ticker":"KXHIGHNY-26OCT04-B65.5","floor_strike":65,"cap_strike":66},
            {"market_ticker":"KXHIGHNY-26OCT04-B67.5","floor_strike":67,"cap_strike":68},
            {"market_ticker":"KXHIGHNY-26OCT04-B69.5","floor_strike":69,"cap_strike":70},
            {"market_ticker":"KXHIGHNY-26OCT04-T70","floor_strike":70,"cap_strike":None},
        ]
        probs = probabilities_for_markets(markets, 65, 2)
        self.assertAlmostEqual(sum(probs.values()), 1.0, places=12)


if __name__ == "__main__":
    unittest.main()
