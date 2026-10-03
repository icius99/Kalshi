import sqlite3
from datetime import datetime

DB = "kalshi.db"
EVENT = "KXHIGHNY-26OCT04"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# Most recent market snapshot timestamp for this event
ts = conn.execute("""
    SELECT MAX(timestamp_utc)
    FROM market_snapshots
    WHERE event_ticker = ?
""", (EVENT,)).fetchone()[0]

markets = conn.execute("""
    SELECT
        market_ticker,
        title,
        yes_bid,
        yes_ask
    FROM market_snapshots
    WHERE event_ticker = ?
      AND timestamp_utc = ?
    ORDER BY market_ticker
""", (EVENT, ts)).fetchall()

print(f"Kalshi snapshot: {ts}")
print()

rows = []
mid_sum = 0.0

for m in markets:
    bid = m["yes_bid"]
    ask = m["yes_ask"]

    if bid is None:
        bid = 0.0

    if ask is None:
        ask = 1.0

    mid = (bid + ask) / 2
    mid_sum += mid

    rows.append((m["title"], bid, ask, mid))

print("KALSHI DISTRIBUTION")
print("-" * 75)

for title, bid, ask, mid in rows:
    normalized = mid / mid_sum

    print(
        f"{title:<48} "
        f"bid={bid:.2f} "
        f"ask={ask:.2f} "
        f"mid={mid:.3f} "
        f"norm={normalized:.1%}"
    )

print()
print(f"Raw midpoint total: {mid_sum:.3f}")
print()

# Get most recent weather collection
weather_ts = conn.execute("""
    SELECT MAX(collected_at_utc)
    FROM weather_forecasts
""").fetchone()[0]

weather = conn.execute("""
    SELECT
        forecast_time,
        temperature_f,
        short_forecast
    FROM weather_forecasts
    WHERE collected_at_utc = ?
      AND substr(forecast_time, 1, 10) = '2026-10-04'
    ORDER BY forecast_time
""", (weather_ts,)).fetchall()


print(f"NWS snapshot: {weather_ts}")
print()

if weather:
    forecast_high = max(
        row["temperature_f"]
        for row in weather
        if row["temperature_f"] is not None
    )

    print(f"NWS forecast daily high: {forecast_high:.0f}°F")
    print()

    for row in weather:
        print(
            row["forecast_time"],
            f"{row['temperature_f']:.0f}°F",
            row["short_forecast"]
        )
else:
    print("No Oct. 4 weather forecast rows found.")

conn.close()