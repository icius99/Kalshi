#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from paper.current_signals import build_evaluation
from paper.ledger import connect, has_open_position


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
    result = build_evaluation(args)
    conn = connect(args.ledger)
    inserted = 0

    for signal in result["signals"]:
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
                forecast_source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
