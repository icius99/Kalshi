from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import requests

from historical.build_nbm_history import (
    DEFAULT_MODEL,
    DEFAULT_STATION,
    DEFAULT_TZ,
    FORECAST_DEFINITION,
    IEM_MOS,
    USER_AGENT,
    extract_daily_high_forecasts,
    fetch_csv,
    nearest_per_runtime_target,
)


def select_forecast_asof(
    rows: list[dict[str, str]],
    target_date: date,
    asof_utc: datetime,
    anchor_hour: int = 15,
    tz_name: str = DEFAULT_TZ,
) -> dict:
    """Return the most recent NBM daily-high forecast known at the as-of timestamp."""
    if asof_utc.tzinfo is None:
        raise ValueError("asof_utc must be timezone-aware")
    asof_utc = asof_utc.astimezone(timezone.utc)
    forecasts = extract_daily_high_forecasts(rows, tz_name, anchor_hour)
    forecasts = nearest_per_runtime_target(forecasts)
    candidates = [
        item
        for item in forecasts
        if item["target_date"] == target_date and item["runtime_utc"] <= asof_utc
    ]
    if not candidates:
        raise ValueError(
            f"no NBM daily-high forecast found for {target_date} as of {asof_utc.isoformat()}"
        )
    return max(candidates, key=lambda item: item["runtime_utc"])


def fetch_forecast_asof(
    target_date: date,
    asof_utc: datetime,
    station: str = DEFAULT_STATION,
    model: str = DEFAULT_MODEL,
    anchor_hour: int = 15,
    tz_name: str = DEFAULT_TZ,
    session: requests.Session | None = None,
) -> dict:
    """Reconstruct the latest NBM daily-high forecast available at a timestamp."""
    if asof_utc.tzinfo is None:
        raise ValueError("asof_utc must be timezone-aware")
    asof_utc = asof_utc.astimezone(timezone.utc)
    own_session = session is None
    session = session or requests.Session()
    if own_session:
        session.headers.update({"User-Agent": USER_AGENT})

    start = (asof_utc - timedelta(days=3)).date()
    rows = fetch_csv(
        session,
        IEM_MOS,
        {
            "station": station,
            "model": model,
            "sts": f"{start.isoformat()}T00:00Z",
            "ets": f"{(asof_utc.date() + timedelta(days=1)).isoformat()}T00:00Z",
            "format": "csv",
        },
    )
    return select_forecast_asof(rows, target_date, asof_utc, anchor_hour, tz_name)
