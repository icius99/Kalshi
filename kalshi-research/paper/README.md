# Paper-trading loop

The paper layer never places real orders. It reads collected Kalshi snapshots,
reconstructs the contemporaneous NBM forecast, applies the promoted calibration
model, and records qualifying simulated entries in `paper.db`.

## One maintenance cycle

From `kalshi-research/`:

```bash
python -m paper.run_cycle
```

One cycle:

1. checks open paper positions against Kalshi's public settlement fields;
2. settles any resolved positions;
3. evaluates the latest collected `KXHIGHNY` market snapshot;
4. records new qualifying simulated positions.

The cycle is designed to be safe to run repeatedly. The ledger prevents a
second open paper position in the same market contract.

The promoted model at `data/models/nbm_error_model.json` must match the current
versioned forecast definition. A stale or legacy model is rejected.

## Defaults

- minimum modeled net edge: 5%
- execution/slippage reserve: 0.5 cents per contract
- minimum visible top-of-book quantity: 10 contracts
- maximum simulated position: 25 contracts
- nearest calibrated lead bucket must be within 6 hours

These are research defaults, not recommendations for real-money trading.

## Reporting

```bash
python -m paper.summary
```

The summary reports aggregate net P&L, event-level correlated exposure, and
performance by model generation/probability method.
