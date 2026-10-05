#!/usr/bin/env python3
"""One-command health check for the unattended NYC paper research loop."""

from __future__ import annotations

import argparse
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from historical.build_nbm_history import FORECAST_DEFINITION
from paper.ledger import connect
from research.error_model import ForecastErrorModel


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("kalshi.db"))
    parser.add_argument("--ledger", type=Path, default=Path("paper.db"))
    parser.add_argument(
        "--model",
        type=Path,
        default=Path("data/models/nbm_error_model.json"),
    )
    parser.add_argument("--max-collector-age-minutes", type=float, default=20.0)
    parser.add_argument("--skip-systemd", action="store_true")
    return parser.parse_args()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def age_minutes(value: str, now_utc: datetime | None = None) -> float:
    now = now_utc or datetime.now(timezone.utc)
    return (
        now.astimezone(timezone.utc) - parse_timestamp(value)
    ).total_seconds() / 60.0


def count_statuses(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    return {
        str(status): int(count)
        for status, count in conn.execute(
            f"SELECT status,COUNT(*) FROM {table} GROUP BY status"
        ).fetchall()
    }


def paper_timer_active() -> bool:
    completed = subprocess.run(
        ["systemctl", "--user", "is-active", "--quiet", "kalshi-paper-cycle.timer"],
        check=False,
    )
    return completed.returncode == 0


def main():
    args = parse_args()
    failures = []
    warnings = []

    print("Kalshi NYC paper-loop health")
    print("----------------------------")

    if not args.db.exists():
        failures.append(f"collector DB missing: {args.db}")
    else:
        conn = sqlite3.connect(args.db)
        latest_market = conn.execute(
            "SELECT MAX(timestamp_utc) FROM market_snapshots"
        ).fetchone()[0]
        latest_weather = conn.execute(
            "SELECT MAX(collected_at_utc) FROM weather_forecasts"
        ).fetchone()[0]
        market_rows = conn.execute(
            "SELECT COUNT(*) FROM market_snapshots"
        ).fetchone()[0]
        conn.close()

        if latest_market is None:
            failures.append("collector DB has no market snapshots")
        else:
            market_age = age_minutes(latest_market)
            print(
                f"Collector market snapshot: {latest_market} "
                f"({market_age:.1f} min old; rows={market_rows:,})"
            )
            if market_age > args.max_collector_age_minutes:
                failures.append(
                    f"market snapshot is {market_age:.1f} minutes old "
                    f"(limit {args.max_collector_age_minutes:.1f})"
                )

        if latest_weather is None:
            warnings.append("collector DB has no weather forecast rows")
        else:
            weather_age = age_minutes(latest_weather)
            print(
                f"Collector weather update:  {latest_weather} "
                f"({weather_age:.1f} min old)"
            )

    if not args.model.exists():
        failures.append(f"promoted model missing: {args.model}")
    else:
        try:
            model = ForecastErrorModel.load(args.model)
            model.require_forecast_definition(FORECAST_DEFINITION)
            print(
                f"Promoted model: schema=v{model.model_version} "
                f"predictor={model.forecast_definition} "
                f"method={model.payload.get('default_probability_method')}"
            )
            if int(model.model_version or 0) < 4:
                failures.append("promoted model schema is older than v4")
        except Exception as exc:
            failures.append(f"promoted model invalid: {exc}")

    ledger = connect(args.ledger)
    position_counts = count_statuses(ledger, "paper_signals")
    evaluation_counts = count_statuses(ledger, "paper_evaluations")
    latest_evaluation = ledger.execute(
        "SELECT event_ticker,created_at_utc,model_lead_bucket,status "
        "FROM paper_evaluations ORDER BY id DESC LIMIT 1"
    ).fetchone()
    ledger.close()

    print(f"Paper positions:   {position_counts or {}}")
    print(f"Forecast states:   {evaluation_counts or {}}")
    if latest_evaluation is None:
        warnings.append("no live forecast evaluation states recorded yet")
    else:
        event, created, lead_bucket, status = latest_evaluation
        print(
            f"Latest evaluation: {event} {lead_bucket}h "
            f"status={status} recorded={created}"
        )

    if not args.skip_systemd:
        active = paper_timer_active()
        print(f"Paper timer:       {'active' if active else 'inactive'}")
        if not active:
            failures.append("kalshi-paper-cycle.timer is not active")

    if warnings:
        print()
        print("Warnings")
        for warning in warnings:
            print(f"  - {warning}")

    print()
    if failures:
        print("HEALTH FAILED")
        for failure in failures:
            print(f"  - {failure}")
        raise SystemExit(1)

    print("HEALTH PASSED")


if __name__ == "__main__":
    main()
