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
    status TEXT NOT NULL DEFAULT 'OPEN',
    settlement_yes INTEGER,
    gross_pnl REAL,
    net_pnl REAL
);
CREATE INDEX IF NOT EXISTS idx_paper_open
ON paper_signals(status, market_ticker);
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
