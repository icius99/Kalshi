#!/usr/bin/env python3
"""Walk-forward price backtest for KXHIGHNY using historical NBM forecasts."""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

import requests

from historical.build_nbm_history import USER_AGENT
from historical.sampling import load_bucketed_rows
from historical.settlement_basis import (
    BASE,
    SERIES,
    event_date,
    event_partition,
    fetch_all_settled_markets,
    get_json,
)
from research.error_model import probabilities_from_error_counts
from research.fees import taker_fee
from research.nbm import NBM_PUBLICATION_LAG

NY = ZoneInfo("America/New_York")
DEFAULT_LEADS = (12, 24, 36, 48, 60)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--leads", default=",".join(map(str, DEFAULT_LEADS)))
    parser.add_argument("--max-lead-distance", type=float, default=5.0)
    parser.add_argument("--min-training-samples", type=int, default=365)
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument("--execution-buffer", type=float, default=0.01)
    parser.add_argument("--empirical-alpha", type=float, default=0.1)
    parser.add_argument("--max-quote-staleness-hours", type=float, default=2.0)
    parser.add_argument("--stride-days", type=int, default=1)
    parser.add_argument("--request-sleep", type=float, default=0.05)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/models/price_backtest.json"),
    )
    return parser.parse_args()


def parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def decimal_close(side: dict | None) -> float | None:
    if not side:
        return None
    value = side.get("close_dollars")
    if value is None:
        value = side.get("close")
    if value in (None, ""):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def quote_at(
    candles: list[dict],
    asof_utc: datetime,
    max_staleness_hours: float,
) -> dict | None:
    """Return latest hourly top-of-book close at or before the as-of time."""
    asof_ts = asof_utc.timestamp()
    candidates = [
        candle
        for candle in candles
        if float(candle.get("end_period_ts", math.inf)) <= asof_ts
    ]
    if not candidates:
        return None
    candle = max(candidates, key=lambda item: float(item["end_period_ts"]))
    age_hours = (asof_ts - float(candle["end_period_ts"])) / 3600.0
    if age_hours > max_staleness_hours + 1e-9:
        return None

    bid = decimal_close(candle.get("yes_bid"))
    ask = decimal_close(candle.get("yes_ask"))
    if bid is None and ask is None:
        return None
    return {
        "end_period_ts": int(candle["end_period_ts"]),
        "yes_bid": bid,
        "yes_ask": ask,
        "staleness_hours": age_hours,
    }


def normalize_markets(markets: list[dict]) -> list[dict]:
    return [
        {
            **market,
            "market_ticker": market["ticker"],
        }
        for market in markets
    ]


class CandleClient:
    def __init__(self, session: requests.Session, request_sleep: float = 0.05):
        self.session = session
        self.request_sleep = request_sleep

    def event_candles(
        self,
        event_ticker: str,
        markets: list[dict],
        start_utc: datetime,
        end_utc: datetime,
    ) -> tuple[dict[str, list[dict]], str]:
        params = {
            "start_ts": int(start_utc.timestamp()),
            "end_ts": int(end_utc.timestamp()),
            "period_interval": 60,
        }

        # The event-level endpoint is much cheaper and returns all contracts,
        # but archived events return empty arrays.
        payload = get_json(
            self.session,
            f"/series/{SERIES}/events/{event_ticker}/candlesticks",
            params,
        )
        tickers = payload.get("market_tickers") or []
        arrays = payload.get("market_candlesticks") or []
        if tickers:
            return {
                ticker: candles
                for ticker, candles in zip(tickers, arrays)
            }, "live_event"

        result = {}
        for market in markets:
            ticker = market["ticker"]
            payload = get_json(
                self.session,
                f"/historical/markets/{ticker}/candlesticks",
                params,
            )
            result[ticker] = payload.get("candlesticks") or []
            if self.request_sleep:
                time.sleep(self.request_sleep)
        return result, "historical_markets"


def prior_error_counts(
    rows_by_lead: dict[int, list[dict]],
    lead: int,
    asof_utc: datetime,
) -> Counter:
    """Only use residuals whose target day had already completed locally."""
    local_day = asof_utc.astimezone(NY).date()
    counts = Counter()
    for row in rows_by_lead.get(lead, []):
        if row["target_date"] >= local_day:
            continue
        error = int(round(row["error"]))
        if abs(row["error"] - error) > 1e-6:
            raise ValueError(f"non-integer error {row['error']}")
        counts[error] += 1
    return counts


def best_trade(
    markets: list[dict],
    probabilities: dict[str, float],
    quotes: dict[str, dict | None],
    min_edge: float,
    execution_buffer: float,
) -> dict | None:
    candidates = []

    for market in markets:
        ticker = market["ticker"]
        quote = quotes.get(ticker)
        if not quote:
            continue

        p_yes = probabilities[ticker]
        ask = quote.get("yes_ask")
        bid = quote.get("yes_bid")

        if ask is not None:
            fee = taker_fee(ask, 1)
            edge = p_yes - ask - fee - execution_buffer
            candidates.append({
                "ticker": ticker,
                "side": "YES",
                "entry_price": ask,
                "fee": fee,
                "edge": edge,
                "model_probability_yes": p_yes,
                "quote_ts": quote["end_period_ts"],
            })

        if bid is not None:
            no_ask = 1.0 - bid
            fee = taker_fee(no_ask, 1)
            edge = (1.0 - p_yes) - no_ask - fee - execution_buffer
            candidates.append({
                "ticker": ticker,
                "side": "NO",
                "entry_price": no_ask,
                "fee": fee,
                "edge": edge,
                "model_probability_yes": p_yes,
                "quote_ts": quote["end_period_ts"],
            })

    if not candidates:
        return None

    best = max(candidates, key=lambda item: item["edge"])
    return best if best["edge"] >= min_edge else None


def settle_trade(trade: dict, market: dict, execution_buffer: float) -> dict:
    yes_won = market.get("result") == "yes"
    won = yes_won if trade["side"] == "YES" else not yes_won
    payout = 1.0 if won else 0.0
    cost = trade["entry_price"] + trade["fee"] + execution_buffer
    pnl = payout - cost
    return {
        **trade,
        "won": won,
        "payout": payout,
        "simulated_cost": cost,
        "net_pnl": pnl,
    }


def summarize(records: list[dict], leads: tuple[int, ...]) -> dict:
    result = {}
    for lead in leads:
        rows = [row for row in records if row["lead_bucket"] == lead]
        trades = [row for row in rows if row.get("trade")]
        settled = [row["trade"] for row in trades]
        capital = sum(t["simulated_cost"] for t in settled)
        pnl = sum(t["net_pnl"] for t in settled)
        result[str(lead)] = {
            "evaluated_events": len(rows),
            "quoted_events": sum(1 for row in rows if row["had_quotes"]),
            "trades": len(settled),
            "wins": sum(1 for trade in settled if trade["won"]),
            "net_pnl": round(pnl, 4),
            "capital": round(capital, 4),
            "roi": (pnl / capital) if capital else None,
            "mean_model_edge": (
                mean(t["edge"] for t in settled) if settled else None
            ),
            "mean_training_samples": (
                mean(row["training_samples"] for row in rows) if rows else None
            ),
        }
    return result


def run_backtest(args, session: requests.Session) -> dict:
    if args.end < args.start:
        raise SystemExit("--end must be >= --start")
    if args.stride_days < 1:
        raise SystemExit("--stride-days must be >= 1")

    leads = tuple(
        sorted({int(value.strip()) for value in args.leads.split(",") if value.strip()})
    )
    selected = load_bucketed_rows(
        args.dataset,
        leads,
        args.max_lead_distance,
    )

    rows_by_date = defaultdict(dict)
    rows_by_lead = defaultdict(list)
    for row in selected:
        rows_by_date[row["target_date"]][row["lead_bucket"]] = row
        rows_by_lead[row["lead_bucket"]].append(row)

    markets = fetch_all_settled_markets(session)
    markets_by_event = defaultdict(list)
    for market in markets:
        target = event_date(market.get("event_ticker", ""))
        if target is None or not (args.start <= target <= args.end):
            continue
        if (target - args.start).days % args.stride_days != 0:
            continue
        markets_by_event[market["event_ticker"]].append(market)

    client = CandleClient(session, args.request_sleep)
    records = []
    source_counts = Counter()
    skipped = Counter()

    for event_ticker, event_markets in sorted(
        markets_by_event.items(),
        key=lambda item: event_date(item[0]) or date.min,
    ):
        target = event_date(event_ticker)
        if target is None:
            continue
        partition, reason = event_partition(event_markets)
        if partition is None:
            skipped[reason] += 1
            continue

        forecast_rows = rows_by_date.get(target, {})
        usable_rows = [
            forecast_rows[lead]
            for lead in leads
            if lead in forecast_rows
        ]
        if not usable_rows:
            skipped["missing_forecast_rows"] += 1
            continue

        eval_times = [
            parse_dt(row["runtime_utc"]) + NBM_PUBLICATION_LAG
            for row in usable_rows
        ]
        candles, source = client.event_candles(
            event_ticker,
            event_markets,
            min(eval_times) - timedelta(hours=2),
            max(eval_times),
        )
        source_counts[source] += 1

        normalized = normalize_markets(event_markets)
        market_by_ticker = {market["ticker"]: market for market in event_markets}

        for row, eval_time in zip(usable_rows, eval_times):
            lead = row["lead_bucket"]
            counts = prior_error_counts(rows_by_lead, lead, eval_time)
            record = {
                "date": target.isoformat(),
                "event_ticker": event_ticker,
                "lead_bucket": lead,
                "forecast_runtime_utc": row["runtime_utc"],
                "forecast_available_utc": eval_time.isoformat(),
                "forecast_high_f": row["forecast"],
                "actual_high_f": row["actual"],
                "training_samples": sum(counts.values()),
                "had_quotes": False,
                "trade": None,
            }

            if sum(counts.values()) < args.min_training_samples:
                record["skip_reason"] = "insufficient_training"
                records.append(record)
                continue

            probabilities = probabilities_from_error_counts(
                normalized,
                row["forecast"],
                dict(counts),
                args.empirical_alpha,
            )

            quotes = {}
            for market in event_markets:
                quote = quote_at(
                    candles.get(market["ticker"], []),
                    eval_time,
                    args.max_quote_staleness_hours,
                )
                quotes[market["ticker"]] = quote
            record["had_quotes"] = any(value is not None for value in quotes.values())

            trade = best_trade(
                event_markets,
                probabilities,
                quotes,
                args.min_edge,
                args.execution_buffer,
            )
            if trade:
                record["trade"] = settle_trade(
                    trade,
                    market_by_ticker[trade["ticker"]],
                    args.execution_buffer,
                )
            records.append(record)

    return {
        "dataset": str(args.dataset),
        "period": [args.start.isoformat(), args.end.isoformat()],
        "stride_days": args.stride_days,
        "leads": list(leads),
        "rules": {
            "min_training_samples": args.min_training_samples,
            "min_edge": args.min_edge,
            "execution_buffer": args.execution_buffer,
            "empirical_alpha": args.empirical_alpha,
            "max_quote_staleness_hours": args.max_quote_staleness_hours,
            "contracts_per_event_horizon": 1,
            "selection": "single highest modeled edge per event/horizon",
            "nbm_publication_lag_minutes": int(NBM_PUBLICATION_LAG.total_seconds() / 60),
        },
        "candle_sources": dict(source_counts),
        "skipped_events": dict(skipped),
        "summary_by_lead": summarize(records, leads),
        "records": records,
    }


def print_report(report: dict):
    print("KXHIGHNY WALK-FORWARD PRICE BACKTEST")
    print(f"Period: {report['period'][0]} .. {report['period'][1]}")
    print(f"Stride: every {report['stride_days']} day(s)")
    print(f"Candle sources: {report['candle_sources']}")
    print(f"Skipped events: {report['skipped_events']}")
    print()
    print("lead  eval quoted trades wins  net P&L  ROI      mean edge  train n")
    print("----  ---- ------ ------ ----  -------  -------  ---------  -------")
    for lead in report["leads"]:
        stats = report["summary_by_lead"][str(lead)]
        roi = "-" if stats["roi"] is None else f"{stats['roi']:+.1%}"
        edge = "-" if stats["mean_model_edge"] is None else f"{stats['mean_model_edge']:.1%}"
        train = "-" if stats["mean_training_samples"] is None else f"{stats['mean_training_samples']:.0f}"
        print(
            f"{lead:>4}  {stats['evaluated_events']:>4} "
            f"{stats['quoted_events']:>6} {stats['trades']:>6} "
            f"{stats['wins']:>4}  {stats['net_pnl']:>+7.2f}  "
            f"{roi:>7}  {edge:>9}  {train:>7}"
        )
    print()
    print("Each lead is a separate strategy slice; do not sum rows as an independent portfolio.")


def main():
    args = parse_args()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    report = run_backtest(args, session)
    print_report(report)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"\nWrote {args.output}")


if __name__ == "__main__":
    main()
