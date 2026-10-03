#!/usr/bin/env python3
"""Audit NWS Central Park daily highs against settled KXHIGHNY winning buckets."""

from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import requests

from historical.build_nbm_history import (
    DEFAULT_STATION,
    USER_AGENT,
    fetch_observations,
)
from research.temperature import bucket_from_market

BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXHIGHNY"
MONTHS = {
    name: number
    for number, name in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
         "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        1,
    )
}
EVENT_RE = re.compile(r"^(?:KX)?HIGHNY-(\d{2})([A-Z]{3})(\d{2})$")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 8, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--station", default=DEFAULT_STATION)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/models/settlement_basis_audit.json"),
    )
    return parser.parse_args()


def event_date(event_ticker: str) -> date | None:
    match = EVENT_RE.fullmatch(event_ticker)
    if not match:
        return None
    year, month, day = match.groups()
    if month not in MONTHS:
        return None
    return date(2000 + int(year), MONTHS[month], int(day))


def get_json(
    session: requests.Session,
    path: str,
    params: dict | None = None,
    max_attempts: int = 5,
) -> dict:
    last_exception = None
    for attempt in range(max_attempts):
        try:
            response = session.get(f"{BASE}{path}", params=params, timeout=30)
        except requests.RequestException as exc:
            last_exception = exc
            if attempt == max_attempts - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == max_attempts - 1:
                response.raise_for_status()
            retry_after = response.headers.get("Retry-After")
            try:
                delay = float(retry_after) if retry_after else 1.5 * (attempt + 1)
            except ValueError:
                delay = 1.5 * (attempt + 1)
            time.sleep(max(1.5, delay))
            continue

        response.raise_for_status()
        return response.json()

    if last_exception is not None:
        raise last_exception
    raise RuntimeError(f"failed to fetch {path}")


def fetch_paged_markets(
    session: requests.Session,
    path: str,
    params: dict,
) -> list[dict]:
    markets = []
    cursor = None
    while True:
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        payload = get_json(session, path, query)
        markets.extend(payload.get("markets", []))
        cursor = payload.get("cursor")
        if not cursor:
            break
    return markets


def fetch_all_settled_markets(session: requests.Session) -> list[dict]:
    """Combine current and archived settled markets, deduplicated by ticker."""
    combined: dict[str, dict] = {}

    current = fetch_paged_markets(
        session,
        "/markets",
        {"series_ticker": SERIES, "status": "settled", "limit": 1000},
    )
    historical = fetch_paged_markets(
        session,
        "/historical/markets",
        {"series_ticker": SERIES, "limit": 1000},
    )

    # Historical first, current second, so current wins any overlap.
    for market in historical + current:
        ticker = market.get("ticker")
        if ticker:
            combined[ticker] = market

    return list(combined.values())


def event_partition(markets: list[dict]):
    """Return sorted temperature buckets if markets form one exhaustive partition."""
    parsed = []
    try:
        for market in markets:
            bucket = bucket_from_market(
                market["ticker"],
                market.get("floor_strike"),
                market.get("cap_strike"),
            )
            parsed.append((market, bucket))
    except (KeyError, TypeError, ValueError):
        return None, "non_temperature_bucket"

    if not parsed:
        return None, "empty_event"

    parsed.sort(key=lambda item: item[1].lower)
    if parsed[0][1].lower != float("-inf"):
        return None, "not_exhaustive_partition"
    if parsed[-1][1].upper != float("inf"):
        return None, "not_exhaustive_partition"

    for (_, previous), (_, current) in zip(parsed, parsed[1:]):
        if previous.upper == float("inf"):
            return None, "overlapping_partition"
        if abs(current.lower - (previous.upper + 1.0)) > 1e-9:
            if current.lower <= previous.upper:
                return None, "overlapping_partition"
            return None, "gapped_partition"

    return parsed, None


def classify_event(markets: list[dict], actual_high: float) -> dict:
    partition, reason = event_partition(markets)
    if partition is None:
        return {"usable": False, "reason": reason}

    winners = [market for market in markets if market.get("result") == "yes"]
    if len(winners) != 1:
        return {"usable": False, "reason": f"{len(winners)}_yes_winners"}

    matching = [
        (market, bucket)
        for market, bucket in partition
        if bucket.lower <= actual_high <= bucket.upper
    ]
    if len(matching) != 1:
        # An exhaustive integer partition should make this impossible.
        return {"usable": False, "reason": f"{len(matching)}_cli_bucket_matches"}

    winner = winners[0]
    cli_market, cli_bucket = matching[0]
    winner_bucket = next(
        bucket for market, bucket in partition
        if market["ticker"] == winner["ticker"]
    )

    same = winner["ticker"] == cli_market["ticker"]
    return {
        "usable": True,
        "same_bucket": same,
        "winner_ticker": winner["ticker"],
        "winner_bucket": winner_bucket.label,
        "cli_ticker": cli_market["ticker"],
        "cli_bucket": cli_bucket.label,
    }


def bucket_distance(cli_high: float, winning_market: dict) -> float:
    """Signed degrees from CLI high to nearest point inside the winning bucket."""
    bucket = bucket_from_market(
        winning_market["ticker"],
        winning_market.get("floor_strike"),
        winning_market.get("cap_strike"),
    )
    if bucket.lower <= cli_high <= bucket.upper:
        return 0.0
    if cli_high < bucket.lower:
        return bucket.lower - cli_high
    return bucket.upper - cli_high


def run_audit(
    markets: list[dict],
    observations: dict[date, float],
    start: date,
    end: date,
) -> dict:
    grouped = defaultdict(list)
    for market in markets:
        ticker = market.get("event_ticker")
        target = event_date(ticker) if ticker else None
        if target is None or not (start <= target <= end):
            continue
        grouped[ticker].append(market)

    rows = []
    skipped = Counter()

    for event_ticker, event_markets in sorted(
        grouped.items(), key=lambda item: event_date(item[0]) or date.min
    ):
        target = event_date(event_ticker)
        if target is None:
            continue
        actual = observations.get(target)
        if actual is None:
            skipped["missing_cli_observation"] += 1
            continue

        result = classify_event(event_markets, actual)
        if not result["usable"]:
            skipped[result["reason"]] += 1
            continue

        winner = next(
            market for market in event_markets
            if market.get("ticker") == result["winner_ticker"]
        )
        distance = bucket_distance(actual, winner)

        rows.append({
            "date": target.isoformat(),
            "event_ticker": event_ticker,
            "cli_high_f": actual,
            "kalshi_winner_ticker": result["winner_ticker"],
            "kalshi_winner_bucket": result["winner_bucket"],
            "cli_bucket_ticker": result["cli_ticker"],
            "cli_bucket": result["cli_bucket"],
            "same_bucket": result["same_bucket"],
            "degrees_to_winning_bucket": distance,
        })

    matches = sum(1 for row in rows if row["same_bucket"])
    mismatches = [row for row in rows if not row["same_bucket"]]

    by_year = {}
    for year in sorted({int(row["date"][:4]) for row in rows}):
        year_rows = [row for row in rows if int(row["date"][:4]) == year]
        year_matches = sum(1 for row in year_rows if row["same_bucket"])
        by_year[str(year)] = {
            "usable_events": len(year_rows),
            "same_bucket_events": year_matches,
            "mismatch_events": len(year_rows) - year_matches,
            "same_bucket_rate": year_matches / len(year_rows),
        }

    distance_counts = Counter(
        str(abs(int(row["degrees_to_winning_bucket"])))
        if float(row["degrees_to_winning_bucket"]).is_integer()
        else str(abs(row["degrees_to_winning_bucket"]))
        for row in mismatches
    )

    return {
        "series": SERIES,
        "station": DEFAULT_STATION,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "usable_events": len(rows),
        "same_bucket_events": matches,
        "mismatch_events": len(mismatches),
        "same_bucket_rate": (matches / len(rows)) if rows else None,
        "usable_date_range": (
            [rows[0]["date"], rows[-1]["date"]] if rows else None
        ),
        "by_year": by_year,
        "skipped": dict(sorted(skipped.items())),
        "mismatch_distance_counts_f": dict(sorted(distance_counts.items())),
        "mismatches": mismatches,
    }


def print_report(report: dict):
    print("KXHIGHNY SETTLEMENT-BASIS AUDIT")
    print(f"Period: {report['start']} .. {report['end']}")
    print(f"Usable partition events: {report['usable_events']:,}")
    print(f"Same NWS CLI/Kalshi bucket: {report['same_bucket_events']:,}")
    print(f"Mismatches: {report['mismatch_events']:,}")
    rate = report["same_bucket_rate"]
    print(f"Bucket agreement: {rate:.2%}" if rate is not None else "Bucket agreement: n/a")
    print(f"Usable date range: {report['usable_date_range']}")
    print("By year:")
    for year, stats in report["by_year"].items():
        print(
            f"  {year}: n={stats['usable_events']} "
            f"agreement={stats['same_bucket_rate']:.2%}"
        )
    print(f"Skipped: {report['skipped']}")
    print(f"Mismatch distance from winning bucket (F): {report['mismatch_distance_counts_f']}")

    mismatches = report["mismatches"]
    if mismatches:
        print()
        print("First mismatches:")
        for row in mismatches[:25]:
            print(
                f"  {row['date']} CLI={row['cli_high_f']:.0f}F "
                f"CLI bucket={row['cli_bucket']} "
                f"Kalshi={row['kalshi_winner_bucket']} "
                f"distance={row['degrees_to_winning_bucket']:+.0f}F"
            )


def main():
    args = parse_args()
    if args.end < args.start:
        raise SystemExit("--end must be >= --start")

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    markets = fetch_all_settled_markets(session)
    print(f"Fetched {len(markets):,} unique settled KXHIGHNY markets")

    observations = fetch_observations(
        session,
        args.station,
        args.start,
        args.end,
        request_sleep=0.35,
    )
    print(f"Fetched {len(observations):,} parsed CLI observations")
    print()

    report = run_audit(markets, observations, args.start, args.end)
    print_report(report)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print()
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
