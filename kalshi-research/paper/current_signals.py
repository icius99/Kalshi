#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from research.error_model import ForecastErrorModel
from research.temperature import bucket_from_market, probabilities_for_markets

NY = ZoneInfo("America/New_York")
EVENT_DATE_RE = re.compile(r"KXHIGHNY-(\\d{2})([A-Z]{3})(\\d{2})")
MONTHS = {m: i for i, m in enumerate(("JAN","FEB","MAR","APR","MAY","JUN","JUL","AUG","SEP","OCT","NOV","DEC"), 1)}


def parse_args():
    p = argparse.ArgumentParser(description="Compare the latest live market snapshot to the fitted weather model.")
    p.add_argument("--db", type=Path, default=Path("kalshi.db"))
    p.add_argument("--model", type=Path, default=Path("data/models/nbm_error_model.json"))
    p.add_argument("--event", help="Event ticker; defaults to the nearest future KXHIGHNY event.")
    p.add_argument("--min-edge", type=float, default=0.05, help="Minimum raw edge after execution buffer.")
    p.add_argument("--execution-buffer", type=float, default=0.01, help="Extra per-contract cost allowance, dollars.")
    p.add_argument("--min-qty", type=float, default=10.0)
    p.add_argument("--max-model-distance", type=float, default=8.0)
    p.add_argument("--anchor-hour", type=int, default=15)
    return p.parse_args()


def event_date(ticker: str) -> date:
    m = EVENT_DATE_RE.fullmatch(ticker)
    if not m:
        raise ValueError(f"unsupported event ticker {ticker}")
    year, mon, day = m.groups()
    return date(2000 + int(year), MONTHS[mon], int(day))


def latest_event(conn: sqlite3.Connection, explicit: str | None) -> tuple[str, str]:
    if explicit:
        ts = conn.execute(
            "SELECT MAX(timestamp_utc) FROM market_snapshots WHERE event_ticker = ?", (explicit,)
        ).fetchone()[0]
        if ts is None:
            raise SystemExit(f"No snapshots found for {explicit}")
        return explicit, ts

    rows = conn.execute(
        "SELECT event_ticker, MAX(timestamp_utc) ts FROM market_snapshots "
        "WHERE series_ticker='KXHIGHNY' GROUP BY event_ticker"
    ).fetchall()
    now = datetime.now(timezone.utc).astimezone(NY).date()
    candidates = [(event_date(r[0]), r[0], r[1]) for r in rows if event_date(r[0]) >= now]
    if not candidates:
        raise SystemExit("No current/future KXHIGHNY event found")
    _, ticker, ts = min(candidates)
    return ticker, ts


def latest_weather_high(conn: sqlite3.Connection, target: date, market_ts: str) -> tuple[str, float]:
    # Never use a weather collection made after the market snapshot being evaluated.
    weather_ts = conn.execute(
        "SELECT MAX(collected_at_utc) FROM weather_forecasts WHERE collected_at_utc <= ?",
        (market_ts,),
    ).fetchone()[0]
    if weather_ts is None:
        raise SystemExit("No contemporaneous weather snapshot found")
    rows = conn.execute(
        "SELECT temperature_f FROM weather_forecasts WHERE collected_at_utc=? "
        "AND substr(forecast_time,1,10)=? AND temperature_f IS NOT NULL",
        (weather_ts, target.isoformat()),
    ).fetchall()
    if not rows:
        raise SystemExit(f"No weather forecast for {target}")
    return weather_ts, max(float(r[0]) for r in rows)


def load_markets(conn: sqlite3.Connection, event: str, ts: str) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT market_ticker,title,floor_strike,cap_strike,yes_bid,yes_bid_qty,yes_ask,yes_ask_qty "
        "FROM market_snapshots WHERE event_ticker=? AND timestamp_utc=? ORDER BY market_ticker",
        (event, ts),
    ).fetchall()
    return [dict(r) for r in rows]


def main():
    args = parse_args()
    conn = sqlite3.connect(args.db)
    event, market_ts = latest_event(conn, args.event)
    target = event_date(event)
    weather_ts, forecast_high = latest_weather_high(conn, target, market_ts)
    markets = load_markets(conn, event, market_ts)
    conn.close()

    snap_dt = datetime.fromisoformat(market_ts).astimezone(NY)
    anchor = datetime.combine(target, time(args.anchor_hour), tzinfo=NY)
    lead_hours = (anchor - snap_dt).total_seconds() / 3600.0

    model = ForecastErrorModel.load(args.model)
    fit = model.nearest(lead_hours, args.max_model_distance)
    model_mean = forecast_high + fit.bias_f
    probs = probabilities_for_markets(markets, model_mean, fit.sigma_f)

    print(f"Event:          {event} ({target})")
    print(f"Market snapshot:{market_ts}")
    print(f"Weather snapshot:{weather_ts}")
    print(f"NWS high:       {forecast_high:.1f} F")
    print(f"Lead:           {lead_hours:.1f} h -> {fit.lead_hours} h model bucket (n={fit.n})")
    print(f"Model:          mean={model_mean:.2f} F sigma={fit.sigma_f:.2f} F")
    print()
    print("bucket    model    bid/ask   qty@ask  YES edge*  NO edge*   signal")
    print("--------  -------  --------  -------  ---------  ---------  ------")

    any_signal = False
    for m in sorted(markets, key=lambda x: bucket_from_market(x["market_ticker"], x.get("floor_strike"), x.get("cap_strike")).lower):
        p = probs[m["market_ticker"]]
        bid = m["yes_bid"]
        ask = m["yes_ask"]
        yes_qty = m["yes_ask_qty"] or 0.0
        no_qty = m["yes_bid_qty"] or 0.0
        yes_edge = None if ask is None else p - float(ask) - args.execution_buffer
        no_ask = None if bid is None else 1.0 - float(bid)
        no_edge = None if no_ask is None else (1.0 - p) - no_ask - args.execution_buffer
        signal = ""
        if yes_edge is not None and yes_edge >= args.min_edge and yes_qty >= args.min_qty:
            signal = "BUY YES"
            any_signal = True
        elif no_edge is not None and no_edge >= args.min_edge and no_qty >= args.min_qty:
            signal = "BUY NO"
            any_signal = True
        bucket = bucket_from_market(m["market_ticker"], m.get("floor_strike"), m.get("cap_strike"))
        fmt = lambda v: "   -   " if v is None else f"{v:7.1%}"
        spread = f"{float(bid):.2f}/{float(ask):.2f}" if bid is not None and ask is not None else f"{bid}/{ask}"
        print(f"{bucket.label:<8}  {p:7.1%}  {spread:<8}  {yes_qty:7.1f}  {fmt(yes_edge)}  {fmt(no_edge)}  {signal}")

    print("\n*Edge subtracts the configured execution buffer but does NOT yet encode Kalshi's exact fee schedule.")
    if not any_signal:
        print("No paper-trade signal meets the configured threshold/liquidity rules.")


if __name__ == "__main__":
    main()
