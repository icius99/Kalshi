#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
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


def score_multiclass_probabilities(
    probabilities: dict[str, float],
    winning_market_ticker: str,
) -> tuple[float, float]:
    if winning_market_ticker not in probabilities:
        raise ValueError("winning market is missing from probability vector")

    total = sum(float(value) for value in probabilities.values())
    if total <= 0:
        raise ValueError("probability vector has no positive mass")

    normalized = {
        ticker: float(value) / total
        for ticker, value in probabilities.items()
    }
    brier = sum(
        (probability - (1.0 if ticker == winning_market_ticker else 0.0)) ** 2
        for ticker, probability in normalized.items()
    )
    winner_probability = max(normalized[winning_market_ticker], 1e-12)
    log_loss = -math.log(winner_probability)
    return brier, log_loss


def settled_winner(
    probabilities: dict[str, float],
    market_cache: dict[str, dict],
) -> str | None:
    outcomes = {}
    for ticker in probabilities:
        market = market_cache.get(ticker)
        if market is None:
            response = requests.get(
                f"{BASE}/markets/{ticker}",
                timeout=15,
            )
            response.raise_for_status()
            market = response.json()["market"]
            market_cache[ticker] = market

        outcome = settlement_yes_from_market(market)
        if outcome is None:
            return None
        outcomes[ticker] = outcome

    winners = [ticker for ticker, outcome in outcomes.items() if outcome == 1]
    if len(winners) != 1:
        return None
    return winners[0]


def gross_pnl(side: str, entry_price: float, quantity: float, settlement_yes: int) -> float:
    payout = settlement_yes if side == "YES" else 1 - settlement_yes
    return (float(payout) - entry_price) * quantity


def net_pnl(
    side: str,
    entry_price: float,
    quantity: float,
    settlement_yes: int,
    entry_fee: float,
) -> float:
    return gross_pnl(side, entry_price, quantity, settlement_yes) - entry_fee


def main():
    args = parse_args()
    conn = connect(args.ledger)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM paper_signals WHERE status='OPEN' ORDER BY id"
    ).fetchall()

    market_cache: dict[str, dict] = {}
    settled = 0
    for row in rows:
        market = market_cache.get(row["market_ticker"])
        if market is None:
            response = requests.get(
                f"{BASE}/markets/{row['market_ticker']}",
                timeout=15,
            )
            response.raise_for_status()
            market = response.json()["market"]
            market_cache[row["market_ticker"]] = market
        outcome = settlement_yes_from_market(market)
        if outcome is None:
            continue

        gross = gross_pnl(
            row["side"],
            float(row["entry_price"]),
            float(row["quantity"]),
            outcome,
        )
        net = gross - float(row["entry_fee"] or 0.0)

        conn.execute(
            """
            UPDATE paper_signals
            SET status='SETTLED',
                settlement_yes=?,
                gross_pnl=?,
                net_pnl=?
            WHERE id=?
            """,
            (outcome, gross, net, row["id"]),
        )
        settled += 1
        print(
            f"SETTLED {row['market_ticker']} {row['side']}: "
            f"YES={outcome}, gross={gross:+.2f}, "
            f"fee={float(row['entry_fee'] or 0):.2f}, net={net:+.2f}"
        )

    evaluations = conn.execute(
        "SELECT * FROM paper_evaluations WHERE status='OPEN' ORDER BY id"
    ).fetchall()

    scored = 0
    for row in evaluations:
        probabilities = json.loads(row["probabilities_json"])
        winner = settled_winner(probabilities, market_cache)
        if winner is None:
            continue

        brier, log_loss = score_multiclass_probabilities(
            probabilities,
            winner,
        )
        conn.execute(
            """
            UPDATE paper_evaluations
            SET status='SETTLED',
                winning_market_ticker=?,
                multiclass_brier=?,
                log_loss=?,
                settled_at_utc=datetime('now')
            WHERE id=?
            """,
            (winner, brier, log_loss, row["id"]),
        )
        scored += 1
        print(
            f"SCORED {row['event_ticker']} "
            f"lead={row['model_lead_bucket']}h "
            f"winner={winner} brier={brier:.4f} logloss={log_loss:.4f}"
        )

    conn.commit()
    conn.close()
    print(f"Settled {settled} paper position(s).")
    print(f"Scored {scored} live evaluation state(s).")


if __name__ == "__main__":
    main()
