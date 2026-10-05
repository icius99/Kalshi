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

1. checks open paper positions and live forecast evaluations against Kalshi's
   public settlement fields;
2. settles resolved simulated positions;
3. scores resolved probability vectors with multiclass Brier score and log loss;
4. evaluates the next eligible `KXHIGHNY` market snapshot;
5. revalidates qualifying entries against fresh Kalshi orderbooks;
6. records any new simulated positions and the live probability state.

The promoted model at `data/models/nbm_error_model.json` must match the current
versioned forecast definition. A stale or legacy model is rejected.

## Live evaluation ledger

`paper_evaluations` stores the probability vector even when no trade is opened.
States are deduplicated by event, NBM runtime, observed-high floor, model
generation, probability method, and entry policy. Repeated five-minute timer
runs therefore do not masquerade as independent forecasts.

At settlement, exactly one winning Kalshi bucket must be available before an
evaluation is scored.

- **Multiclass Brier** is the sum across buckets of `(p - outcome)^2`.
- **Log loss** is `-log(p)` for the winning bucket.

For headline live calibration, `paper.summary` further collapses the stored
states to one forecast per event / nominal lead bucket, choosing the runtime
closest to that bucket. This mirrors the historical sampling logic and avoids
pseudo-replication from correlated model cycles.

## Current research safeguards

- minimum modeled net edge: 5%
- execution/slippage reserve: 0.5 cents per contract
- minimum visible top-of-book quantity: 10 contracts
- maximum simulated position: 25 contracts
- nearest calibrated lead bucket within 6 hours
- 1 F conservative NWS/TWC observation buffer
- collector snapshot no older than 20 minutes
- no new entry inside 3 hours of the 3 PM ET anchor
- fresh Kalshi orderbook revalidation immediately before simulated entry

These are research defaults, not recommendations for real-money trading.

## Reporting

```bash
python -m paper.summary
```

The summary reports simulated P&L plus live out-of-sample calibration. Position
P&L is grouped by event because contracts from the same daily temperature event
are not independent.
