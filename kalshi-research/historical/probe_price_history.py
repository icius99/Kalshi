#!/usr/bin/env python3
"""Probe current vs archived KXHIGHNY candlestick access."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import requests

BASE="https://external-api.kalshi.com/trade-api/v2"
SERIES="KXHIGHNY"


def get(path, params=None):
    r=requests.get(f"{BASE}{path}",params=params,timeout=30)
    print("GET",r.url,"status",r.status_code)
    if r.status_code>=400:
        print(r.text[:1000])
        return None
    return r.json()


def probe_event(event_ticker: str, asof: datetime):
    print()
    print("EVENT",event_ticker)
    event=get(f"/events/{event_ticker}",{"with_nested_markets":"true"})
    if not event:
        return
    event_obj=event.get("event",event)
    markets=event_obj.get("markets") or []
    print("markets",len(markets))
    print("tickers",[m.get("ticker") for m in markets])

    start=int((asof-timedelta(hours=4)).timestamp())
    end=int((asof+timedelta(hours=1)).timestamp())
    candles=get(
        f"/series/{SERIES}/events/{event_ticker}/candlesticks",
        {"start_ts":start,"end_ts":end,"period_interval":60},
    )
    if candles:
        print("event candle keys",candles.keys())
        print("market_tickers",candles.get("market_tickers"))
        arrays=candles.get("market_candlesticks") or []
        print("candles/market",[len(x) for x in arrays])
        for ticker,arr in zip(candles.get("market_tickers") or [],arrays):
            if arr:
                print("sample",ticker,json.dumps(arr[-1],indent=2)[:2000])
                break

    historical_markets=get(
        "/historical/markets",
        {"event_ticker":event_ticker,"limit":1000},
    )
    archived=(historical_markets or {}).get("markets") or []
    print("archived markets",len(archived))
    if archived:
        ticker=archived[0]["ticker"]
        hist=get(
            f"/historical/markets/{ticker}/candlesticks",
            {"start_ts":start,"end_ts":end,"period_interval":60},
        )
        if hist:
            arr=hist.get("candlesticks") or []
            print("historical single",ticker,"candles",len(arr))
            if arr:
                print("historical sample",json.dumps(arr[-1],indent=2)[:2000])


def main():
    probe_event(
        "KXHIGHNY-25SEP25",
        datetime(2025,9,24,19,0,tzinfo=timezone.utc),
    )
    probe_event(
        "KXHIGHNY-26SEP25",
        datetime(2026,9,24,19,0,tzinfo=timezone.utc),
    )


if __name__=="__main__":
    main()
