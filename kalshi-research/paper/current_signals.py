#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from research.error_model import ForecastErrorModel
from research.nbm import FORECAST_DEFINITION, fetch_forecast_asof
from research.observations import (
    conservative_minimum_settlement_high,
    fetch_observed_high_asof,
)
from research.signals import evaluate_probabilities
from research.temperature import bucket_from_market

NY = ZoneInfo("America/New_York")
INTRADAY_CONDITIONING = "nws_observed_high_floor_v1"
ENTRY_POLICY = "pre_anchor_3h_live_revalidation_v1"


class PaperEvaluationSkip(RuntimeError):
    """Paper evaluation should skip normally rather than fail."""


EVENT_DATE_RE = re.compile(r"KXHIGHNY-(\d{2})([A-Z]{3})(\d{2})")
MONTHS = {
    m: i
    for i, m in enumerate(
        ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"),
        1,
    )
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare a contemporaneous NBM forecast to executable Kalshi prices."
    )
    parser.add_argument("--db", type=Path, default=Path("kalshi.db"))
    parser.add_argument(
        "--model", type=Path, default=Path("data/models/nbm_error_model.json")
    )
    parser.add_argument(
        "--event",
        help="Event ticker; defaults to the nearest current/future KXHIGHNY event.",
    )
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument(
        "--execution-buffer",
        type=float,
        default=0.005,
        help="Per-contract slippage/uncertainty reserve, separate from modeled taker fees.",
    )
    parser.add_argument("--min-qty", type=float, default=10.0)
    parser.add_argument("--max-contracts", type=int, default=25)
    parser.add_argument("--max-model-distance", type=float, default=6.0)
    parser.add_argument("--anchor-hour", type=int, default=15)
    parser.add_argument(
        "--observation-buffer-f",
        type=float,
        default=1.0,
        help="Conservative NWS-to-settlement source/rounding buffer.",
    )
    parser.add_argument(
        "--max-snapshot-age-minutes",
        type=float,
        default=20.0,
        help="Reject stale collector snapshots; <=0 disables this guard.",
    )
    parser.add_argument(
        "--min-market-lead-hours",
        type=float,
        default=3.0,
        help=(
            "Do not open new paper positions inside this many hours of the "
            "3 PM anchor; late-day forecasts are outside the calibrated entry regime."
        ),
    )
    return parser.parse_args()


def event_date(ticker: str) -> date:
    match = EVENT_DATE_RE.fullmatch(ticker)
    if not match:
        raise ValueError(f"unsupported event ticker {ticker}")
    year, month, day = match.groups()
    return date(2000 + int(year), MONTHS[month], int(day))


def latest_event(conn: sqlite3.Connection, explicit: str | None) -> tuple[str, str]:
    if explicit:
        timestamp = conn.execute(
            "SELECT MAX(timestamp_utc) FROM market_snapshots WHERE event_ticker=?",
            (explicit,),
        ).fetchone()[0]
        if timestamp is None:
            raise SystemExit(f"No snapshots found for {explicit}")
        return explicit, timestamp

    rows = conn.execute(
        "SELECT event_ticker,MAX(timestamp_utc) FROM market_snapshots "
        "WHERE series_ticker='KXHIGHNY' GROUP BY event_ticker"
    ).fetchall()

    today = datetime.now(timezone.utc).astimezone(NY).date()
    candidates = [
        (event_date(row[0]), row[0], row[1])
        for row in rows
        if event_date(row[0]) >= today
    ]
    if not candidates:
        raise SystemExit("No current/future KXHIGHNY event found")

    _, ticker, timestamp = min(candidates)
    return ticker, timestamp


def load_markets(
    conn: sqlite3.Connection, event: str, timestamp: str
) -> list[dict]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT market_ticker,title,floor_strike,cap_strike,"
        "yes_bid,yes_bid_qty,yes_ask,yes_ask_qty "
        "FROM market_snapshots WHERE event_ticker=? AND timestamp_utc=? "
        "ORDER BY market_ticker",
        (event, timestamp),
    ).fetchall()
    return [dict(row) for row in rows]



def lead_hours_to_anchor(
    anchor: datetime,
    reference_utc: datetime,
) -> float:
    return (
        anchor.astimezone(timezone.utc) - reference_utc.astimezone(timezone.utc)
    ).total_seconds() / 3600.0


def snapshot_age_minutes(
    snapshot_utc: datetime,
    now_utc: datetime | None = None,
) -> float:
    now = now_utc or datetime.now(timezone.utc)
    return (
        now.astimezone(timezone.utc) - snapshot_utc.astimezone(timezone.utc)
    ).total_seconds() / 60.0


def build_evaluation(args):
    conn = sqlite3.connect(args.db)
    event, market_timestamp = latest_event(conn, args.event)
    markets = load_markets(conn, event, market_timestamp)
    conn.close()

    target = event_date(event)
    snapshot_dt = datetime.fromisoformat(market_timestamp).astimezone(timezone.utc)
    age_minutes = snapshot_age_minutes(snapshot_dt)
    if args.max_snapshot_age_minutes > 0 and age_minutes > args.max_snapshot_age_minutes:
        raise PaperEvaluationSkip(
            f"latest market snapshot is {age_minutes:.1f} minutes old "
            f"(limit {args.max_snapshot_age_minutes:.1f})"
        )

    anchor = datetime.combine(target, time(args.anchor_hour), tzinfo=NY)
    market_lead_hours = lead_hours_to_anchor(anchor, snapshot_dt)
    if market_lead_hours < args.min_market_lead_hours:
        raise PaperEvaluationSkip(
            f"market is only {market_lead_hours:.1f}h from the "
            f"{args.anchor_hour}:00 ET anchor; entry policy requires at least "
            f"{args.min_market_lead_hours:.1f}h"
        )

    observed = None
    minimum_actual_f = None
    if target == snapshot_dt.astimezone(NY).date():
        observed = fetch_observed_high_asof(target, snapshot_dt)
        if observed is None:
            raise PaperEvaluationSkip(
                "no Central Park observation was available as of the market snapshot"
            )
        minimum_actual_f = conservative_minimum_settlement_high(
            observed["observed_high_f"],
            args.observation_buffer_f,
        )

    nbm = fetch_forecast_asof(target, snapshot_dt, anchor_hour=args.anchor_hour)
    forecast_high = float(nbm["forecast_high_f"])
    model_lead_hours = lead_hours_to_anchor(anchor, nbm["runtime_utc"])

    model = ForecastErrorModel.load(args.model)
    model.require_forecast_definition(FORECAST_DEFINITION)
    fit, probabilities = model.probabilities_for_markets(
        markets,
        forecast_high,
        model_lead_hours,
        args.max_model_distance,
        minimum_actual_f=minimum_actual_f,
    )
    signals = evaluate_probabilities(
        markets,
        probabilities,
        args.min_edge,
        args.execution_buffer,
        args.min_qty,
        args.max_contracts,
    )

    return {
        "event": event,
        "model_version": model.model_version,
        "forecast_definition": model.forecast_definition,
        "probability_method": model.payload.get(
            "default_probability_method", "empirical_integer_errors"
        ),
        "target": target,
        "market_ts": market_timestamp,
        "markets": markets,
        "nbm": nbm,
        "forecast_high": forecast_high,
        "forecast_sigma": nbm.get("forecast_sigma_f"),
        "forecast_source": nbm.get("forecast_source"),
        "lead_hours": model_lead_hours,
        "model_lead_hours": model_lead_hours,
        "market_lead_hours": market_lead_hours,
        "snapshot_age_minutes": age_minutes,
        "observed": observed,
        "observed_high_f": (
            None if observed is None else observed["observed_high_f"]
        ),
        "minimum_actual_f": minimum_actual_f,
        "intraday_conditioning": (
            INTRADAY_CONDITIONING if observed is not None else "not_applicable_future"
        ),
        "observation_buffer_f": args.observation_buffer_f,
        "entry_policy": ENTRY_POLICY,
        "min_market_lead_hours": args.min_market_lead_hours,
        "fit": fit,
        "probs": probabilities,
        "signals": signals,
    }


def main():
    args = parse_args()
    result = build_evaluation(args)
    fit = result["fit"]
    nbm = result["nbm"]

    print(f"Event:           {result['event']} ({result['target']})")
    print(f"Market snapshot: {result['market_ts']}")
    print(f"NBM runtime:     {nbm['runtime_utc'].isoformat()}")
    print(f"NBM high:        {result['forecast_high']:.1f} F")
    print(
        f"Forecast lead:   {result['model_lead_hours']:.1f} h -> "
        f"{fit.lead_hours} h error bucket (n={fit.n})"
    )
    print(
        f"Market lead:     {result['market_lead_hours']:.1f} h "
        "(snapshot to 3 PM anchor; not used for calibration)"
    )
    print(f"Snapshot age:    {result['snapshot_age_minutes']:.1f} min")
    if result["observed"] is not None:
        print(
            f"Observed high:   {result['observed_high_f']:.1f} F "
            f"through {result['observed']['high_observation_utc'].isoformat()}"
        )
        print(
            f"Condition floor: {result['minimum_actual_f']} F "
            f"(NWS proxy minus {result['observation_buffer_f']:.1f} F buffer)"
        )
    print(f"Predictor:       {FORECAST_DEFINITION}")
    print(
        f"Probability:     {result['probability_method']} "
        f"(schema v{result['model_version']})"
    )
    print(
        f"Model:           empirical integer-error distribution; "
        f"RMSE={fit.rmse_f:.2f} F, historical bias={fit.bias_f:+.2f} F "
        f"(bias not applied)"
    )
    print()
    print("bucket    model    bid/ask   ask qty   best signal")
    print("--------  -------  --------  --------  ------------------------------")

    signals_by_market = {}
    for signal in result["signals"]:
        signals_by_market.setdefault(signal.market_ticker, signal)

    def market_sort_key(market):
        bucket = bucket_from_market(
            market["market_ticker"],
            market.get("floor_strike"),
            market.get("cap_strike"),
        )
        return bucket.lower

    for market in sorted(result["markets"], key=market_sort_key):
        bucket = bucket_from_market(
            market["market_ticker"],
            market.get("floor_strike"),
            market.get("cap_strike"),
        )
        probability = result["probs"][market["market_ticker"]]
        bid = market.get("yes_bid")
        ask = market.get("yes_ask")
        if bid is not None and ask is not None:
            spread = f"{float(bid):.2f}/{float(ask):.2f}"
        else:
            spread = f"{bid}/{ask}"

        signal = signals_by_market.get(market["market_ticker"])
        signal_text = (
            ""
            if signal is None
            else (
                f"BUY {signal.side} x{signal.quantity} "
                f"fee={signal.fee_total:.2f} net-edge={signal.estimated_edge:.1%}"
            )
        )
        print(
            f"{bucket.label:<8}  {probability:7.1%}  {spread:<8}  "
            f"{float(market.get('yes_ask_qty') or 0):8.1f}  {signal_text}"
        )

    print()
    print(
        "Signal edge is net of the standard KXHIGHNY taker fee and the "
        "configured execution/slippage buffer."
    )


if __name__ == "__main__":
    main()
