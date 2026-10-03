#!/usr/bin/env python3
"""Probe Kalshi public settlement-history endpoints for KXHIGHNY."""

from __future__ import annotations

import json
import requests

BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXHIGHNY"


def get_json(path: str, params: dict | None = None):
    response = requests.get(f"{BASE}{path}", params=params, timeout=30)
    print(f"GET {response.url}")
    print(f"  status={response.status_code}")
    if response.status_code >= 400:
        print("  body=" + response.text[:1000].replace("\n", " "))
        return None
    return response.json()


def paged(path: str, item_key: str, params: dict):
    items = []
    cursor = None
    pages = 0
    while True:
        query = dict(params)
        if cursor:
            query["cursor"] = cursor
        data = get_json(path, query)
        if data is None:
            return None
        pages += 1
        batch = data.get(item_key, [])
        items.extend(batch)
        cursor = data.get("cursor")
        if not cursor:
            break
        if pages >= 100:
            raise RuntimeError("pagination runaway")
    print(f"  pages={pages} {item_key}={len(items)}")
    return items


def summarize_events(events):
    if not events:
        print("No events returned.")
        return

    print()
    print("EVENT SAMPLE")
    for event in (events[0], events[-1]) if len(events) > 1 else (events[0],):
        print(json.dumps({
            "event_ticker": event.get("event_ticker"),
            "series_ticker": event.get("series_ticker"),
            "sub_title": event.get("sub_title"),
            "strike_date": event.get("strike_date"),
            "mutually_exclusive": event.get("mutually_exclusive"),
            "market_count": len(event.get("markets") or []),
        }, indent=2))
        markets = event.get("markets") or []
        if markets:
            print("  market keys:", ", ".join(sorted(markets[0].keys())))
            for market in markets[:2]:
                print("  ", {
                    "ticker": market.get("ticker"),
                    "result": market.get("result"),
                    "settlement_value_dollars": market.get("settlement_value_dollars"),
                    "floor_strike": market.get("floor_strike"),
                    "cap_strike": market.get("cap_strike"),
                    "status": market.get("status"),
                })


def main():
    print("KALSHI SETTLEMENT HISTORY PROBE")
    print()

    cutoff = get_json("/historical/cutoff")
    print("historical cutoff:")
    print(json.dumps(cutoff, indent=2)[:3000] if cutoff else "unavailable")
    print()

    events = paged(
        "/events",
        "events",
        {
            "series_ticker": SERIES,
            "status": "settled",
            "with_nested_markets": "true",
            "limit": 200,
        },
    )
    if events is not None:
        summarize_events(events)

    print()
    print("LIVE SETTLED MARKETS")
    markets = paged(
        "/markets",
        "markets",
        {
            "series_ticker": SERIES,
            "status": "settled",
            "limit": 1000,
        },
    )
    if markets:
        print("first:", {
            "ticker": markets[0].get("ticker"),
            "result": markets[0].get("result"),
            "settlement_value_dollars": markets[0].get("settlement_value_dollars"),
            "settlement_ts": markets[0].get("settlement_ts"),
        })
        print("last:", {
            "ticker": markets[-1].get("ticker"),
            "result": markets[-1].get("result"),
            "settlement_value_dollars": markets[-1].get("settlement_value_dollars"),
            "settlement_ts": markets[-1].get("settlement_ts"),
        })

    print()
    print("HISTORICAL MARKETS ATTEMPT")
    historical = paged(
        "/historical/markets",
        "markets",
        {
            "series_ticker": SERIES,
            "limit": 1000,
        },
    )
    if historical:
        print("historical first:", {
            "ticker": historical[0].get("ticker"),
            "result": historical[0].get("result"),
            "settlement_value_dollars": historical[0].get("settlement_value_dollars"),
            "settlement_ts": historical[0].get("settlement_ts"),
        })
        print("historical last:", {
            "ticker": historical[-1].get("ticker"),
            "result": historical[-1].get("result"),
            "settlement_value_dollars": historical[-1].get("settlement_value_dollars"),
            "settlement_ts": historical[-1].get("settlement_ts"),
        })


if __name__ == "__main__":
    main()
