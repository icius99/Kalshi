from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at_utc TEXT NOT NULL,
    market_snapshot_utc TEXT NOT NULL,
    weather_snapshot_utc TEXT NOT NULL,
    event_ticker TEXT NOT NULL,
    market_ticker TEXT NOT NULL,
    side TEXT NOT NULL CHECK(side IN ('YES','NO')),
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    model_probability_yes REAL NOT NULL,
    estimated_edge REAL NOT NULL,
    lead_hours REAL NOT NULL,
    model_lead_bucket INTEGER NOT NULL,
    model_sample_n INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'OPEN',
    settlement_yes INTEGER,
    gross_pnl REAL,
    UNIQUE(market_snapshot_utc, market_ticker, side)
);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute(SCHEMA)
    return conn
