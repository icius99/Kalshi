from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from research.temperature import bucket_from_market


def empirical_error_pmf_from_counts(
    error_counts: dict[int, int],
    alpha: float = 0.1,
) -> dict[int, float]:
    """Laplace-smoothed empirical integer-Fahrenheit error distribution."""
    if alpha <= 0:
        raise ValueError("alpha must be positive")
    if not error_counts:
        raise ValueError("error_counts must not be empty")

    support_min = min(-20, min(error_counts))
    support_max = max(20, max(error_counts))
    support = range(support_min, support_max + 1)
    denominator = sum(error_counts.values()) + alpha * len(support)
    return {
        error: (error_counts.get(error, 0) + alpha) / denominator
        for error in support
    }


def probabilities_from_error_counts(
    markets: list[dict],
    forecast_high_f: float,
    error_counts: dict[int, int],
    alpha: float = 0.1,
) -> dict[str, float]:
    """Map an empirical error histogram into an exhaustive temperature event."""
    pmf = empirical_error_pmf_from_counts(error_counts, alpha)
    probabilities = {}
    for market in markets:
        ticker = market.get("market_ticker", market.get("ticker"))
        if not ticker:
            raise ValueError("market missing ticker")
        bucket = bucket_from_market(
            ticker,
            market.get("floor_strike"),
            market.get("cap_strike"),
        )
        probabilities[ticker] = sum(
            mass
            for error, mass in pmf.items()
            if bucket.lower <= forecast_high_f + error <= bucket.upper
        )

    total = sum(probabilities.values())
    if total <= 0:
        raise ValueError("market buckets captured no empirical probability mass")
    return {ticker: probability / total for ticker, probability in probabilities.items()}


@dataclass(frozen=True)
class ErrorBucket:
    lead_hours: int
    n: int
    bias_f: float
    sigma_f: float
    rmse_f: float
    error_counts: dict[int, int]


class ForecastErrorModel:
    def __init__(self, payload: dict):
        self.payload = payload
        self.smoothing_alpha = float(payload.get("empirical_smoothing_alpha", 0.1))
        if self.smoothing_alpha <= 0:
            raise ValueError("empirical smoothing alpha must be positive")

        self.buckets: dict[int, ErrorBucket] = {}
        for lead, stats in payload.get("buckets", {}).items():
            counts = {
                int(error): int(count)
                for error, count in stats.get("error_counts", {}).items()
            }
            self.buckets[int(lead)] = ErrorBucket(
                lead_hours=int(lead),
                n=int(stats["n"]),
                bias_f=float(stats.get("bias_f", 0.0)),
                sigma_f=float(stats.get("sd_error_f", stats.get("rmse_f", 0.0))),
                rmse_f=float(stats.get("rmse_f", stats.get("sd_error_f", 0.0))),
                error_counts=counts,
            )
        if not self.buckets:
            raise ValueError("error model contains no fitted lead-time buckets")

    @classmethod
    def load(cls, path: str | Path) -> "ForecastErrorModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def nearest(self, lead_hours: float, max_distance: float | None = None) -> ErrorBucket:
        bucket = min(self.buckets.values(), key=lambda x: abs(x.lead_hours - lead_hours))
        if max_distance is not None and abs(bucket.lead_hours - lead_hours) > max_distance:
            raise ValueError(
                f"nearest fitted lead bucket ({bucket.lead_hours}h) is too far from {lead_hours:.1f}h"
            )
        return bucket

    def error_pmf(self, bucket: ErrorBucket, alpha: float | None = None) -> dict[int, float]:
        """Laplace-smoothed integer-Fahrenheit error distribution."""
        alpha = self.smoothing_alpha if alpha is None else float(alpha)
        if alpha <= 0:
            raise ValueError("alpha must be positive")

        observed = bucket.error_counts
        if not observed:
            raise ValueError(
                "model bucket has no empirical error_counts; rebuild the historical model"
            )
        return empirical_error_pmf_from_counts(observed, alpha)

    def probabilities_for_markets(
        self,
        markets: list[dict],
        forecast_high_f: float,
        lead_hours: float,
        max_distance: float | None = None,
    ) -> tuple[ErrorBucket, dict[str, float]]:
        """Map empirical historical forecast errors into current Kalshi buckets."""
        fit = self.nearest(lead_hours, max_distance)
        probabilities = probabilities_from_error_counts(
            markets,
            forecast_high_f,
            fit.error_counts,
            self.smoothing_alpha,
        )
        return fit, probabilities
