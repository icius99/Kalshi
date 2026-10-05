from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at_utc TEXT NOT NULL,
    market_snapshot_utc TEXT NOT NULL,
    forecast_runtime_utc TEXT NOT NULL,
    event_ticker TEXT NOT NULL,
    market_ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('YES','NO')),
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    entry_fee REAL NOT NULL DEFAULT 0,
    model_probability_yes REAL NOT NULL,
    estimated_edge REAL NOT NULL,
    lead_hours REAL NOT NULL,
    model_lead_bucket INTEGER NOT NULL,
    model_sample_n INTEGER NOT NULL,
    model_version INTEGER,
    forecast_definition TEXT,
    probability_method TEXT,
    forecast_high_f REAL,
    forecast_sigma_f REAL,
    forecast_source TEXT,
    intraday_conditioning TEXT,
    observed_high_f REAL,
    minimum_actual_f REAL,
    observation_buffer_f REAL,
    entry_policy TEXT,
    execution_quote_utc TEXT,
    invalidation_reason TEXT,
    status TEXT NOT NULL DEFAULT 'OPEN',
    settlement_yes INTEGER,
    gross_pnl REAL,
    net_pnl REAL
);
CREATE INDEX IF NOT EXISTS idx_paper_open
ON paper_signals(status, market_ticker);

CREATE TABLE IF NOT EXISTS paper_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    evaluation_key TEXT NOT NULL UNIQUE,
    created_at_utc TEXT NOT NULL,
    event_ticker TEXT NOT NULL,
    market_snapshot_utc TEXT NOT NULL,
    execution_quote_utc TEXT NOT NULL,
    forecast_runtime_utc TEXT NOT NULL,
    model_version INTEGER NOT NULL,
    forecast_definition TEXT NOT NULL,
    probability_method TEXT NOT NULL,
    forecast_high_f REAL NOT NULL,
    forecast_sigma_f REAL,
    forecast_source TEXT,
    model_lead_hours REAL NOT NULL,
    model_lead_bucket INTEGER NOT NULL,
    model_sample_n INTEGER NOT NULL,
    market_lead_hours REAL NOT NULL,
    intraday_conditioning TEXT,
    observed_high_f REAL,
    minimum_actual_f REAL,
    observation_buffer_f REAL,
    entry_policy TEXT NOT NULL,
    probabilities_json TEXT NOT NULL,
    signal_count INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    winning_market_ticker TEXT,
    multiclass_brier REAL,
    log_loss REAL,
    settled_at_utc TEXT
);
CREATE INDEX IF NOT EXISTS idx_paper_eval_status
ON paper_evaluations(status, event_ticker);
"""


def _ensure_columns(conn: sqlite3.Connection) -> None:
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(paper_signals)").fetchall()
    }
    if "entry_fee" not in columns:
        conn.execute(
            "ALTER TABLE paper_signals ADD COLUMN entry_fee REAL NOT NULL DEFAULT 0"
        )
    if "net_pnl" not in columns:
        conn.execute(
            "ALTER TABLE paper_signals ADD COLUMN net_pnl REAL"
        )

    additions = {
        "model_version": "INTEGER",
        "forecast_definition": "TEXT",
        "probability_method": "TEXT",
        "forecast_high_f": "REAL",
        "forecast_sigma_f": "REAL",
        "forecast_source": "TEXT",
        "intraday_conditioning": "TEXT",
        "observed_high_f": "REAL",
        "minimum_actual_f": "REAL",
        "observation_buffer_f": "REAL",
        "entry_policy": "TEXT",
        "execution_quote_utc": "TEXT",
        "invalidation_reason": "TEXT",
    }
    added_conditioning_column = "intraday_conditioning" not in columns
    for name, sql_type in additions.items():
        if name not in columns:
            conn.execute(
                f"ALTER TABLE paper_signals ADD COLUMN {name} {sql_type}"
            )

    if added_conditioning_column:
        conn.execute(
            """
            UPDATE paper_signals
            SET status='INVALIDATED',
                invalidation_reason='pre_intraday_conditioning_v1'
            WHERE status='OPEN'
            """
        )

    if "entry_policy" not in columns:
        conn.execute(
            """
            UPDATE paper_signals
            SET status='INVALIDATED',
                invalidation_reason='pre_entry_policy_v1'
            WHERE status='OPEN'
            """
        )


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    _ensure_columns(conn)
    return conn


def has_open_position(conn: sqlite3.Connection, market_ticker: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM paper_signals WHERE status='OPEN' AND market_ticker=? LIMIT 1",
        (market_ticker,),
    ).fetchone()
    return row is not None


def evaluation_key(
    event_ticker: str,
    forecast_runtime_utc: str,
    minimum_actual_f: float | None,
    model_version: int,
    probability_method: str,
    entry_policy: str,
) -> str:
    floor_text = "none" if minimum_actual_f is None else f"{minimum_actual_f:.1f}"
    return "|".join(
        [
            event_ticker,
            forecast_runtime_utc,
            floor_text,
            f"v{model_version}",
            probability_method,
            entry_policy,
        ]
    )
