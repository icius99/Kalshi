from __future__ import annotations

from dataclasses import dataclass
from math import inf
from statistics import NormalDist


@dataclass(frozen=True)
class TemperatureBucket:
    label: str
    lower: float = -inf
    upper: float = inf

    def probability(self, dist: NormalDist) -> float:
        """Probability for integer-reported temperatures using 0.5F continuity cuts."""
        low_cdf = 0.0 if self.lower == -inf else dist.cdf(self.lower - 0.5)
        high_cdf = 1.0 if self.upper == inf else dist.cdf(self.upper + 0.5)
        return max(0.0, min(1.0, high_cdf - low_cdf))


def bucket_from_market(ticker: str, floor_strike, cap_strike) -> TemperatureBucket:
    floor = None if floor_strike is None else float(floor_strike)
    cap = None if cap_strike is None else float(cap_strike)

    if "-B" in ticker:
        if floor is None or cap is None:
            raise ValueError(f"bounded market missing strikes: {ticker}")
        return TemperatureBucket(f"{int(floor)}-{int(cap)}", floor, cap)

    if "-T" in ticker:
        if floor is not None and cap is None:
            return TemperatureBucket(f">={int(floor) + 1}", floor + 1, inf)
        if cap is not None and floor is None:
            return TemperatureBucket(f"<={int(cap) - 1}", -inf, cap - 1)

    raise ValueError(f"cannot infer temperature bucket from {ticker}")


def probabilities_for_markets(markets: list[dict], mean_f: float, sigma_f: float) -> dict[str, float]:
    if sigma_f <= 0:
        raise ValueError("sigma_f must be positive")
    dist = NormalDist(mu=mean_f, sigma=sigma_f)
    result = {}
    for market in markets:
        bucket = bucket_from_market(
            market["market_ticker"], market.get("floor_strike"), market.get("cap_strike")
        )
        result[market["market_ticker"]] = bucket.probability(dist)
    return result
