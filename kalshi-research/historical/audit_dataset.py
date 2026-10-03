#!/usr/bin/env python3
"""Audit a generated NBM-vs-CLI historical dataset before fitting models."""

from __future__ import annotations

import argparse
import csv
import math
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from statistics import mean, median, pstdev


EXPECTED_LEADS = (12, 24, 36, 48, 60, 72)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--lead-tolerance", type=float, default=5.0)
    parser.add_argument("--show-largest", type=int, default=10)
    return parser.parse_args()


def nearest_lead(value: float, tolerance: float) -> int | None:
    lead = min(EXPECTED_LEADS, key=lambda x: abs(x - value))
    return lead if abs(lead - value) <= tolerance else None


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                target = date.fromisoformat(row["target_date"])
                lead = float(row["lead_hours"])
                forecast = float(row["forecast_high_f"])
                actual = float(row["actual_high_f"])
                error = float(row["error_f"])
                sigma_text = row.get("forecast_sigma_f", "").strip()
                sigma = float(sigma_text) if sigma_text else None
            except (KeyError, TypeError, ValueError) as exc:
                raise SystemExit(
                    f"Malformed row at CSV line {line_number}: {exc}"
                ) from exc

            rows.append(
                {
                    "target_date": target,
                    "runtime_utc": row["runtime_utc"],
                    "valid_utc": row["valid_utc"],
                    "lead_hours": lead,
                    "forecast_high_f": forecast,
                    "forecast_sigma_f": sigma,
                    "actual_high_f": actual,
                    "error_f": error,
                }
            )
    return rows


def audit(rows: list[dict], tolerance: float) -> dict:
    if not rows:
        raise SystemExit("Dataset is empty.")

    issues = []
    by_date = defaultdict(list)
    by_lead = defaultdict(list)

    for row in rows:
        by_date[row["target_date"]].append(row)
        bucket = nearest_lead(row["lead_hours"], tolerance)
        if bucket is None:
            issues.append(
                f"{row['target_date']}: unexpected lead {row['lead_hours']:.1f}h"
            )
        else:
            by_lead[bucket].append(row)

        recomputed = row["actual_high_f"] - row["forecast_high_f"]
        if not math.isclose(recomputed, row["error_f"], abs_tol=1e-9):
            issues.append(
                f"{row['target_date']} {row['runtime_utc']}: "
                f"error mismatch stored={row['error_f']:.1f} "
                f"computed={recomputed:.1f}"
            )

    dates = sorted(by_date)
    duplicate_runtime_keys = Counter(
        (row["target_date"], row["runtime_utc"]) for row in rows
    )
    duplicates = [key for key, count in duplicate_runtime_keys.items() if count > 1]
    for target, runtime in duplicates:
        issues.append(f"duplicate target/runtime: {target} {runtime}")

    summary = {
        "rows": len(rows),
        "days": len(dates),
        "first_date": dates[0],
        "last_date": dates[-1],
        "issues": issues,
        "by_lead": {},
    }

    for lead in EXPECTED_LEADS:
        values = by_lead.get(lead, [])
        errors = [row["error_f"] for row in values]
        sigmas = [
            row["forecast_sigma_f"]
            for row in values
            if row["forecast_sigma_f"] is not None
        ]
        summary["by_lead"][lead] = {
            "n": len(values),
            "bias": mean(errors) if errors else None,
            "mae": mean(abs(x) for x in errors) if errors else None,
            "rmse": math.sqrt(mean(x * x for x in errors)) if errors else None,
            "sd": pstdev(errors) if len(errors) > 1 else None,
            "median_error": median(errors) if errors else None,
            "mean_xnd": mean(sigmas) if sigmas else None,
        }

    return summary


def fmt(value, digits=2):
    return "-" if value is None else f"{value:.{digits}f}"


def main():
    args = parse_args()
    rows = load_rows(args.dataset)
    result = audit(rows, args.lead_tolerance)

    print(f"Dataset: {args.dataset}")
    print(
        f"Rows: {result['rows']:,} across {result['days']:,} target days "
        f"({result['first_date']} .. {result['last_date']})"
    )
    print()
    print("lead   n    bias    MAE   RMSE     SD   mean XND")
    print("----  ---  ------  -----  -----  -----  --------")
    for lead in EXPECTED_LEADS:
        stats = result["by_lead"][lead]
        print(
            f"{lead:>4}  {stats['n']:>3}  "
            f"{fmt(stats['bias']):>6}  {fmt(stats['mae']):>5}  "
            f"{fmt(stats['rmse']):>5}  {fmt(stats['sd']):>5}  "
            f"{fmt(stats['mean_xnd']):>8}"
        )

    print()
    print("Largest absolute forecast errors")
    print("-------------------------------")
    largest = sorted(
        rows,
        key=lambda row: abs(row["error_f"]),
        reverse=True,
    )[: args.show_largest]
    for row in largest:
        print(
            f"{row['target_date']} lead={row['lead_hours']:5.1f}h "
            f"fcst={row['forecast_high_f']:5.1f} "
            f"actual={row['actual_high_f']:5.1f} "
            f"error={row['error_f']:+5.1f} "
            f"xnd={fmt(row['forecast_sigma_f'], 1)}"
        )

    print()
    if result["issues"]:
        print(f"AUDIT FAILED: {len(result['issues'])} issue(s)")
        for issue in result["issues"][:20]:
            print(f"  - {issue}")
        if len(result["issues"]) > 20:
            print(f"  ... and {len(result['issues']) - 20} more")
        raise SystemExit(1)

    print("AUDIT PASSED: no structural inconsistencies found.")


if __name__ == "__main__":
    main()
