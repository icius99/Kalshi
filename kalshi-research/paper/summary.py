#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    return parser.parse_args()


def main():
    args = parse_args()
    conn = sqlite3.connect(args.ledger)
    conn.row_factory = sqlite3.Row

    rows = conn.execute(
        """
        SELECT id,event_ticker,market_ticker,side,entry_price,quantity,
               entry_fee,estimated_edge,lead_hours,status,gross_pnl,net_pnl,
               model_version,forecast_definition,probability_method,
               forecast_high_f,forecast_sigma_f,forecast_source
        FROM paper_signals ORDER BY id
        """
    ).fetchall()

    if not rows:
        print("No paper positions recorded.")
        conn.close()
        return

    print("id  side  price  qty    fee   edge    lead   status    net pnl  model  market")
    print("--  ----  -----  -----  ----  ------  ------  --------  -------  -----  --------------------------")
    for row in rows:
        pnl = "-" if row["net_pnl"] is None else f"{row['net_pnl']:+.2f}"
        print(
            f"{row['id']:>2}  {row['side']:<4}  {row['entry_price']:.2f}   "
            f"{row['quantity']:>5.1f}  {row['entry_fee']:>4.2f}  "
            f"{row['estimated_edge']:>6.1%}  {row['lead_hours']:>6.1f}  "
            f"{row['status']:<8}  {pnl:>7}  "
            f"v{row['model_version'] or '-'} "
            f"{(row['probability_method'] or '-').replace('_integer_errors', ''):<10} "
            f"{row['market_ticker']}"
        )

    closed = [row for row in rows if row["net_pnl"] is not None]
    if closed:
        gross_total = sum(row["gross_pnl"] for row in closed)
        fee_total = sum(row["entry_fee"] for row in closed)
        net_total = sum(row["net_pnl"] for row in closed)
        capital = sum(
            row["entry_price"] * row["quantity"] + row["entry_fee"]
            for row in closed
        )
        roi = net_total / capital if capital else 0.0
        print()
        print(f"Closed positions: {len(closed)}")
        print(f"Gross P&L:        {gross_total:+.2f}")
        print(f"Entry fees:       {fee_total:.2f}")
        print(f"Net P&L:          {net_total:+.2f}")
        print(f"Net ROI:          {roi:+.1%}")

        by_model = {}
        for row in closed:
            key = (
                row["model_version"],
                row["forecast_definition"],
                row["probability_method"],
            )
            by_model.setdefault(key, []).append(row)

        by_event = {}
        for row in closed:
            by_event.setdefault(row["event_ticker"], []).append(row)

        print()
        print("Closed P&L by event")
        for event, event_rows in sorted(by_event.items()):
            event_net = sum(row["net_pnl"] for row in event_rows)
            event_capital = sum(
                row["entry_price"] * row["quantity"] + row["entry_fee"]
                for row in event_rows
            )
            event_roi = event_net / event_capital if event_capital else 0.0
            print(
                f"  {event}: positions={len(event_rows)} "
                f"capital={event_capital:.2f} net={event_net:+.2f} "
                f"roi={event_roi:+.1%}"
            )

        print()
        print("Closed P&L by model generation")
        for key, model_rows in sorted(
            by_model.items(), key=lambda item: str(item[0])
        ):
            version, definition, method = key
            model_net = sum(row["net_pnl"] for row in model_rows)
            print(
                f"  v{version or '-'} {method or '-'}: "
                f"n={len(model_rows)} net={model_net:+.2f} "
                f"predictor={definition or '-'}"
            )

    conn.close()


if __name__ == "__main__":
    main()
