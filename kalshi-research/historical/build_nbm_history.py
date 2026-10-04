#!/usr/bin/env python3
"""Build a historical NYC calendar-day high forecast verification dataset.

Forecast source: NWS National Blend of Models (NBS text guidance) archived by
the Iowa Environmental Mesonet (IEM). The predictor combines NBM TXN with
early-morning TMP guidance so it covers the full NYC local calendar day.
Observation source: parsed NWS CLI daily highs for Central Park/KNYC via IEM.

The output is intentionally plain CSV so the modeling layer is decoupled from
network/data-acquisition details.
"""

from __future__ import annotations

import argparse
import csv
import io
import math
import time
from collections import defaultdict
from datetime import date, datetime, time as dtime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

IEM_MOS = "https://mesonet.agron.iastate.edu/cgi-bin/request/mos.py"
IEM_CLI = "https://mesonet.agron.iastate.edu/json/cli.py"
DEFAULT_STATION = "KNYC"
DEFAULT_TZ = "America/New_York"
DEFAULT_MODEL = "NBS"
USER_AGENT = "kalshi-weather-research/0.2 (historical verification)"
FORECAST_DEFINITION = "calendar_day_nbm_txn_plus_early_tmp_v1"
OBSERVATION_DEFINITION = "nws_cli_knyc_calendar_day_high_v1"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, type=date.fromisoformat)
    parser.add_argument("--end", required=True, type=date.fromisoformat)
    parser.add_argument("--station", default=DEFAULT_STATION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timezone", default=DEFAULT_TZ)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/historical/nbm_nyc_daily_high.csv"),
    )
    parser.add_argument(
        "--anchor-hour",
        type=int,
        default=15,
        help="Local hour used to define lead time to the expected daily high.",
    )
    parser.add_argument(
        "--mos-chunk-days",
        type=int,
        default=31,
        help="IEM MOS request span. Smaller chunks are easier to retry.",
    )
    parser.add_argument("--request-sleep", type=float, default=0.35)
    return parser.parse_args()


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if value == "" or value.upper() in {"M", "MM", "NULL", "NONE", "NA"}:
        return None
    return value


def _float(value: str | None) -> float | None:
    value = _clean(value)
    if value is None:
        return None
    try:
        result = float(value)
    except ValueError:
        return None
    return result if math.isfinite(result) else None


def _pick(row: dict[str, str], *names: str) -> str | None:
    lower = {key.lower(): value for key, value in row.items() if key}
    for name in names:
        if name.lower() in lower:
            return lower[name.lower()]
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    value = _clean(value)
    if value is None:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                dt = datetime.strptime(value, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _iter_chunks(start: date, end: date, days: int):
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + timedelta(days=days - 1))
        yield cursor, chunk_end
        cursor = chunk_end + timedelta(days=1)


def fetch_csv(
    session: requests.Session,
    url: str,
    params: dict,
    max_attempts: int = 5,
) -> list[dict[str, str]]:
    """Fetch an IEM CSV endpoint with bounded retry/backoff for throttling."""

    response = None
    last_exception = None
    for attempt in range(max_attempts):
        try:
            response = session.get(url, params=params, timeout=60)
        except requests.RequestException as exc:
            last_exception = exc
            if attempt == max_attempts - 1:
                raise
            time.sleep(2.5 * (attempt + 1))
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == max_attempts - 1:
                response.raise_for_status()

            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 2.5 * (attempt + 1)
            except ValueError:
                delay = 2.5 * (attempt + 1)

            time.sleep(max(2.5, delay))
            continue

        response.raise_for_status()
        break

    if response is None:
        if last_exception is not None:
            raise last_exception
        raise RuntimeError("IEM request did not produce a response")

    text = response.text
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise RuntimeError(f"No CSV header returned by {response.url}")

    # Some IEM CSV services emit a trailing delimiter on data rows. DictReader
    # stores the extra unnamed field under a None key; drop only that phantom
    # column and preserve every named field.
    rows = [
        {key: value for key, value in row.items() if key is not None}
        for row in reader
    ]
    return rows


def parse_cli_observations(
    rows: list[dict[str, str]],
    start: date,
    end: date,
) -> dict[date, float]:
    """Convert parsed NWS CLI CSV rows into target-date daily highs."""
    observations: dict[date, float] = {}

    for row in rows:
        day_text = _pick(row, "valid")
        high = _float(_pick(row, "high"))
        if not day_text or high is None:
            continue

        try:
            day = date.fromisoformat(day_text[:10])
        except ValueError:
            continue

        if start <= day <= end:
            observations[day] = high

    return observations


def fetch_observations(
    session: requests.Session,
    station: str,
    start: date,
    end: date,
    request_sleep: float,
) -> dict[date, float]:
    """Fetch parsed NWS CLI daily highs for Central Park/KNYC.

    IEM's /json/cli.py service returns atomic values parsed directly from NWS
    CLI text products.  This is preferable to the computed daily-summary
    endpoint for NWSCLI stations because KNYC is populated in cli_data even
    when /cgi-bin/request/daily.py returns no rows.
    """
    observations: dict[date, float] = {}

    for year in range(start.year, end.year + 1):
        rows = fetch_csv(
            session,
            IEM_CLI,
            {
                "station": station,
                "year": year,
                "fmt": "csv",
            },
        )

        observations.update(parse_cli_observations(rows, start, end))
        time.sleep(request_sleep)

    return observations


def fetch_mos_rows(
    session: requests.Session,
    station: str,
    model: str,
    start: date,
    end: date,
    chunk_days: int,
    request_sleep: float,
) -> list[dict[str, str]]:
    all_rows: list[dict[str, str]] = []
    for cstart, cend in _iter_chunks(start, end, chunk_days):
        # Include all runs through the end date.  IEM uses UTC run timestamps.
        sts = f"{cstart.isoformat()}T00:00Z"
        ets = f"{(cend + timedelta(days=1)).isoformat()}T00:00Z"
        rows = fetch_csv(
            session,
            IEM_MOS,
            {
                "station": station,
                "model": model,
                "sts": sts,
                "ets": ets,
                "format": "csv",
            },
        )
        all_rows.extend(rows)
        print(f"MOS {cstart}..{cend}: {len(rows):,} rows")
        time.sleep(request_sleep)
    return all_rows


def extract_daily_high_forecasts(
    rows: list[dict[str, str]],
    tz_name: str,
    anchor_hour: int,
) -> list[dict]:
    """Build a calendar-day high forecast from NBS guidance.

    NBM TXN maximum covers 12Z(current day)-06Z(next day), which misses the
    first several hours of the NYC local calendar day.  That matters on frontal
    passages when the day's true high occurs shortly after midnight.

    For each model runtime / target date:
    1. take the documented 00Z TXN maximum for the daytime/evening window;
    2. find TMP guidance from local midnight up to (but not including) 12Z;
    3. use the larger value as the forecast for the full local calendar day.

    XND is used when TXN wins. If an early-morning TMP value wins and TSD is
    available for that valid time, TSD is used instead.
    """
    tz = ZoneInfo(tz_name)

    parsed_rows: list[dict] = []
    by_runtime: dict[datetime, list[dict]] = defaultdict(list)

    for row in rows:
        runtime = _parse_datetime(
            _pick(row, "runtime", "runtime_utc", "run_time", "model_run")
        )
        valid = _parse_datetime(
            _pick(row, "ftime", "ftime_utc", "valid", "valid_time")
        )
        if runtime is None or valid is None:
            continue

        parsed = {
            "raw": row,
            "runtime_utc": runtime,
            "valid_utc": valid,
            "tmp": _float(_pick(row, "tmp")),
            "tsd": _float(_pick(row, "tsd")),
            "txn": _float(_pick(row, "txn")),
            "xnd": _float(_pick(row, "xnd")),
        }
        parsed_rows.append(parsed)
        by_runtime[runtime].append(parsed)

    forecasts: list[dict] = []

    for item in parsed_rows:
        txn = item["txn"]
        valid = item["valid_utc"]
        runtime = item["runtime_utc"]

        if txn is None:
            continue

        # NOAA NBM station-card definition: maximum TXN is reported at 00Z
        # following the 12Z-06Z max-temperature window.
        if valid.hour != 0 or valid.minute != 0:
            continue

        target_date = (valid - timedelta(hours=12)).date()
        anchor = datetime.combine(target_date, dtime(anchor_hour), tzinfo=tz)
        lead_hours = (
            anchor.astimezone(timezone.utc) - runtime
        ).total_seconds() / 3600.0
        if lead_hours < -3 or lead_hours > 168:
            continue

        local_midnight_utc = datetime.combine(
            target_date, dtime(0), tzinfo=tz
        ).astimezone(timezone.utc)
        txn_window_start_utc = datetime.combine(
            target_date, dtime(12), tzinfo=timezone.utc
        )

        early_candidates = [
            candidate
            for candidate in by_runtime[runtime]
            if candidate["tmp"] is not None
            and local_midnight_utc <= candidate["valid_utc"] < txn_window_start_utc
        ]

        early = None
        if early_candidates:
            # Prefer the warmest early-morning point. Break temperature ties in
            # favor of the earlier valid time to keep selection deterministic.
            early = max(
                early_candidates,
                key=lambda candidate: (
                    candidate["tmp"],
                    -candidate["valid_utc"].timestamp(),
                ),
            )

        early_high = None if early is None else early["tmp"]
        early_sigma = None if early is None else early["tsd"]

        if early_high is not None and early_high > txn:
            forecast_high = early_high
            forecast_sigma = early_sigma if early_sigma is not None else item["xnd"]
            forecast_source = "early_tmp"
            source_valid_utc = early["valid_utc"]
        else:
            forecast_high = txn
            forecast_sigma = item["xnd"]
            forecast_source = "txn"
            source_valid_utc = valid

        forecasts.append(
            {
                "target_date": target_date,
                "runtime_utc": runtime,
                "valid_utc": valid,
                "source_valid_utc": source_valid_utc,
                "lead_hours": lead_hours,
                "forecast_high_f": forecast_high,
                "forecast_sigma_f": forecast_sigma,
                "forecast_source": forecast_source,
                "txn_high_f": txn,
                "txn_sigma_f": item["xnd"],
                "early_tmp_high_f": early_high,
                "early_tmp_sigma_f": early_sigma,
            }
        )

    return forecasts


def nearest_per_runtime_target(forecasts: list[dict]) -> list[dict]:
    """Deduplicate repeated rows for the same runtime/target date.

    A conforming NBS bulletin should yield one 00Z daily-maximum TXN record for
    each runtime/target date.  Keep a deterministic record if an archive ever
    contains duplicates.
    """
    groups: dict[tuple[datetime, date], list[dict]] = defaultdict(list)
    for item in forecasts:
        groups[(item["runtime_utc"], item["target_date"])].append(item)

    selected = []
    for values in groups.values():
        values.sort(key=lambda x: x["valid_utc"])
        selected.append(values[0])
    return selected


def write_dataset(path: Path, forecasts: list[dict], observations: dict[date, float]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "target_date",
        "runtime_utc",
        "valid_utc",
        "source_valid_utc",
        "lead_hours",
        "forecast_high_f",
        "forecast_sigma_f",
        "forecast_source",
        "txn_high_f",
        "txn_sigma_f",
        "early_tmp_high_f",
        "early_tmp_sigma_f",
        "actual_high_f",
        "error_f",
        "txn_error_f",
    ]
    count = 0
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for item in sorted(forecasts, key=lambda x: (x["target_date"], x["runtime_utc"])):
            actual = observations.get(item["target_date"])
            if actual is None:
                continue
            error = actual - item["forecast_high_f"]
            txn_error = actual - item["txn_high_f"]
            writer.writerow(
                {
                    "target_date": item["target_date"].isoformat(),
                    "runtime_utc": item["runtime_utc"].isoformat(),
                    "valid_utc": item["valid_utc"].isoformat(),
                    "source_valid_utc": item["source_valid_utc"].isoformat(),
                    "lead_hours": f"{item['lead_hours']:.2f}",
                    "forecast_high_f": f"{item['forecast_high_f']:.1f}",
                    "forecast_sigma_f": (
                        ""
                        if item["forecast_sigma_f"] is None
                        else f"{item['forecast_sigma_f']:.1f}"
                    ),
                    "forecast_source": item["forecast_source"],
                    "txn_high_f": f"{item['txn_high_f']:.1f}",
                    "txn_sigma_f": (
                        ""
                        if item["txn_sigma_f"] is None
                        else f"{item['txn_sigma_f']:.1f}"
                    ),
                    "early_tmp_high_f": (
                        ""
                        if item["early_tmp_high_f"] is None
                        else f"{item['early_tmp_high_f']:.1f}"
                    ),
                    "early_tmp_sigma_f": (
                        ""
                        if item["early_tmp_sigma_f"] is None
                        else f"{item['early_tmp_sigma_f']:.1f}"
                    ),
                    "actual_high_f": f"{actual:.1f}",
                    "error_f": f"{error:.1f}",
                    "txn_error_f": f"{txn_error:.1f}",
                }
            )
            count += 1
    return count


def main() -> None:
    args = parse_args()
    if args.end < args.start:
        raise SystemExit("--end must be on or after --start")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    observations = fetch_observations(
        session, args.station, args.start, args.end, args.request_sleep
    )
    print(f"Observations: {len(observations):,} days")

    # Include runs up to three days before the first target day so the dataset
    # contains 48-72 h lead forecasts for the beginning of the requested span.
    mos_rows = fetch_mos_rows(
        session,
        args.station,
        args.model,
        args.start - timedelta(days=3),
        args.end,
        args.mos_chunk_days,
        args.request_sleep,
    )
    print(f"Raw MOS rows: {len(mos_rows):,}")

    forecasts = extract_daily_high_forecasts(mos_rows, args.timezone, args.anchor_hour)
    forecasts = [f for f in forecasts if args.start <= f["target_date"] <= args.end]
    forecasts = nearest_per_runtime_target(forecasts)
    print(f"Daily-high forecast records: {len(forecasts):,}")

    count = write_dataset(args.output, forecasts, observations)
    print(f"Wrote {count:,} verified forecasts to {args.output}")


if __name__ == "__main__":
    main()
