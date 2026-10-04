#!/usr/bin/env python3
"""Walk-forward comparison of probabilistic forecast-error models by calendar year."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from historical.sampling import load_bucketed_rows
from historical.validate_chronological import (
    empirical_error_pmf,
    empirical_error_probability,
    fit_xnd_scale,
    rounded_temperature_probability,
)

DEFAULT_BUCKETS = (12, 24, 36, 48, 60)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    parser.add_argument("--first-test-year", type=int, default=2022)
    parser.add_argument("--last-test-year", type=int)
    parser.add_argument("--min-train", type=int, default=300)
    parser.add_argument("--min-test", type=int, default=100)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/models/nbm_walkforward.json"),
    )
    return parser.parse_args()


def score_fold(train: list[dict], test: list[dict]) -> dict:
    train_errors = [row["error"] for row in train]
    if not train_errors:
        raise ValueError("empty training set")

    empirical_pmf = empirical_error_pmf(train_errors)
    global_sigma = math.sqrt(mean(error * error for error in train_errors))
    xnd_scale, xnd_train_n = fit_xnd_scale(train)

    empirical_losses = []
    global_losses = []
    xnd_losses = []
    common_n = 0

    for row in test:
        xnd = row.get("forecast_sigma")
        if xnd is None or xnd <= 0 or xnd_scale is None:
            continue

        common_n += 1
        empirical_p = empirical_error_probability(row["error"], empirical_pmf)
        empirical_losses.append(-math.log(empirical_p))

        global_p = rounded_temperature_probability(
            row["actual"],
            row["forecast"],
            global_sigma,
        )
        global_losses.append(-math.log(global_p))

        xnd_p = rounded_temperature_probability(
            row["actual"],
            row["forecast"],
            xnd * xnd_scale,
        )
        xnd_losses.append(-math.log(xnd_p))

    if not common_n:
        raise ValueError("no common test rows with XND")

    losses = {
        "empirical": mean(empirical_losses),
        "global_normal": mean(global_losses),
        "scaled_xnd": mean(xnd_losses),
    }
    winner = min(losses, key=losses.get)

    return {
        "n": common_n,
        "xnd_train_n": xnd_train_n,
        "xnd_scale": xnd_scale,
        "losses": losses,
        "winner": winner,
    }


def aggregate(results: list[dict]) -> dict:
    totals = defaultdict(float)
    total_n = 0
    wins = defaultdict(int)

    for result in results:
        n = result["n"]
        total_n += n
        wins[result["winner"]] += 1
        for name, loss in result["losses"].items():
            totals[name] += loss * n

    return {
        "n": total_n,
        "mean_losses": {
            name: total / total_n
            for name, total in totals.items()
        },
        "wins": dict(wins),
    }


def main():
    args = parse_args()
    buckets = tuple(
        sorted({int(value.strip()) for value in args.buckets.split(",") if value.strip()})
    )
    rows = load_bucketed_rows(args.dataset, buckets, args.max_distance)
    if not rows:
        raise SystemExit("No usable rows found.")

    max_year = max(row["target_date"].year for row in rows)
    last_year = args.last_test_year or max_year

    by_bucket = defaultdict(list)
    for row in rows:
        by_bucket[row["lead_bucket"]].append(row)

    per_bucket_results = defaultdict(list)
    report = {
        "dataset": str(args.dataset),
        "first_test_year": args.first_test_year,
        "last_test_year": last_year,
        "lead_buckets_hours": list(buckets),
        "folds": [],
        "aggregate_by_lead": {},
        "aggregate_all": None,
    }

    print("Walk-forward annual probabilistic comparison")
    print("Lower log loss is better. Each test year uses only prior-year training data.")
    print()
    print("year lead  train test  XNDsc   empirical  globalN   scaledXND  winner")
    print("---- ----  ----- ----  -----   ---------  -------   ---------  -----------")

    for year in range(args.first_test_year, last_year + 1):
        test_start = date(year, 1, 1)
        test_end = date(year + 1, 1, 1)

        for bucket in buckets:
            values = by_bucket[bucket]
            train = [row for row in values if row["target_date"] < test_start]
            test = [
                row for row in values
                if test_start <= row["target_date"] < test_end
            ]

            if len(train) < args.min_train or len(test) < args.min_test:
                continue

            result = score_fold(train, test)
            result["year"] = year
            result["lead_bucket"] = bucket
            per_bucket_results[bucket].append(result)
            report["folds"].append(result.copy())

            losses = result["losses"]
            print(
                f"{year:>4} {bucket:>4}  {len(train):>5} {result['n']:>4}  "
                f"{result['xnd_scale']:>5.2f}   "
                f"{losses['empirical']:>9.3f}  "
                f"{losses['global_normal']:>7.3f}   "
                f"{losses['scaled_xnd']:>9.3f}  "
                f"{result['winner']}"
            )

    print()
    print("Aggregate by lead")
    print("lead folds     n  empirical  globalN  scaledXND  wins")
    print("---- ----- -----  ---------  -------  ---------  ---------------------------")

    all_results = []
    for bucket in buckets:
        results = per_bucket_results.get(bucket, [])
        if not results:
            continue
        all_results.extend(results)
        agg = aggregate(results)
        report["aggregate_by_lead"][str(bucket)] = agg
        losses = agg["mean_losses"]
        wins = ", ".join(
            f"{name}={count}"
            for name, count in sorted(agg["wins"].items())
        )
        print(
            f"{bucket:>4} {len(results):>5} {agg['n']:>5}  "
            f"{losses['empirical']:>9.3f}  "
            f"{losses['global_normal']:>7.3f}  "
            f"{losses['scaled_xnd']:>9.3f}  {wins}"
        )

    if all_results:
        agg = aggregate(all_results)
        report["aggregate_all"] = agg
        losses = agg["mean_losses"]
        report["recommended_probability_method"] = min(
            losses, key=losses.get
        )
        wins = ", ".join(
            f"{name}={count}"
            for name, count in sorted(agg["wins"].items())
        )
        print()
        print(
            "ALL"
            f"  folds={len(all_results)} n={agg['n']} "
            f"empirical={losses['empirical']:.3f} "
            f"globalN={losses['global_normal']:.3f} "
            f"scaledXND={losses['scaled_xnd']:.3f} "
            f"wins[{wins}]"
        )
        print(
            "Recommended probability method: "
            f"{report['recommended_probability_method']}"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote walk-forward report to {args.output}")


if __name__ == "__main__":
    main()
