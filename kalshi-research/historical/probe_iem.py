#!/usr/bin/env python3
"""Small live smoke test for the IEM sources used by the historical model."""

from __future__ import annotations

import argparse
from datetime import date, timedelta

import requests

from historical.build_nbm_history import (
    DEFAULT_MODEL,
    DEFAULT_STATION,
    IEM_CLI,
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

CLI_REQUIRED_ALIASES = {
    "date": ("valid",),
    "high": ("high",),
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

    cli_rows = fetch_csv(
        session,
        IEM_CLI,
        {
            "station": args.station,
            "year": args.date.year,
            "fmt": "csv",
        },
    )

    if not cli_rows:
        raise SystemExit("IEM parsed CLI endpoint returned no rows.")

    assert_aliases(cli_rows[0], CLI_REQUIRED_ALIASES, "parsed CLI")

    print()
    print("Parsed CLI probe OK")
    print("Columns:")
    print("  " + ", ".join(cli_rows[0].keys()))
    print(f"Rows for {args.date.year}: {len(cli_rows):,}")

    matches = [
        row for row in cli_rows
        if _pick(row, *CLI_REQUIRED_ALIASES["date"]) == args.date.isoformat()
    ]
    if not matches:
        raise SystemExit(
            f"No parsed CLI observation found for {args.date.isoformat()}."
        )

    sample = matches[0]
    print(
        "Sample: "
        f"date={_pick(sample, *CLI_REQUIRED_ALIASES['date'])}, "
        f"high={_pick(sample, *CLI_REQUIRED_ALIASES['high'])}"
    )

    print()
    print("IEM historical source probe passed.")


if __name__ == "__main__":
    main()
