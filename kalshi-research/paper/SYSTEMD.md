# Unattended paper operation

The collector remains the source of archived market snapshots. The paper timer is
a separate paper-only process; it cannot place real Kalshi orders.

## Install the user timer

From `kalshi-research/`:

```bash
python -m paper.install_timer --dry-run
python -m paper.install_timer
```

The installer writes:

- `~/.config/systemd/user/kalshi-paper-cycle.service`
- `~/.config/systemd/user/kalshi-paper-cycle.timer`

The timer runs every five minutes at minute 2/7/12/... so it is offset from the
existing collector's minute 0/5 cadence.

The service freezes the current research safeguards explicitly:

- minimum net modeled edge: 5%
- execution/slippage reserve: 0.5 cents per contract
- minimum visible quantity: 10
- maximum simulated position: 25 contracts
- calibrated NBM lead bucket within 6 hours
- 1 F conservative NWS/TWC observation buffer
- collector snapshot no older than 20 minutes
- no new entry inside 3 hours of the 3 PM ET anchor
- fresh Kalshi orderbook revalidation immediately before recording a paper entry

## Inspect operation

```bash
systemctl --user list-timers kalshi-paper-cycle.timer --no-pager
systemctl --user status kalshi-paper-cycle.timer
journalctl --user -u kalshi-paper-cycle.service -n 50 --no-pager
python -m paper.summary
```

## Stop unattended paper operation

```bash
systemctl --user disable --now kalshi-paper-cycle.timer
```

No real-order placement code is used by this timer.
