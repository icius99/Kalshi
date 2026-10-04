#!/usr/bin/env python3
"""Compare the latest collected Kalshi snapshot with fresh public orderbooks."""

from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import requests

from collector import BASE, get_best_prices
from paper.current_signals import latest_event, load_markets


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("kalshi.db"))
    parser.add_argument("--event")
    parser.add_argument(
        "--fail-diff",
        type=float,
        default=0.10,
        help="Exit non-zero if any comparable bid/ask moves by this many dollars.",
    )
    return parser.parse_args()


def fetch_live_quotes(
    ticker: str,
    session: requests.Session | None = None,
) -> tuple[float | None, float | None, float | None, float | None]:
    client = session or requests.Session()
    response = client.get(
        f"{BASE}/markets/{ticker}/orderbook",
        timeout=10,
    )
    response.raise_for_status()
    book = response.json()["orderbook_fp"]
    return get_best_prices(book)


def price_delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return abs(float(a) - float(b))


def fmt_price(value: float | None) -> str:
    return "-" if value is None else f"{float(value):.2f}"


def fmt_delta(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def main():
    args = parse_args()

    conn = sqlite3.connect(args.db)
    event, snapshot_ts = latest_event(conn, args.event)
    stored = load_markets(conn, event, snapshot_ts)
    conn.close()

    fetch_started = datetime.now(timezone.utc)
    session = requests.Session()

    print(f"Event:              {event}")
    print(f"Stored snapshot:    {snapshot_ts}")
    print(f"Live audit started: {fetch_started.isoformat()}")
    print()
    print("market                      stored bid/ask  live bid/ask   Δbid  Δask")
    print("--------------------------  --------------  -------------  ----  ----")

    max_diff = 0.0
    comparable = 0

    for market in sorted(stored, key=lambda item: item["market_ticker"]):
        ticker = market["market_ticker"]
        live_bid, _, live_ask, _ = fetch_live_quotes(ticker, session)

        bid_delta = price_delta(market.get("yes_bid"), live_bid)
        ask_delta = price_delta(market.get("yes_ask"), live_ask)

        for delta in (bid_delta, ask_delta):
            if delta is not None:
                comparable += 1
                max_diff = max(max_diff, delta)

        print(
            f"{ticker:<26}  "
            f"{fmt_price(market.get('yes_bid'))}/{fmt_price(market.get('yes_ask')):<5}  "
            f"{fmt_price(live_bid)}/{fmt_price(live_ask):<5}  "
            f"{fmt_delta(bid_delta):>4}  {fmt_delta(ask_delta):>4}"
        )

    print()
    print(f"Comparable quote sides: {comparable}")
    print(f"Maximum absolute quote delta: {max_diff:.2f}")

    if comparable == 0:
        raise SystemExit("No comparable quote sides were available.")

    if args.fail_diff > 0 and max_diff >= args.fail_diff:
        raise SystemExit(
            f"QUOTE AUDIT FAILED: max delta {max_diff:.2f} "
            f">= threshold {args.fail_diff:.2f}"
        )

    print("QUOTE AUDIT PASSED.")


if __name__ == "__main__":
    main()
