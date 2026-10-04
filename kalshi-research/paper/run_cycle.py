#!/usr/bin/env python3
"""Run one idempotent paper-trading maintenance/evaluation cycle."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Settle resolved paper positions, then evaluate the latest NYC "
            "market snapshot and record any new qualifying signals."
        )
    )
    parser.add_argument("--db", type=Path, default=Path("kalshi.db"))
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("data/models/nbm_error_model.json"),
    )
    parser.add_argument("--event")
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument("--execution-buffer", type=float, default=0.005)
    parser.add_argument("--min-qty", type=float, default=10.0)
    parser.add_argument("--max-contracts", type=int, default=25)
    parser.add_argument("--max-model-distance", type=float, default=6.0)
    parser.add_argument("--anchor-hour", type=int, default=15)
    parser.add_argument("--skip-settle", action="store_true")
    return parser.parse_args()


def build_commands(args) -> list[list[str]]:
    py = sys.executable
    commands: list[list[str]] = []

    if not args.skip_settle:
        commands.append(
            [
                py,
                "-m",
                "paper.settle",
                "--ledger",
                str(args.ledger),
            ]
        )

    record = [
        py,
        "-m",
        "paper.record_signals",
        "--db",
        str(args.db),
        "--ledger",
        str(args.ledger),
        "--model",
        str(args.model),
        "--min-edge",
        str(args.min_edge),
        "--execution-buffer",
        str(args.execution_buffer),
        "--min-qty",
        str(args.min_qty),
        "--max-contracts",
        str(args.max_contracts),
        "--max-model-distance",
        str(args.max_model_distance),
        "--anchor-hour",
        str(args.anchor_hour),
    ]
    if args.event:
        record.extend(["--event", args.event])

    commands.append(record)
    return commands


def main():
    args = parse_args()
    failures = []

    for command in build_commands(args):
        print("$ " + " ".join(command), flush=True)
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            failures.append((command, completed.returncode))

    if failures:
        details = "; ".join(
            f"{' '.join(command)} -> {code}"
            for command, code in failures
        )
        raise SystemExit(f"Paper cycle completed with failures: {details}")

    print("Paper cycle completed successfully.")


if __name__ == "__main__":
    main()
