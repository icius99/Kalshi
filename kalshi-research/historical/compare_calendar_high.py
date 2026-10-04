#!/usr/bin/env python3
"""Compare calendar-day hybrid forecasts against raw TXN on identical samples."""

from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from statistics import mean

from historical.sampling import load_bucketed_rows

DEFAULT_BUCKETS = (12, 24, 36, 48, 60)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--buckets", default=",".join(map(str, DEFAULT_BUCKETS)))
    parser.add_argument("--max-distance", type=float, default=5.0)
    return parser.parse_args()


def summarize(rows: list[dict]) -> dict:
    comparable = [
        row for row in rows
        if row.get("txn_error") is not None
    ]
    if not comparable:
        return {
            "n": 0,
            "hybrid_rmse": None,
            "txn_rmse": None,
            "hybrid_mae": None,
            "txn_mae": None,
            "early_tmp_n": 0,
        }

    hybrid_errors = [row["error"] for row in comparable]
    txn_errors = [row["txn_error"] for row in comparable]
    early_tmp_n = sum(
        1 for row in comparable if row.get("forecast_source") == "early_tmp"
    )

    return {
        "n": len(comparable),
        "hybrid_rmse": math.sqrt(mean(error * error for error in hybrid_errors)),
        "txn_rmse": math.sqrt(mean(error * error for error in txn_errors)),
        "hybrid_mae": mean(abs(error) for error in hybrid_errors),
        "txn_mae": mean(abs(error) for error in txn_errors),
        "early_tmp_n": early_tmp_n,
    }


def fmt(value):
    return "-" if value is None else f"{value:.3f}"


def main():
    args = parse_args()
    buckets = tuple(
        sorted({int(value.strip()) for value in args.buckets.split(",") if value.strip()})
    )

    rows = load_bucketed_rows(args.dataset, buckets, args.max_distance)
    by_lead = defaultdict(list)
    for row in rows:
        by_lead[row["lead_bucket"]].append(row)

    print("Calendar-day hybrid vs raw TXN on identical sampled rows")
    print("lead    n  earlyTMP  hybridRMSE  txnRMSE  hybridMAE  txnMAE")
    print("----  ---  --------  ----------  -------  ---------  ------")

    overall = summarize(rows)
    for bucket in buckets:
        stats = summarize(by_lead.get(bucket, []))
        print(
            f"{bucket:>4}  {stats['n']:>3}  {stats['early_tmp_n']:>8}  "
            f"{fmt(stats['hybrid_rmse']):>10}  {fmt(stats['txn_rmse']):>7}  "
            f"{fmt(stats['hybrid_mae']):>9}  {fmt(stats['txn_mae']):>6}"
        )

    print()
    print(
        f"ALL   {overall['n']:>3}  {overall['early_tmp_n']:>8}  "
        f"{fmt(overall['hybrid_rmse']):>10}  {fmt(overall['txn_rmse']):>7}  "
        f"{fmt(overall['hybrid_mae']):>9}  {fmt(overall['txn_mae']):>6}"
    )

    if overall["n"]:
        rmse_delta = overall["hybrid_rmse"] - overall["txn_rmse"]
        mae_delta = overall["hybrid_mae"] - overall["txn_mae"]
        print()
        print(f"RMSE delta hybrid - TXN: {rmse_delta:+.3f} F")
        print(f"MAE delta hybrid - TXN:  {mae_delta:+.3f} F")


if __name__ == "__main__":
    main()
