#!/usr/bin/env python3
"""Install the paper-only cycle as a systemd user timer."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


SERVICE_NAME = "kalshi-paper-cycle.service"
TIMER_NAME = "kalshi-paper-cycle.timer"


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--unit-dir",
        type=Path,
        default=Path.home() / ".config/systemd/user",
    )
    return parser.parse_args()


def render_service(root: Path, python: Path) -> str:
    return f"""[Unit]
Description=Kalshi NYC paper-trading evaluation cycle
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory={root}
Environment=PYTHONUNBUFFERED=1
ExecStart={python} -m paper.run_cycle --min-edge 0.05 --execution-buffer 0.005 --min-qty 10 --max-contracts 25 --max-model-distance 6 --anchor-hour 15 --observation-buffer-f 1 --max-snapshot-age-minutes 20 --min-market-lead-hours 3
"""


def render_timer() -> str:
    return """[Unit]
Description=Run Kalshi NYC paper evaluation every five minutes

[Timer]
OnCalendar=*:2/5
Persistent=true
AccuracySec=15s
Unit=kalshi-paper-cycle.service

[Install]
WantedBy=timers.target
"""


def install(unit_dir: Path, dry_run: bool = False) -> tuple[Path, Path]:
    root = Path(__file__).resolve().parents[1]
    python = root / ".venv/bin/python"

    if not python.exists():
        raise SystemExit(f"Virtualenv Python not found: {python}")

    service_path = unit_dir / SERVICE_NAME
    timer_path = unit_dir / TIMER_NAME
    service_text = render_service(root, python)
    timer_text = render_timer()

    if dry_run:
        print(f"--- {service_path} ---")
        print(service_text)
        print(f"--- {timer_path} ---")
        print(timer_text)
        return service_path, timer_path

    unit_dir.mkdir(parents=True, exist_ok=True)
    service_path.write_text(service_text, encoding="utf-8")
    timer_path.write_text(timer_text, encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(
        ["systemctl", "--user", "enable", "--now", TIMER_NAME],
        check=True,
    )

    return service_path, timer_path


def main():
    args = parse_args()
    service_path, timer_path = install(args.unit_dir, args.dry_run)

    if args.dry_run:
        return

    print(f"Installed {service_path}")
    print(f"Installed {timer_path}")
    print()
    subprocess.run(
        ["systemctl", "--user", "list-timers", TIMER_NAME, "--no-pager"],
        check=False,
    )
    print()
    print(
        "Logs: journalctl --user -u kalshi-paper-cycle.service "
        "-n 50 --no-pager"
    )


if __name__ == "__main__":
    main()
