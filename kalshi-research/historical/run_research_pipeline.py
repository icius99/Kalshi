#!/usr/bin/env python3
"""Run the historical research workflow with date-stamped outputs.

This orchestrates existing modules; it does not duplicate their model logic.
The generated model is not promoted to the live default path unless explicitly
requested with --promote-model.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from historical.build_nbm_history import FORECAST_DEFINITION


DEFAULT_BUCKETS = "12,24,36,48,60"


@dataclass(frozen=True)
class PipelinePaths:
    dataset: Path
    validation: Path
    walkforward: Path
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
        walkforward=model_dir / f"nbm_walkforward_{tag}.json",
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
            "historical.walkforward_compare",
            str(paths.dataset),
            "--buckets",
            args.buckets,
            "--output",
            str(paths.walkforward),
        ]
    )

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


def validate_promotion(paths: PipelinePaths) -> dict:
    """Refuse to promote stale or evidence-incompatible calibration artifacts."""
    if not paths.model.exists():
        raise SystemExit(f"Model file does not exist: {paths.model}")
    if not paths.walkforward.exists():
        raise SystemExit(f"Walk-forward report does not exist: {paths.walkforward}")

    model = json.loads(paths.model.read_text(encoding="utf-8"))
    walkforward = json.loads(paths.walkforward.read_text(encoding="utf-8"))

    if int(model.get("version", 0)) < 4:
        raise SystemExit(
            "Refusing promotion: model schema is older than v4. "
            "Rerun the current pipeline with --skip-build first."
        )
    if model.get("forecast_definition") != FORECAST_DEFINITION:
        raise SystemExit(
            "Refusing promotion: model forecast_definition does not match "
            f"runtime predictor {FORECAST_DEFINITION!r}."
        )

    default_method = model.get("default_probability_method")
    recommendation = walkforward.get("recommended_probability_method")
    if recommendation is None:
        losses = (walkforward.get("aggregate_all") or {}).get("mean_losses") or {}
        if losses:
            recommendation = min(losses, key=losses.get)

    mapping = {
        "empirical_integer_errors": "empirical",
        "scaled_nbm_uncertainty_normal": "scaled_xnd",
    }
    expected = mapping.get(default_method)
    if expected is None:
        raise SystemExit(
            f"Refusing promotion: unsupported default probability method {default_method!r}."
        )
    if recommendation != expected:
        raise SystemExit(
            "Refusing promotion: walk-forward evidence recommends "
            f"{recommendation!r}, but model default is {default_method!r}."
        )

    return {
        "model_version": model["version"],
        "forecast_definition": model["forecast_definition"],
        "default_probability_method": default_method,
        "walkforward_recommendation": recommendation,
    }



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
    print(f"  walkforward:{paths.walkforward}")
    print(f"  model:      {paths.model}")
    if args.test_start:
        print(f"  holdout:    {args.test_start} and later")
    else:
        print("  holdout:    automatic chronological 75/25 split")

    for command in build_commands(args, paths):
        run_command(command)

    if args.promote_model:
        promotion = validate_promotion(paths)
        shutil.copy2(paths.model, paths.promoted_model)
        print()
        print(f"Promoted validated model to {paths.promoted_model}")
        print(
            "  "
            f"schema=v{promotion['model_version']} "
            f"predictor={promotion['forecast_definition']} "
            f"method={promotion['default_probability_method']}"
        )
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
