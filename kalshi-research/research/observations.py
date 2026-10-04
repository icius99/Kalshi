from __future__ import annotations

import math
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import requests

NWS_BASE = "https://api.weather.gov"
STATION = "KNYC"
NY = ZoneInfo("America/New_York")
HEADERS = {
    "User-Agent": "kalshi-weather-research/0.4 (paper intraday conditioning)"
}


def c_to_f(value_c: float) -> float:
    return value_c * 9.0 / 5.0 + 32.0


def fetch_observed_high_asof(
    target_date: date,
    asof_utc: datetime,
    station: str = STATION,
    session: requests.Session | None = None,
) -> dict | None:
    """Return highest reported Central Park temperature available by asof_utc.

    Queries only the target local calendar day through the market snapshot time,
    so live paper evaluation cannot incorporate observations after the quote.
    """
    if asof_utc.tzinfo is None:
        raise ValueError("asof_utc must be timezone-aware")

    asof_utc = asof_utc.astimezone(timezone.utc)
    local_asof = asof_utc.astimezone(NY)
    if target_date > local_asof.date():
        return None

    start_local = datetime.combine(target_date, time(0), tzinfo=NY)
    end_local = min(
        local_asof,
        datetime.combine(target_date, time(23, 59, 59), tzinfo=NY),
    )
    if end_local < start_local:
        return None

    client = session or requests.Session()
    response = client.get(
        f"{NWS_BASE}/stations/{station}/observations",
        params={
            "start": start_local.astimezone(timezone.utc).isoformat(),
            "end": end_local.astimezone(timezone.utc).isoformat(),
            "limit": 200,
        },
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()

    candidates = []
    for feature in response.json().get("features", []):
        props = feature.get("properties") or {}
        timestamp_text = props.get("timestamp")
        temperature = (props.get("temperature") or {}).get("value")
        if timestamp_text is None or temperature is None:
            continue

        try:
            timestamp = datetime.fromisoformat(
                timestamp_text.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            value_c = float(temperature)
        except (TypeError, ValueError):
            continue

        if not math.isfinite(value_c) or timestamp > asof_utc:
            continue

        local_timestamp = timestamp.astimezone(NY)
        if local_timestamp.date() != target_date:
            continue

        candidates.append(
            {
                "timestamp_utc": timestamp,
                "temperature_f": c_to_f(value_c),
            }
        )

    if not candidates:
        return None

    high = max(candidates, key=lambda item: item["temperature_f"])
    return {
        "station": station,
        "source": "nws_api_station_observations",
        "asof_utc": asof_utc,
        "observed_high_f": high["temperature_f"],
        "high_observation_utc": high["timestamp_utc"],
        "observation_count": len(candidates),
    }


def conservative_minimum_settlement_high(
    observed_high_f: float,
    source_buffer_f: float = 1.0,
) -> int:
    """Conservative integer lower bound for final settlement high.

    NWS is a proxy for the current TWC settlement source. Subtract a configurable
    source/rounding buffer before flooring so conditioning cannot become falsely
    overconfident from a one-degree source mismatch.
    """
    if source_buffer_f < 0:
        raise ValueError("source_buffer_f must be non-negative")
    return math.floor(observed_high_f - source_buffer_f)
