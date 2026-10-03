import requests
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://external-api.kalshi.com/trade-api/v2"
SERIES = "KXHIGHNY"

DB_PATH = Path("kalshi.db")

WEATHER_LAT = 40.7812
WEATHER_LON = -73.9665

HEADERS = {
    "User-Agent": "kalshi-weather-research/0.1"
}

def get_connection():
    conn = sqlite3.connect(DB_PATH)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            timestamp_utc TEXT NOT NULL,

            series_ticker TEXT NOT NULL,
            event_ticker TEXT NOT NULL,
            market_ticker TEXT NOT NULL,

            title TEXT,

            floor_strike REAL,
            cap_strike REAL,

            yes_bid REAL,
            yes_bid_qty REAL,

            yes_ask REAL,
            yes_ask_qty REAL,

            volume REAL,

            close_time TEXT,
            expiration_time TEXT
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_market_time
        ON market_snapshots(market_ticker, timestamp_utc)
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_event_time
        ON market_snapshots(event_ticker, timestamp_utc)
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_forecasts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            collected_at_utc TEXT NOT NULL,
            forecast_generated_at TEXT,

            location TEXT NOT NULL,

            forecast_time TEXT NOT NULL,
            temperature_f REAL,

            short_forecast TEXT,
            probability_of_precipitation REAL,
            wind_speed TEXT,
            wind_direction TEXT
        )
    """)

    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_weather_time
        ON weather_forecasts(forecast_time, collected_at_utc)
    """)

    return conn


def get_open_markets():
    response = requests.get(
        f"{BASE}/markets",
        params={
            "series_ticker": SERIES,
            "status": "open",
        },
        timeout=10,
    )

    response.raise_for_status()
    return response.json()["markets"]


def get_orderbook(ticker):
    response = requests.get(
        f"{BASE}/markets/{ticker}/orderbook",
        timeout=10,
    )

    response.raise_for_status()

    return response.json()["orderbook_fp"]


def get_best_prices(book):

    yes_bids = book.get("yes_dollars") or []
    no_bids = book.get("no_dollars") or []

    best_yes = (
        max(yes_bids, key=lambda x: float(x[0]))
        if yes_bids
        else None
    )

    best_no = (
        max(no_bids, key=lambda x: float(x[0]))
        if no_bids
        else None
    )

    if best_yes:
        yes_bid = float(best_yes[0])
        yes_bid_qty = float(best_yes[1])
    else:
        yes_bid = None
        yes_bid_qty = None

    if best_no:
        no_bid = float(best_no[0])

        # Buying YES is equivalent to selling NO.
        yes_ask = round(1.0 - no_bid, 4)
        yes_ask_qty = float(best_no[1])
    else:
        yes_ask = None
        yes_ask_qty = None

    return (
        yes_bid,
        yes_bid_qty,
        yes_ask,
        yes_ask_qty,
    )


def collect():

    timestamp = datetime.now(timezone.utc).isoformat()

    markets = get_open_markets()

    conn = get_connection()

    rows = []

    for market in markets:

        ticker = market["ticker"]

        try:
            book = get_orderbook(ticker)

        except Exception as exc:
            print(f"Failed orderbook {ticker}: {exc}")
            continue

        (
            yes_bid,
            yes_bid_qty,
            yes_ask,
            yes_ask_qty,
        ) = get_best_prices(book)

        row = (
            timestamp,

            SERIES,
            market["event_ticker"],
            ticker,

            market.get("title"),

            market.get("floor_strike"),
            market.get("cap_strike"),

            yes_bid,
            yes_bid_qty,

            yes_ask,
            yes_ask_qty,

            float(market.get("volume_fp", 0)),

            market.get("close_time"),
            market.get("expiration_time"),
        )

        rows.append(row)

    conn.executemany("""
        INSERT INTO market_snapshots (
            timestamp_utc,
            series_ticker,
            event_ticker,
            market_ticker,
            title,
            floor_strike,
            cap_strike,
            yes_bid,
            yes_bid_qty,
            yes_ask,
            yes_ask_qty,
            volume,
            close_time,
            expiration_time
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    weather_rows = store_weather(
        conn,
        timestamp,
    )

    conn.commit()
    conn.close()

    print(
        f"{timestamp}: stored "
        f"{len(rows)} market snapshots and "
        f"{weather_rows} weather forecast rows"
    )

def get_hourly_weather():

    point_url = (
        f"https://api.weather.gov/points/"
        f"{WEATHER_LAT},{WEATHER_LON}"
    )

    point_response = requests.get(
        point_url,
        headers=HEADERS,
        timeout=10,
    )

    point_response.raise_for_status()

    point_props = point_response.json()["properties"]

    hourly_url = point_props["forecastHourly"]

    response = requests.get(
        hourly_url,
        headers=HEADERS,
        timeout=10,
    )

    response.raise_for_status()

    data = response.json()["properties"]

    generated_at = data.get("generatedAt")
    periods = data["periods"]

    return generated_at, periods


def store_weather(conn, collected_at):

    generated_at, periods = get_hourly_weather()

    rows = []

    for period in periods:

        precip = period.get(
            "probabilityOfPrecipitation",
            {}
        ).get("value")

        row = (
            collected_at,
            generated_at,
            "Central Park NYC",

            period["startTime"],
            period["temperature"],

            period.get("shortForecast"),
            precip,
            period.get("windSpeed"),
            period.get("windDirection"),
        )

        rows.append(row)

    conn.executemany("""
        INSERT INTO weather_forecasts (
            collected_at_utc,
            forecast_generated_at,
            location,
            forecast_time,
            temperature_f,
            short_forecast,
            probability_of_precipitation,
            wind_speed,
            wind_direction
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, rows)

    return len(rows)


if __name__ == "__main__":
    collect()