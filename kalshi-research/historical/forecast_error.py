#!/usr/bin/env python3
"""Fit and query an empirical daily-high forecast error model."""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import NormalDist, mean, pstdev

DEFAULT_BUCKETS = (12, 24, 36, 48, 60, 72)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--output", type=Path, default=Path("data/models/nbm_error_model.json"))
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    parser.add_argument("--min-samples", type=int, default=30)
    return parser.parse_args()


def nearest_bucket(lead: float, buckets: tuple[int, ...], max_distance: float) -> int | None:
    bucket = min(buckets, key=lambda x: abs(x - lead))
    return bucket if abs(bucket - lead) <= max_distance else None


def load_errors(path: Path, buckets: tuple[int, ...], max_distance: float):
    grouped = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                lead = float(row["lead_hours"])
                error = float(row["error_f"])
            except (KeyError, TypeError, ValueError):
                continue
            bucket = nearest_bucket(lead, buckets, max_distance)
            if bucket is not None and math.isfinite(error):
                grouped[bucket].append(error)
    return grouped


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
    }


def kalshi_bucket_probabilities(forecast_high_f: float, bias_f: float, sd_error_f: float) -> dict[str, float]:
    """Map a forecast + error distribution to KXHIGHNY-style integer buckets.

    Kalshi's displayed buckets are <=62, 63-64, 65-66, 67-68, 69-70, >=71.
    Half-degree cut points implement integer rounding boundaries for a continuous
    approximation to the realized daily high.
    """
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
    buckets = tuple(sorted({int(x.strip()) for x in args.buckets.split(",") if x.strip()}))
    grouped = load_errors(args.dataset, buckets, args.max_distance)

    model = {
        "dataset": str(args.dataset),
        "lead_buckets_hours": list(buckets),
        "max_bucket_distance_hours": args.max_distance,
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
    print(f"\nWrote model to {args.output}")


if __name__ == "__main__":
    main()
