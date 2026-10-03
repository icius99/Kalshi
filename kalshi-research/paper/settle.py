#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import requests

from paper.ledger import connect

BASE = "https://external-api.kalshi.com/trade-api/v2"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Resolve open paper positions using public Kalshi settlement fields."
    )
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    return parser.parse_args()


def settlement_yes_from_market(market: dict) -> int | None:
    value = market.get("settlement_value_dollars")
    if value in (None, ""):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if abs(numeric - 1.0) < 1e-9:
        return 1
    if abs(numeric) < 1e-9:
        return 0
    return None


def gross_pnl(side: str, entry_price: float, quantity: float, settlement_yes: int) -> float:
    payout = settlement_yes if side == "YES" else 1 - settlement_yes
    return (float(payout) - entry_price) * quantity


def main():
    args = parse_args()
    conn = connect(args.ledger)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM paper_signals WHERE status='OPEN' ORDER BY id"
    ).fetchall()

    settled = 0
    for row in rows:
        response = requests.get(
            f"{BASE}/markets/{row['market_ticker']}",
            timeout=15,
        )
        response.raise_for_status()
        market = response.json()["market"]
        outcome = settlement_yes_from_market(market)
        if outcome is None:
            continue

        pnl = gross_pnl(
            row["side"],
            float(row["entry_price"]),
            float(row["quantity"]),
            outcome,
        )
        conn.execute(
            """
            UPDATE paper_signals
            SET status='SETTLED', settlement_yes=?, gross_pnl=?
            WHERE id=?
            """,
            (outcome, pnl, row["id"]),
        )
        settled += 1
        print(
            f"SETTLED {row['market_ticker']} {row['side']}: "
            f"YES={outcome}, gross P&L {pnl:+.2f}"
        )

    conn.commit()
    conn.close()
    print(f"Settled {settled} paper position(s).")


if __name__ == "__main__":
    main()
