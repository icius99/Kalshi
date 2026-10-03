# Paper-trading layer

This layer is intentionally separated from the live collector and contains **no authenticated trading code**.

## Inspect current signals

After building the historical error model:

```bash
python -m paper.current_signals \
  --db kalshi.db \
  --model data/models/nbm_error_model.json
```

Defaults are deliberately conservative for an early research build:

- minimum modeled edge: 5 percentage points
- execution/slippage reserve: 1 cent per contract
- minimum displayed top-of-book quantity: 10 contracts
- closest historical lead-time model must be within 8 hours

The execution reserve is **not** a Kalshi fee model. Until fees are encoded and tested, any displayed edge should be treated as pre-fee research only.

## Design rules

- Never use a weather snapshot collected after the market snapshot being evaluated.
- Never substitute midpoint for executable ask when deciding a hypothetical entry.
- Missing bid/ask means that side is not executable in the simulation.
- Paper-trading storage lives separately from `kalshi.db` so research bugs cannot damage collection history.
- No real-money trading should be added until the model survives chronological out-of-sample testing and fee/slippage stress tests.
