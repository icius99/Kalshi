#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from paper.ledger import connect


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    return parser.parse_args()


def primary_evaluations(rows):
    """One settled state per event/lead bucket, closest to nominal horizon."""
    primary = {}
    for row in rows:
        if row["status"] != "SETTLED":
            continue
        key = (row["event_ticker"], row["model_lead_bucket"])
        distance = abs(row["model_lead_hours"] - row["model_lead_bucket"])
        candidate = (distance, row["id"], row)
        current = primary.get(key)
        if current is None or candidate[:2] < current[:2]:
            primary[key] = candidate
    return [item[2] for item in primary.values()]


def mean_or_none(values):
    return sum(values) / len(values) if values else None


def main():
    args = parse_args()
    conn = connect(args.ledger)
    conn.row_factory = sqlite3.Row

    positions = conn.execute(
        """
        SELECT id,event_ticker,market_ticker,side,entry_price,quantity,
               entry_fee,estimated_edge,lead_hours,status,gross_pnl,net_pnl,
               model_version,forecast_definition,probability_method,
               forecast_high_f,forecast_sigma_f,forecast_source
        FROM paper_signals ORDER BY id
        """
    ).fetchall()
    evaluations = conn.execute(
        """
        SELECT id,event_ticker,forecast_runtime_utc,model_lead_hours,
               model_lead_bucket,probability_method,signal_count,status,
               winning_market_ticker,multiclass_brier,log_loss
        FROM paper_evaluations ORDER BY id
        """
    ).fetchall()

    if not positions and not evaluations:
        print("No paper positions or live forecast evaluations recorded.")
        conn.close()
        return

    if positions:
        print("id  side  price  qty    fee   edge    lead   status    net pnl  model  market")
        print("--  ----  -----  -----  ----  ------  ------  --------  -------  -----  --------------------------")
        for row in positions:
            pnl = "-" if row["net_pnl"] is None else f"{row['net_pnl']:+.2f}"
            method = (row["probability_method"] or "-").replace("_integer_errors", "")
            print(
                f"{row['id']:>2}  {row['side']:<4}  {row['entry_price']:.2f}   "
                f"{row['quantity']:>5.1f}  {row['entry_fee']:>4.2f}  "
                f"{row['estimated_edge']:>6.1%}  {row['lead_hours']:>6.1f}  "
                f"{row['status']:<8}  {pnl:>7}  "
                f"v{row['model_version'] or '-'} {method:<10} "
                f"{row['market_ticker']}"
            )

        closed = [row for row in positions if row["net_pnl"] is not None]
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
    print("Live forecast calibration")
    open_evals = [row for row in evaluations if row["status"] == "OPEN"]
    settled_evals = [row for row in evaluations if row["status"] == "SETTLED"]
    signal_states = sum(1 for row in evaluations if row["signal_count"] > 0)
    print(
        f"Stored states: {len(evaluations)} "
        f"(open={len(open_evals)}, settled={len(settled_evals)}, "
        f"states with signals={signal_states})"
    )

    primary = primary_evaluations(evaluations)
    if primary:
        brier = mean_or_none([row["multiclass_brier"] for row in primary])
        log_loss = mean_or_none([row["log_loss"] for row in primary])
        events = len({row["event_ticker"] for row in primary})
        print(
            f"Primary OOS sample: {len(primary)} event/lead states "
            f"across {events} event(s)"
        )
        print(f"Mean multiclass Brier: {brier:.4f}")
        print(f"Mean log loss:         {log_loss:.4f}")

        by_lead = {}
        for row in primary:
            by_lead.setdefault(row["model_lead_bucket"], []).append(row)

        print()
        print("lead    n   events   Brier  log loss")
        print("----  ---  -------  ------  --------")
        for lead, lead_rows in sorted(by_lead.items()):
            lead_brier = mean_or_none(
                [row["multiclass_brier"] for row in lead_rows]
            )
            lead_log = mean_or_none([row["log_loss"] for row in lead_rows])
            lead_events = len({row["event_ticker"] for row in lead_rows})
            print(
                f"{lead:>4}  {len(lead_rows):>3}  {lead_events:>7}  "
                f"{lead_brier:>6.4f}  {lead_log:>8.4f}"
            )
    else:
        print("No settled primary forecast states yet.")

    conn.close()


if __name__ == "__main__":
    main()
