#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from paper.current_signals import PaperEvaluationSkip, build_evaluation
from paper.execution import revalidate_signals
from paper.ledger import connect, evaluation_key, has_open_position
from research.error_model import ModelHorizonUnavailable


def parse_args():
    parser = argparse.ArgumentParser(
        description="Record qualifying model signals in a separate paper-trading ledger."
    )
    parser.add_argument("--db", type=Path, default=Path("kalshi.db"))
    parser.add_argument(
        "--model", type=Path, default=Path("data/models/nbm_error_model.json")
    )
    parser.add_argument("--event")
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument("--execution-buffer", type=float, default=0.005)
    parser.add_argument("--min-qty", type=float, default=10.0)
    parser.add_argument("--max-model-distance", type=float, default=6.0)
    parser.add_argument("--anchor-hour", type=int, default=15)
    parser.add_argument("--observation-buffer-f", type=float, default=1.0)
    parser.add_argument("--max-snapshot-age-minutes", type=float, default=20.0)
    parser.add_argument("--min-market-lead-hours", type=float, default=3.0)
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    parser.add_argument(
        "--max-contracts",
        type=int,
        default=25,
        help="Cap paper position size even when more top-of-book liquidity is displayed.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        result = build_evaluation(args)
    except (ModelHorizonUnavailable, PaperEvaluationSkip) as exc:
        print(f"SKIP paper evaluation: {exc}")
        return

    observed_text = (
        "none"
        if result["observed_high_f"] is None
        else (
            f"{result['observed_high_f']:.1f}F "
            f"(floor {result['minimum_actual_f']}F)"
        )
    )
    print(
        f"Paper evaluation {result['event']}: "
        f"snapshot={result['market_ts']} "
        f"forecast={result['forecast_high']:.1f}F "
        f"observed={observed_text} "
        f"model-lead={result['model_lead_hours']:.1f}h "
        f"bucket={result['fit'].lead_hours}h"
    )

    execution_quote_utc, live_markets, live_signals = revalidate_signals(
        result["markets"],
        result["probs"],
        args.min_edge,
        args.execution_buffer,
        args.min_qty,
        args.max_contracts,
    )
    if len(live_signals) != len(result["signals"]):
        print(
            f"Live quote revalidation changed qualifying signals: "
            f"{len(result['signals'])} -> {len(live_signals)}"
        )

    conn = connect(args.ledger)

    runtime_text = result["nbm"]["runtime_utc"].isoformat()
    eval_key = evaluation_key(
        result["event"],
        runtime_text,
        result["minimum_actual_f"],
        int(result["model_version"]),
        result["probability_method"],
        result["entry_policy"],
    )
    before_changes = conn.total_changes
    conn.execute(
        """
        INSERT OR IGNORE INTO paper_evaluations (
            evaluation_key,
            created_at_utc,
            event_ticker,
            market_snapshot_utc,
            execution_quote_utc,
            forecast_runtime_utc,
            model_version,
            forecast_definition,
            probability_method,
            forecast_high_f,
            forecast_sigma_f,
            forecast_source,
            model_lead_hours,
            model_lead_bucket,
            model_sample_n,
            market_lead_hours,
            intraday_conditioning,
            observed_high_f,
            minimum_actual_f,
            observation_buffer_f,
            entry_policy,
            probabilities_json,
            signal_count
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            eval_key,
            datetime.now(timezone.utc).isoformat(),
            result["event"],
            result["market_ts"],
            execution_quote_utc,
            runtime_text,
            result["model_version"],
            result["forecast_definition"],
            result["probability_method"],
            result["forecast_high"],
            result["forecast_sigma"],
            result["forecast_source"],
            result["model_lead_hours"],
            result["fit"].lead_hours,
            result["fit"].n,
            result["market_lead_hours"],
            result["intraday_conditioning"],
            result["observed_high_f"],
            result["minimum_actual_f"],
            result["observation_buffer_f"],
            result["entry_policy"],
            json.dumps(result["probs"], sort_keys=True),
            len(live_signals),
        ),
    )
    if conn.total_changes > before_changes:
        print(
            f"Recorded live evaluation state for {result['event']} "
            f"at {result['fit'].lead_hours}h bucket."
        )

    inserted = 0

    for signal in live_signals:
        if has_open_position(conn, signal.market_ticker):
            continue

        quantity = signal.quantity
        if quantity <= 0:
            continue

        conn.execute(
            """
            INSERT INTO paper_signals (
                created_at_utc,
                market_snapshot_utc,
                forecast_runtime_utc,
                event_ticker,
                market_ticker,
                side,
                entry_price,
                quantity,
                entry_fee,
                model_probability_yes,
                estimated_edge,
                lead_hours,
                model_lead_bucket,
                model_sample_n,
                model_version,
                forecast_definition,
                probability_method,
                forecast_high_f,
                forecast_sigma_f,
                forecast_source,
                intraday_conditioning,
                observed_high_f,
                minimum_actual_f,
                observation_buffer_f,
                entry_policy,
                execution_quote_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now(timezone.utc).isoformat(),
                result["market_ts"],
                result["nbm"]["runtime_utc"].isoformat(),
                result["event"],
                signal.market_ticker,
                signal.side,
                signal.entry_price,
                quantity,
                signal.fee_total,
                signal.model_probability_yes,
                signal.estimated_edge,
                result["lead_hours"],
                result["fit"].lead_hours,
                result["fit"].n,
                result["model_version"],
                result["forecast_definition"],
                result["probability_method"],
                result["forecast_high"],
                result["forecast_sigma"],
                result["forecast_source"],
                result["intraday_conditioning"],
                result["observed_high_f"],
                result["minimum_actual_f"],
                result["observation_buffer_f"],
                result["entry_policy"],
                execution_quote_utc,
            ),
        )
        inserted += 1
        print(
            f"PAPER BUY {signal.side} {signal.market_ticker}: "
            f"{quantity:g} @ {signal.entry_price:.2f}, "
            f"fee={signal.fee_total:.2f}, net estimated edge {signal.estimated_edge:.1%}"
        )

    conn.commit()
    conn.close()
    print(f"Recorded {inserted} new paper position(s) in {args.ledger}")


if __name__ == "__main__":
    main()
