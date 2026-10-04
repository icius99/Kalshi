#!/usr/bin/env python3
"""Fit a daily-high forecast error model from historical NBM verification."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import NormalDist, mean, pstdev

from historical.build_nbm_history import FORECAST_DEFINITION, OBSERVATION_DEFINITION
from historical.sampling import load_bucketed_rows, nearest_bucket

# 72h remains available via --buckets, but the live 2021-2026 audit found
# materially thinner/less stable coverage there. Keep the default model to the
# well-populated 12-60h horizons.
DEFAULT_BUCKETS = (12, 24, 36, 48, 60)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/models/nbm_error_model.json"))
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--empirical-alpha", type=float, default=0.1)
    return parser.parse_args()


def load_errors(path: Path, buckets: tuple[int, ...], max_distance: float):
    grouped = defaultdict(list)
    for row in load_bucketed_rows(path, buckets, max_distance):
        grouped[row["lead_bucket"]].append(row["error"])
    return grouped


def integer_error_counts(errors: list[float]) -> dict[str, int]:
    counts = Counter()
    for error in errors:
        rounded = int(round(error))
        if abs(error - rounded) > 1e-6:
            raise ValueError(f"expected integer-Fahrenheit error, got {error}")
        counts[rounded] += 1
    return {str(key): counts[key] for key in sorted(counts)}


def summarize(errors: list[float]) -> dict:
    bias = mean(errors)
    sd = pstdev(errors) if len(errors) > 1 else 0.0
    mae = mean(abs(x) for x in errors)
    rmse = math.sqrt(mean(x * x for x in errors))
    sorted_abs = sorted(abs(x) for x in errors)
    p90 = sorted_abs[min(len(sorted_abs) - 1, math.ceil(0.90 * len(sorted_abs)) - 1)]
    return {
        "n": len(errors),
        "bias_f": round(bias, 4),
        "sd_error_f": round(sd, 4),
        "mae_f": round(mae, 4),
        "rmse_f": round(rmse, 4),
        "p90_abs_error_f": round(p90, 4),
        "error_counts": integer_error_counts(errors),
    }


def kalshi_bucket_probabilities(
    forecast_high_f: float, bias_f: float, sd_error_f: float
) -> dict[str, float]:
    """Legacy normal approximation retained for model-comparison research."""
    if sd_error_f <= 0:
        raise ValueError("sd_error_f must be positive")
    dist = NormalDist(mu=forecast_high_f + bias_f, sigma=sd_error_f)
    cuts = [62.5, 64.5, 66.5, 68.5, 70.5]
    cdf = [dist.cdf(x) for x in cuts]
    values = [
        cdf[0],
        cdf[1] - cdf[0],
        cdf[2] - cdf[1],
        cdf[3] - cdf[2],
        cdf[4] - cdf[3],
        1.0 - cdf[4],
    ]
    labels = ["<=62", "63-64", "65-66", "67-68", "69-70", ">=71"]
    return dict(zip(labels, values))


def main() -> None:
    args = parse_args()
    if args.empirical_alpha <= 0:
        raise SystemExit("--empirical-alpha must be positive")

    buckets = tuple(sorted({int(x.strip()) for x in args.buckets.split(",") if x.strip()}))
    grouped = load_errors(args.dataset, buckets, args.max_distance)

    model = {
        "version": 3,
        "distribution": "empirical_integer_errors",
        "forecast_definition": FORECAST_DEFINITION,
        "observation_definition": OBSERVATION_DEFINITION,
        "station": "KNYC",
        "series": "KXHIGHNY",
        "dataset": str(args.dataset),
        "lead_buckets_hours": list(buckets),
        "max_bucket_distance_hours": args.max_distance,
        "empirical_smoothing_alpha": args.empirical_alpha,
        "buckets": {},
    }

    print("lead  n     bias     sd     MAE    RMSE   p90|err|")
    print("---- ----  -------  -----  -----  -----  --------")
    for bucket in buckets:
        errors = grouped.get(bucket, [])
        if len(errors) < args.min_samples:
            print(f"{bucket:>4} {len(errors):>4}  insufficient samples")
            continue
        stats = summarize(errors)
        model["buckets"][str(bucket)] = stats
        print(
            f"{bucket:>4} {stats['n']:>4}  {stats['bias_f']:>+7.2f}  "
            f"{stats['sd_error_f']:>5.2f}  {stats['mae_f']:>5.2f}  "
            f"{stats['rmse_f']:>5.2f}  {stats['p90_abs_error_f']:>8.2f}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(model, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote empirical model to {args.output}")


if __name__ == "__main__":
    main()
