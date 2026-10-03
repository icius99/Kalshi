#!/usr/bin/env python3
"""Chronological out-of-sample validation for the NBM daily-high error model."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import NormalDist, mean, pstdev

from historical.sampling import load_bucketed_rows


DEFAULT_BUCKETS = (12, 24, 36, 48, 60)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--test-start", type=date.fromisoformat)
    parser.add_argument("--train-fraction", type=float, default=0.75)
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    parser.add_argument("--min-train", type=int, default=60)
    parser.add_argument("--min-test", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/models/nbm_validation.json"),
    )
    return parser.parse_args()


def load_rows(path: Path, buckets: tuple[int, ...], max_distance: float):
    return load_bucketed_rows(path, buckets, max_distance)


def choose_test_start(rows: list[dict], explicit: date | None, train_fraction: float) -> date:
    if explicit is not None:
        return explicit
    dates = sorted({row["target_date"] for row in rows})
    if len(dates) < 2:
        raise SystemExit("Dataset does not contain enough distinct dates for a chronological split.")
    if not 0.5 <= train_fraction < 1.0:
        raise SystemExit("--train-fraction must be >=0.5 and <1.0")
    index = min(len(dates) - 1, max(1, int(len(dates) * train_fraction)))
    return dates[index]


def interval_contains(actual: float, mu: float, sigma: float, central_mass: float) -> bool:
    alpha = (1.0 - central_mass) / 2.0
    dist = NormalDist(mu=mu, sigma=sigma)
    lo = dist.inv_cdf(alpha)
    hi = dist.inv_cdf(1.0 - alpha)
    return lo <= actual <= hi


def rounded_temperature_probability(actual: float, mu: float, sigma: float) -> float:
    """Probability assigned to the observed integer-Fahrenheit outcome."""
    dist = NormalDist(mu=mu, sigma=sigma)
    return max(1e-12, dist.cdf(actual + 0.5) - dist.cdf(actual - 0.5))


def empirical_error_pmf(errors: list[float], alpha: float = 0.1) -> dict[int, float]:
    """Laplace-smoothed empirical integer-error distribution."""
    counts = Counter(int(round(error)) for error in errors)
    if not counts:
        raise ValueError("cannot fit empirical distribution without errors")
    support_min = min(-20, min(counts))
    support_max = max(20, max(counts))
    support = range(support_min, support_max + 1)
    denominator = len(errors) + alpha * len(support)
    return {
        error: (counts.get(error, 0) + alpha) / denominator
        for error in support
    }


def empirical_error_probability(error: float, pmf: dict[int, float]) -> float:
    rounded = int(round(error))
    if abs(error - rounded) > 1e-6:
        raise ValueError(f"expected integer-Fahrenheit error, got {error}")
    return max(1e-12, pmf.get(rounded, 1e-12))


def fit_xnd_scale(rows: list[dict]) -> tuple[float | None, int]:
    """Fit a zero-mean multiplicative scale for NBM XND on training data.

    If sigma_i = scale * XND_i and forecast error is modeled as Normal(0, sigma_i),
    the maximum-likelihood scale is sqrt(mean((error / XND)^2)).
    """
    standardized_sq = []
    for row in rows:
        xnd = row.get("forecast_sigma")
        if xnd is None or xnd <= 0:
            continue
        standardized_sq.append((row["error"] / xnd) ** 2)

    if not standardized_sq:
        return None, 0

    scale = math.sqrt(mean(standardized_sq))
    if not math.isfinite(scale) or scale <= 0:
        return None, len(standardized_sq)
    return scale, len(standardized_sq)


def evaluate_bucket(train: list[dict], test: list[dict]) -> dict:
    train_errors = [row["error"] for row in train]
    bias = mean(train_errors)
    sigma = pstdev(train_errors)
    if sigma <= 0:
        raise ValueError("training residual sigma is zero")

    raw_errors = [row["error"] for row in test]
    corrected_errors = [
        row["actual"] - (row["forecast"] + bias)
        for row in test
    ]

    log_losses = []
    no_bias_normal_log_losses = []
    empirical_log_losses = []
    train_rmse = math.sqrt(mean(x * x for x in train_errors))
    empirical_pmf = empirical_error_pmf(train_errors)
    cover50 = []
    cover80 = []
    cover90 = []
    standardized = []

    xnd_scale, xnd_train_n = fit_xnd_scale(train)
    xnd_raw_log_losses = []
    xnd_scaled_log_losses = []
    xnd_scaled_cover90 = []
    xnd_test_n = 0

    for row in test:
        mu = row["forecast"] + bias
        probability = rounded_temperature_probability(row["actual"], mu, sigma)
        log_losses.append(-math.log(probability))

        no_bias_probability = rounded_temperature_probability(
            row["actual"], row["forecast"], train_rmse
        )
        no_bias_normal_log_losses.append(-math.log(no_bias_probability))

        empirical_probability = empirical_error_probability(
            row["error"], empirical_pmf
        )
        empirical_log_losses.append(-math.log(empirical_probability))

        cover50.append(interval_contains(row["actual"], mu, sigma, 0.50))
        cover80.append(interval_contains(row["actual"], mu, sigma, 0.80))
        cover90.append(interval_contains(row["actual"], mu, sigma, 0.90))
        standardized.append((row["actual"] - mu) / sigma)

        xnd = row.get("forecast_sigma")
        if xnd is not None and xnd > 0:
            xnd_test_n += 1
            raw_xnd_probability = rounded_temperature_probability(
                row["actual"], row["forecast"], xnd
            )
            xnd_raw_log_losses.append(-math.log(raw_xnd_probability))

            if xnd_scale is not None:
                scaled_sigma = xnd * xnd_scale
                scaled_probability = rounded_temperature_probability(
                    row["actual"], row["forecast"], scaled_sigma
                )
                xnd_scaled_log_losses.append(-math.log(scaled_probability))
                xnd_scaled_cover90.append(
                    interval_contains(
                        row["actual"],
                        row["forecast"],
                        scaled_sigma,
                        0.90,
                    )
                )

    return {
        "n_train": len(train),
        "n_test": len(test),
        "train_bias_f": round(bias, 4),
        "train_sigma_f": round(sigma, 4),
        "test_raw_bias_f": round(mean(raw_errors), 4),
        "test_corrected_bias_f": round(mean(corrected_errors), 4),
        "test_raw_rmse_f": round(math.sqrt(mean(x * x for x in raw_errors)), 4),
        "test_corrected_rmse_f": round(
            math.sqrt(mean(x * x for x in corrected_errors)), 4
        ),
        "mean_integer_log_loss": round(mean(log_losses), 6),
        "mean_bias_corrected_normal_log_loss": round(mean(log_losses), 6),
        "mean_no_bias_normal_log_loss": round(mean(no_bias_normal_log_losses), 6),
        "mean_empirical_log_loss": round(mean(empirical_log_losses), 6),
        "coverage_50": round(mean(cover50), 4),
        "coverage_80": round(mean(cover80), 4),
        "coverage_90": round(mean(cover90), 4),
        "standardized_error_mean": round(mean(standardized), 4),
        "standardized_error_sd": round(
            pstdev(standardized) if len(standardized) > 1 else 0.0, 4
        ),
        "xnd_train_n": xnd_train_n,
        "xnd_test_n": xnd_test_n,
        "xnd_scale": None if xnd_scale is None else round(xnd_scale, 6),
        "mean_raw_xnd_log_loss": (
            None
            if not xnd_raw_log_losses
            else round(mean(xnd_raw_log_losses), 6)
        ),
        "mean_scaled_xnd_log_loss": (
            None
            if not xnd_scaled_log_losses
            else round(mean(xnd_scaled_log_losses), 6)
        ),
        "scaled_xnd_coverage_90": (
            None
            if not xnd_scaled_cover90
            else round(mean(xnd_scaled_cover90), 4)
        ),
    }


def main():
    args = parse_args()
    buckets = tuple(
        sorted({int(value.strip()) for value in args.buckets.split(",") if value.strip()})
    )
    rows = load_rows(args.dataset, buckets, args.max_distance)
    if not rows:
        raise SystemExit("No usable rows found in dataset.")

    test_start = choose_test_start(rows, args.test_start, args.train_fraction)
    grouped_train = defaultdict(list)
    grouped_test = defaultdict(list)

    for row in rows:
        destination = grouped_test if row["target_date"] >= test_start else grouped_train
        destination[row["lead_bucket"]].append(row)

    report = {
        "dataset": str(args.dataset),
        "test_start": test_start.isoformat(),
        "lead_buckets_hours": list(buckets),
        "buckets": {},
    }

    print(f"Chronological split: train before {test_start}; test on/after {test_start}")
    print()
    print("lead  train test  bias  RMSE   empLL zeroNLL  XNDsc XNDLL Xcov90")
    print("----  ----- ----  ----- -----  ----- -------  ----- ----- ------")

    for bucket in buckets:
        train = grouped_train.get(bucket, [])
        test = grouped_test.get(bucket, [])
        if len(train) < args.min_train or len(test) < args.min_test:
            print(
                f"{bucket:>4}  {len(train):>5} {len(test):>4}  insufficient samples"
            )
            continue

        stats = evaluate_bucket(train, test)
        report["buckets"][str(bucket)] = stats
        xnd_scale = stats["xnd_scale"]
        xnd_ll = stats["mean_scaled_xnd_log_loss"]
        xnd_cov = stats["scaled_xnd_coverage_90"]
        print(
            f"{bucket:>4}  {stats['n_train']:>5} {stats['n_test']:>4}  "
            f"{stats['train_bias_f']:>+5.2f} {stats['test_raw_rmse_f']:>5.2f}  "
            f"{stats['mean_empirical_log_loss']:>5.3f} "
            f"{stats['mean_no_bias_normal_log_loss']:>7.3f}  "
            f"{'-' if xnd_scale is None else f'{xnd_scale:.2f}':>5} "
            f"{'-' if xnd_ll is None else f'{xnd_ll:.3f}':>5} "
            f"{'-' if xnd_cov is None else f'{xnd_cov:.1%}':>6}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote validation report to {args.output}")


if __name__ == "__main__":
    main()
