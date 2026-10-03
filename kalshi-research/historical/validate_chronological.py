#!/usr/bin/env python3
"""Chronological out-of-sample validation for the NBM daily-high error model."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import NormalDist, mean, pstdev


DEFAULT_BUCKETS = (12, 24, 36, 48, 60, 72)


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


def nearest_bucket(lead: float, buckets: tuple[int, ...], max_distance: float):
    bucket = min(buckets, key=lambda value: abs(value - lead))
    return bucket if abs(bucket - lead) <= max_distance else None


def load_rows(path: Path, buckets: tuple[int, ...], max_distance: float):
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                target = date.fromisoformat(row["target_date"])
                lead = float(row["lead_hours"])
                forecast = float(row["forecast_high_f"])
                actual = float(row["actual_high_f"])
            except (KeyError, TypeError, ValueError):
                continue
            bucket = nearest_bucket(lead, buckets, max_distance)
            if bucket is None:
                continue
            rows.append(
                {
                    "target_date": target,
                    "lead_bucket": bucket,
                    "forecast": forecast,
                    "actual": actual,
                    "error": actual - forecast,
                }
            )
    return rows


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
    cover50 = []
    cover80 = []
    cover90 = []
    standardized = []

    for row in test:
        mu = row["forecast"] + bias
        probability = rounded_temperature_probability(row["actual"], mu, sigma)
        log_losses.append(-math.log(probability))
        cover50.append(interval_contains(row["actual"], mu, sigma, 0.50))
        cover80.append(interval_contains(row["actual"], mu, sigma, 0.80))
        cover90.append(interval_contains(row["actual"], mu, sigma, 0.90))
        standardized.append((row["actual"] - mu) / sigma)

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
        "coverage_50": round(mean(cover50), 4),
        "coverage_80": round(mean(cover80), 4),
        "coverage_90": round(mean(cover90), 4),
        "standardized_error_mean": round(mean(standardized), 4),
        "standardized_error_sd": round(
            pstdev(standardized) if len(standardized) > 1 else 0.0, 4
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
    print("lead  train test  bias   sigma  rawRMSE adjRMSE  cov50 cov80 cov90  logloss")
    print("----  ----- ----  -----  -----  ------- -------  ----- ----- -----  -------")

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
        print(
            f"{bucket:>4}  {stats['n_train']:>5} {stats['n_test']:>4}  "
            f"{stats['train_bias_f']:>+5.2f}  {stats['train_sigma_f']:>5.2f}  "
            f"{stats['test_raw_rmse_f']:>7.2f} {stats['test_corrected_rmse_f']:>7.2f}  "
            f"{stats['coverage_50']:>5.1%} {stats['coverage_80']:>5.1%} "
            f"{stats['coverage_90']:>5.1%}  {stats['mean_integer_log_loss']:>7.3f}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote validation report to {args.output}")


if __name__ == "__main__":
    main()
