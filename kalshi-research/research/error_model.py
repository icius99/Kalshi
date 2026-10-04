from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import NormalDist

from research.temperature import bucket_from_market


class ModelHorizonUnavailable(ValueError):
    """No calibrated lead bucket is close enough to the forecast runtime."""


@dataclass(frozen=True)
class ErrorBucket:
    lead_hours: int
    n: int
    bias_f: float
    sigma_f: float
    rmse_f: float
    error_counts: dict[int, int]
    nbm_uncertainty_n: int
    nbm_uncertainty_scale: float | None


class ForecastErrorModel:
    def __init__(self, payload: dict):
        self.payload = payload
        self.forecast_definition = payload.get("forecast_definition")
        self.observation_definition = payload.get("observation_definition")
        self.model_version = payload.get("version")
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
                nbm_uncertainty_n=int(stats.get("nbm_uncertainty_n", 0)),
                nbm_uncertainty_scale=(
                    None
                    if stats.get("nbm_uncertainty_scale") is None
                    else float(stats["nbm_uncertainty_scale"])
                ),
            )
        if not self.buckets:
            raise ValueError("error model contains no fitted lead-time buckets")

    @classmethod
    def load(cls, path: str | Path) -> "ForecastErrorModel":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def require_forecast_definition(self, expected: str) -> None:
        if self.forecast_definition != expected:
            actual = self.forecast_definition or "<missing/legacy>"
            raise ValueError(
                "forecast/model mismatch: this runtime uses "
                f"{expected!r}, but the loaded calibration model declares "
                f"{actual!r}. Rebuild and promote the model with the current "
                "historical pipeline before paper-signal use."
            )

    def nearest(self, lead_hours: float, max_distance: float | None = None) -> ErrorBucket:
        bucket = min(self.buckets.values(), key=lambda x: abs(x.lead_hours - lead_hours))
        if max_distance is not None and abs(bucket.lead_hours - lead_hours) > max_distance:
            raise ModelHorizonUnavailable(
                f"nearest fitted lead bucket ({bucket.lead_hours}h) "
                f"is too far from forecast lead {lead_hours:.1f}h"
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

        support_min = min(-20, min(observed))
        support_max = max(20, max(observed))
        support = range(support_min, support_max + 1)
        denominator = bucket.n + alpha * len(support)

        return {
            error: (observed.get(error, 0) + alpha) / denominator
            for error in support
        }

    def probabilities_for_markets_scaled_uncertainty(
        self,
        markets: list[dict],
        forecast_high_f: float,
        forecast_sigma_f: float,
        lead_hours: float,
        max_distance: float | None = None,
    ) -> tuple[ErrorBucket, dict[str, float]]:
        """Map calibrated NBM case-specific uncertainty into Kalshi buckets."""
        if forecast_sigma_f <= 0:
            raise ValueError("forecast_sigma_f must be positive")

        fit = self.nearest(lead_hours, max_distance)
        if fit.nbm_uncertainty_scale is None or fit.nbm_uncertainty_scale <= 0:
            raise ValueError(
                f"lead bucket {fit.lead_hours}h has no fitted NBM uncertainty scale"
            )

        sigma = forecast_sigma_f * fit.nbm_uncertainty_scale
        dist = NormalDist(mu=forecast_high_f, sigma=sigma)
        probabilities: dict[str, float] = {}

        for market in markets:
            ticker = market["market_ticker"]
            bucket = bucket_from_market(
                ticker,
                market.get("floor_strike"),
                market.get("cap_strike"),
            )
            probabilities[ticker] = bucket.probability(dist)

        total = sum(probabilities.values())
        if total <= 0:
            raise ValueError("market buckets captured no calibrated probability mass")

        return fit, {
            ticker: probability / total
            for ticker, probability in probabilities.items()
        }

    def probabilities_for_markets(
        self,
        markets: list[dict],
        forecast_high_f: float,
        lead_hours: float,
        max_distance: float | None = None,
    ) -> tuple[ErrorBucket, dict[str, float]]:
        """Map empirical historical forecast errors into current Kalshi buckets."""
        fit = self.nearest(lead_hours, max_distance)
        pmf = self.error_pmf(fit)
        probabilities: dict[str, float] = {}

        for market in markets:
            ticker = market["market_ticker"]
            bucket = bucket_from_market(
                ticker,
                market.get("floor_strike"),
                market.get("cap_strike"),
            )

            probability = 0.0
            for error, mass in pmf.items():
                actual = forecast_high_f + error
                if bucket.lower <= actual <= bucket.upper:
                    probability += mass

            probabilities[ticker] = probability

        total = sum(probabilities.values())
        if total <= 0:
            raise ValueError("market buckets captured no empirical probability mass")

        # A KXHIGHNY event is intended to be an exhaustive partition. Normalize
        # tiny floating/support artifacts so the returned distribution sums to 1.
        return fit, {
            ticker: probability / total
            for ticker, probability in probabilities.items()
        }
