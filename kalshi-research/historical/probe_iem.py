#!/usr/bin/env python3
"""Small live smoke test for the IEM sources used by the historical model."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import requests

from historical.build_nbm_history import (
    DEFAULT_MODEL,
    DEFAULT_STATION,
    IEM_DAILY,
    IEM_MOS,
    USER_AGENT,
    _parse_datetime,
    _pick,
    fetch_csv,
)


MOS_REQUIRED_ALIASES = {
    "runtime": ("runtime", "runtime_utc", "run_time", "model_run"),
    "valid": ("ftime", "ftime_utc", "valid", "valid_time"),
    "txn": ("txn",),
}

DAILY_REQUIRED_ALIASES = {
    "date": ("day", "date", "valid"),
    "max_temp_f": ("max_temp_f", "high", "max_tmpf"),
}


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", type=date.fromisoformat, default=date.today() - timedelta(days=7))
    parser.add_argument("--station", default=DEFAULT_STATION)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    return parser.parse_args()


def assert_aliases(row: dict[str, str], aliases: dict[str, tuple[str, ...]], source: str):
    missing = []
    for logical_name, names in aliases.items():
        if _pick(row, *names) is None:
            missing.append((logical_name, names))
    if missing:
        details = ", ".join(
            f"{logical} via {names}" for logical, names in missing
        )
        raise SystemExit(
            f"{source}: required fields not found: {details}\n"
            f"Returned columns: {', '.join(row.keys())}"
        )


def main():
    args = parse_args()
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    mos_rows = fetch_csv(
        session,
        IEM_MOS,
        {
            "station": args.station,
            "model": args.model,
            "sts": f"{args.date.isoformat()}T00:00Z",
            "ets": f"{(args.date + timedelta(days=2)).isoformat()}T00:00Z",
            "format": "csv",
        },
    )

    if not mos_rows:
        raise SystemExit("IEM MOS returned no rows for the probe window.")

    assert_aliases(mos_rows[0], MOS_REQUIRED_ALIASES, "MOS")

    print("MOS probe OK")
    print("Columns:")
    print("  " + ", ".join(mos_rows[0].keys()))
    print(f"Rows: {len(mos_rows):,}")

    txn_rows = [row for row in mos_rows if _pick(row, "txn") not in (None, "", "M")]
    max_rows = []
    min_rows = []
    other_rows = []

    for row in txn_rows:
        valid = _parse_datetime(_pick(row, *MOS_REQUIRED_ALIASES["valid"]))
        if valid is None:
            other_rows.append(row)
        elif valid.hour == 0 and valid.minute == 0:
            max_rows.append(row)
        elif valid.hour == 12 and valid.minute == 0:
            min_rows.append(row)
        else:
            other_rows.append(row)

    print(f"Rows with TXN: {len(txn_rows):,}")
    print(f"  00Z maximum rows: {len(max_rows):,}")
    print(f"  12Z minimum rows: {len(min_rows):,}")
    print(f"  other valid times: {len(other_rows):,}")

    sample = max_rows[0] if max_rows else (txn_rows[0] if txn_rows else None)
    if sample:
        print("TXN maximum sample:" if max_rows else "TXN sample:")
        print(f"  runtime={_pick(sample, *MOS_REQUIRED_ALIASES['runtime'])}")
        print(f"  valid={_pick(sample, *MOS_REQUIRED_ALIASES['valid'])}")
        print(f"  txn={_pick(sample, 'txn')}")
        print(f"  xnd={_pick(sample, 'xnd')}")

    daily_rows = fetch_csv(
        session,
        IEM_DAILY,
        {
            "sts": args.date.isoformat(),
            "ets": args.date.isoformat(),
            "network": "NWSCLI",
            "stations": args.station,
            "var": "max_temp_f",
            "format": "csv",
            "na": "",
        },
    )

    if not daily_rows:
        raise SystemExit("IEM daily climate endpoint returned no rows.")

    assert_aliases(daily_rows[0], DAILY_REQUIRED_ALIASES, "daily climate")

    print()
    print("Daily climate probe OK")
    print("Columns:")
    print("  " + ", ".join(daily_rows[0].keys()))
    print(f"Rows: {len(daily_rows):,}")
    sample = daily_rows[0]
    print(
        "Sample: "
        f"date={_pick(sample, *DAILY_REQUIRED_ALIASES['date'])}, "
        f"max_temp_f={_pick(sample, *DAILY_REQUIRED_ALIASES['max_temp_f'])}"
    )

    print()
    print("IEM historical source probe passed.")


if __name__ == "__main__":
    main()
