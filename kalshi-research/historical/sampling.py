from __future__ import annotations

import csv
import math
from datetime import date
from pathlib import Path


def nearest_bucket(
    lead_hours: float,
    buckets: tuple[int, ...],
    max_distance: float,
) -> int | None:
    bucket = min(buckets, key=lambda value: abs(value - lead_hours))
    return bucket if abs(bucket - lead_hours) <= max_distance else None


def load_bucketed_rows(
    path: Path,
    buckets: tuple[int, ...],
    max_distance: float,
) -> list[dict]:
    """Load one best forecast per target-date / lead-bucket pair.

    NBM is issued on a six-hour cadence. More than one cycle can fall within the
    tolerance around a nominal 12/24/36/... hour bucket. Counting all of them
    would overweight a single realized day and make sample sizes look larger
    than they really are. Keep only the cycle whose actual lead is closest to
    the requested bucket; break exact ties in favor of the later runtime by
    choosing the smaller lead.
    """
    candidates: dict[tuple[date, int], dict] = {}

    with path.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            try:
                target = date.fromisoformat(raw["target_date"])
                lead = float(raw["lead_hours"])
                forecast = float(raw["forecast_high_f"])
                actual = float(raw["actual_high_f"])
                error = float(raw["error_f"])
            except (KeyError, TypeError, ValueError):
                continue

            if not all(math.isfinite(value) for value in (lead, forecast, actual, error)):
                continue

            bucket = nearest_bucket(lead, buckets, max_distance)
            if bucket is None:
                continue

            record = {
                "target_date": target,
                "lead_bucket": bucket,
                "lead_hours": lead,
                "forecast": forecast,
                "actual": actual,
                "error": error,
                "distance_to_bucket": abs(lead - bucket),
                "forecast_sigma": None,
                "runtime_utc": raw.get("runtime_utc"),
                "valid_utc": raw.get("valid_utc"),
                "forecast_source": raw.get("forecast_source"),
                "txn_forecast": None,
                "txn_error": None,
                "early_tmp_forecast": None,
            }

            optional_numeric = {
                "txn_high_f": "txn_forecast",
                "txn_error_f": "txn_error",
                "early_tmp_high_f": "early_tmp_forecast",
            }
            for raw_name, record_name in optional_numeric.items():
                try:
                    value_text = raw.get(raw_name)
                    if value_text not in (None, ""):
                        value = float(value_text)
                        if math.isfinite(value):
                            record[record_name] = value
                except ValueError:
                    pass

            try:
                sigma_text = raw.get("forecast_sigma_f")
                if sigma_text not in (None, ""):
                    sigma = float(sigma_text)
                    if math.isfinite(sigma):
                        record["forecast_sigma"] = sigma
            except ValueError:
                pass

            key = (target, bucket)
            previous = candidates.get(key)
            if previous is None:
                candidates[key] = record
                continue

            current_rank = (
                record["distance_to_bucket"],
                record["lead_hours"],
            )
            previous_rank = (
                previous["distance_to_bucket"],
                previous["lead_hours"],
            )
            if current_rank < previous_rank:
                candidates[key] = record

    return sorted(
        candidates.values(),
        key=lambda row: (row["target_date"], row["lead_bucket"]),
    )
