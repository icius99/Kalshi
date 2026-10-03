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
               entry_fee,estimated_edge,lead_hours,status,gross_pnl,net_pnl
        FROM paper_signals ORDER BY id
        """
    ).fetchall()

    if not rows:
        print("No paper positions recorded.")
        conn.close()
        return

    print("id  side  price  qty    fee   edge    lead   status    net pnl  market")
    print("--  ----  -----  -----  ----  ------  ------  --------  -------  --------------------------")
    for row in rows:
        pnl = "-" if row["net_pnl"] is None else f"{row['net_pnl']:+.2f}"
        print(
            f"{row['id']:>2}  {row['side']:<4}  {row['entry_price']:.2f}   "
            f"{row['quantity']:>5.1f}  {row['entry_fee']:>4.2f}  "
            f"{row['estimated_edge']:>6.1%}  {row['lead_hours']:>6.1f}  "
            f"{row['status']:<8}  {pnl:>7}  {row['market_ticker']}"
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

    conn.close()


if __name__ == "__main__":
    main()
