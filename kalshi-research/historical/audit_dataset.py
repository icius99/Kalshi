#!/usr/bin/env python3
"""Structural and statistical sanity checks for a built historical dataset."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import mean

from historical.sampling import load_bucketed_rows

DEFAULT_BUCKETS = (12, 24, 36, 48, 60, 72)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    return parser.parse_args()


def parse_iso_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def raw_audit(path: Path) -> dict:
    target_actuals = defaultdict(set)
    rows_per_date = Counter()
    runtime_target_pairs = Counter()
    structural_errors = []
    raw_rows = 0

    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            raw_rows += 1
            try:
                target = date.fromisoformat(row["target_date"])
                actual = float(row["actual_high_f"])
                forecast = float(row["forecast_high_f"])
                error = float(row["error_f"])
                lead = float(row["lead_hours"])
                runtime = parse_iso_datetime(row["runtime_utc"])
                valid = parse_iso_datetime(row["valid_utc"])
            except (KeyError, TypeError, ValueError) as exc:
                structural_errors.append(f"line {line_number}: parse failure: {exc}")
                continue

            if not all(math.isfinite(v) for v in (actual, forecast, error, lead)):
                structural_errors.append(f"line {line_number}: non-finite numeric value")
                continue

            if abs((actual - forecast) - error) > 1e-9:
                structural_errors.append(
                    f"line {line_number}: error_f != actual_high_f - forecast_high_f"
                )

            if valid.hour != 0 or valid.minute != 0:
                structural_errors.append(
                    f"line {line_number}: daily max valid time is not 00Z: {valid.isoformat()}"
                )

            mapped_target = (valid - timedelta(hours=12)).date()
            if mapped_target != target:
                structural_errors.append(
                    f"line {line_number}: valid time maps to {mapped_target}, not {target}"
                )

            target_actuals[target].add(actual)
            rows_per_date[target] += 1
            runtime_target_pairs[(runtime.isoformat(), target)] += 1

    duplicate_runtime_targets = [
        key for key, count in runtime_target_pairs.items() if count > 1
    ]
    if duplicate_runtime_targets:
        structural_errors.append(
            f"{len(duplicate_runtime_targets)} duplicate runtime/target pairs"
        )

    inconsistent_actual_dates = [
        target for target, values in target_actuals.items() if len(values) > 1
    ]
    if inconsistent_actual_dates:
        structural_errors.append(
            f"{len(inconsistent_actual_dates)} dates have inconsistent actual highs"
        )

    dates = sorted(target_actuals)
    missing_dates = []
    if dates:
        cursor = dates[0]
        while cursor <= dates[-1]:
            if cursor not in target_actuals:
                missing_dates.append(cursor)
            cursor += timedelta(days=1)

    return {
        "raw_rows": raw_rows,
        "dates": dates,
        "rows_per_date": rows_per_date,
        "missing_dates": missing_dates,
        "structural_errors": structural_errors,
    }


def main():
    args = parse_args()
    buckets = tuple(
        sorted({int(value.strip()) for value in args.buckets.split(",") if value.strip()})
    )

    raw = raw_audit(args.dataset)
    selected = load_bucketed_rows(args.dataset, buckets, args.max_distance)

    print(f"Dataset: {args.dataset}")
    print(f"Raw forecast rows: {raw['raw_rows']:,}")
    print(f"Target dates: {len(raw['dates']):,}")

    if raw["dates"]:
        print(f"Date range: {raw['dates'][0]} .. {raw['dates'][-1]}")
        counts = list(raw["rows_per_date"].values())
        print(
            "Raw forecasts/date: "
            f"min={min(counts)} mean={mean(counts):.1f} max={max(counts)}"
        )

    if raw["missing_dates"]:
        preview = ", ".join(day.isoformat() for day in raw["missing_dates"][:8])
        suffix = " ..." if len(raw["missing_dates"]) > 8 else ""
        print(f"Missing dates inside range: {len(raw['missing_dates'])} ({preview}{suffix})")
    else:
        print("Missing dates inside range: 0")

    print()
    print("Selected one-per-date lead buckets")
    print("lead  n_dates  mean_lead  max_dist  bias    MAE    RMSE  mean_XND")
    print("----  -------  ---------  --------  ------  -----  -----  --------")

    by_bucket = defaultdict(list)
    for row in selected:
        by_bucket[row["lead_bucket"]].append(row)

    for bucket in buckets:
        rows = by_bucket.get(bucket, [])
        if not rows:
            print(f"{bucket:>4}  {0:>7}  -          -         -       -      -      -")
            continue

        errors = [row["error"] for row in rows]
        sigmas = [row["forecast_sigma"] for row in rows if row["forecast_sigma"] is not None]
        rmse = math.sqrt(mean(value * value for value in errors))
        mean_sigma = "-" if not sigmas else f"{mean(sigmas):.2f}"
        print(
            f"{bucket:>4}  {len(rows):>7}  {mean(row['lead_hours'] for row in rows):>9.2f}  "
            f"{max(row['distance_to_bucket'] for row in rows):>8.2f}  "
            f"{mean(errors):>+6.2f}  {mean(abs(x) for x in errors):>5.2f}  "
            f"{rmse:>5.2f}  {mean_sigma:>8}"
        )

    print()
    print(f"Selected rows: {len(selected):,}")

    if selected:
        print("First selected rows:")
        for row in selected[:6]:
            print(
                f"  {row['target_date']} lead={row['lead_hours']:.1f}h "
                f"bucket={row['lead_bucket']}h forecast={row['forecast']:.0f} "
                f"actual={row['actual']:.0f} error={row['error']:+.0f} "
                f"xnd={row['forecast_sigma']}"
            )

    if raw["structural_errors"]:
        print()
        print("STRUCTURAL AUDIT FAILED")
        for error in raw["structural_errors"][:20]:
            print(f"  - {error}")
        raise SystemExit(2)

    print()
    print("Structural audit passed.")


if __name__ == "__main__":
    main()
