#!/usr/bin/env python3
"""Run the historical research workflow with date-stamped outputs.

This orchestrates existing modules; it does not duplicate their model logic.
The generated model is not promoted to the live default path unless explicitly
requested with --promote-model.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path


DEFAULT_BUCKETS = "12,24,36,48,60"


@dataclass(frozen=True)
class PipelinePaths:
    dataset: Path
    validation: Path
    model: Path
    promoted_model: Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--test-start", type=date.fromisoformat)
    parser.add_argument("--historical-dir", type=Path, default=Path("data/historical"))
    parser.add_argument("--model-dir", type=Path, default=Path("data/models"))
    parser.add_argument("--buckets", default=DEFAULT_BUCKETS)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument(
        "--promote-model",
        action="store_true",
        help=(
            "After all prior stages succeed, copy the dated model to "
            "data/models/nbm_error_model.json for live paper-signal use."
        ),
    )
    return parser.parse_args()


def make_paths(
    start: date,
    end: date,
    historical_dir: Path,
    model_dir: Path,
) -> PipelinePaths:
    tag = f"{start:%Y%m%d}_{end:%Y%m%d}"
    return PipelinePaths(
        dataset=historical_dir / f"nbm_nyc_{tag}.csv",
        validation=model_dir / f"nbm_validation_{tag}.json",
        model=model_dir / f"nbm_error_model_{tag}.json",
        promoted_model=model_dir / "nbm_error_model.json",
    )


def build_commands(args, paths: PipelinePaths) -> list[list[str]]:
    py = sys.executable
    commands: list[list[str]] = []

    if not args.skip_build:
        commands.append(
            [
                py,
                "-m",
                "historical.build_nbm_history",
                "--start",
                args.start.isoformat(),
                "--end",
                args.end.isoformat(),
                "--output",
                str(paths.dataset),
            ]
        )

    commands.append(
        [
            py,
            "-m",
            "historical.audit_dataset",
            str(paths.dataset),
        ]
    )

    commands.append(
        [
            py,
            "-m",
            "historical.compare_calendar_high",
            str(paths.dataset),
            "--buckets",
            args.buckets,
        ]
    )

    validation = [
        py,
        "-m",
        "historical.validate_chronological",
        str(paths.dataset),
        "--buckets",
        args.buckets,
        "--output",
        str(paths.validation),
    ]
    if args.test_start is not None:
        validation.extend(["--test-start", args.test_start.isoformat()])
    commands.append(validation)

    commands.append(
        [
            py,
            "-m",
            "historical.forecast_error",
            str(paths.dataset),
            "--buckets",
            args.buckets,
            "--output",
            str(paths.model),
        ]
    )

    return commands


def run_command(command: list[str]) -> None:
    print()
    print("$ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main():
    args = parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be on or after --start")

    paths = make_paths(
        args.start,
        args.end,
        args.historical_dir,
        args.model_dir,
    )
    paths.dataset.parent.mkdir(parents=True, exist_ok=True)
    paths.validation.parent.mkdir(parents=True, exist_ok=True)

    print("Historical research pipeline")
    print(f"  range:      {args.start} .. {args.end}")
    print(f"  dataset:    {paths.dataset}")
    print(f"  validation: {paths.validation}")
    print(f"  model:      {paths.model}")
    if args.test_start:
        print(f"  holdout:    {args.test_start} and later")
    else:
        print("  holdout:    automatic chronological 75/25 split")

    for command in build_commands(args, paths):
        run_command(command)

    if args.promote_model:
        shutil.copy2(paths.model, paths.promoted_model)
        print()
        print(f"Promoted validated model to {paths.promoted_model}")
    else:
        print()
        print("Model was NOT promoted to the live default path.")
        print(
            "Review the audit/validation output first; rerun with "
            "--skip-build --promote-model only when you want to promote it."
        )

    print()
    print("Pipeline completed successfully.")


if __name__ == "__main__":
    main()
