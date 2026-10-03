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
               estimated_edge,lead_hours,status,gross_pnl
        FROM paper_signals ORDER BY id
        """
    ).fetchall()

    if not rows:
        print("No paper positions recorded.")
        conn.close()
        return

    print("id  side  price  qty    edge    lead   status    pnl     market")
    print("--  ----  -----  -----  ------  ------  --------  ------  --------------------------")
    for row in rows:
        pnl = "-" if row["gross_pnl"] is None else f"{row['gross_pnl']:+.2f}"
        print(
            f"{row['id']:>2}  {row['side']:<4}  {row['entry_price']:.2f}   "
            f"{row['quantity']:>5.1f}  {row['estimated_edge']:>6.1%}  "
            f"{row['lead_hours']:>6.1f}  {row['status']:<8}  {pnl:>6}  "
            f"{row['market_ticker']}"
        )

    closed = [row for row in rows if row["gross_pnl"] is not None]
    if closed:
        total_pnl = sum(row["gross_pnl"] for row in closed)
        total_cost = sum(row["entry_price"] * row["quantity"] for row in closed)
        roi = total_pnl / total_cost if total_cost else 0.0
        print()
        print(f"Closed positions: {len(closed)}")
        print("Gross P&L:        " + f"{total_pnl:+.2f}")
        print(f"Gross ROI:        {roi:+.1%}")
        print("Gross means before exact Kalshi fees.")

    conn.close()


if __name__ == "__main__":
    main()
