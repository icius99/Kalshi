# Paper-trading layer

This layer is intentionally separate from the live collector and contains **no authenticated trading code**.

## 1. Inspect the current model vs market

After the historical NBM error model exists:

\`\`\`bash
python -m paper.current_signals \
  --db kalshi.db \
  --model data/models/nbm_error_model.json
\`\`\`

The comparator reconstructs the latest **NBM/NBS forecast that was actually available at the Kalshi snapshot timestamp**. This avoids applying an NBM historical error distribution to the different public NWS point-forecast product.

Defaults are intentionally conservative:

- minimum modeled edge: 5 percentage points
- execution/slippage reserve: 1 cent per contract
- minimum displayed top-of-book quantity: 10 contracts
- historical lead-time model must be within 8 hours of the current lead time

The execution reserve is **not** the exact Kalshi fee schedule.

## 2. Record qualifying paper positions

\`\`\`bash
python -m paper.record_signals
\`\`\`

Paper positions go into a separate local \`paper.db\`. Only one open position is allowed per market contract so five-minute snapshots do not create hundreds of highly correlated pseudo-trades.

The default paper size is capped at 25 contracts and can never exceed displayed top-of-book quantity.

## 3. Settle resolved positions

\`\`\`bash
python -m paper.settle
\`\`\`

This uses Kalshi's public market endpoint and \`settlement_value_dollars\`; it does not require an API key.

## 4. Review results

\`\`\`bash
python -m paper.summary
\`\`\`

Reported P&L is gross of exact Kalshi transaction fees until the fee model is implemented.

## Design rules

- Never use a model run published after the market snapshot being evaluated.
- Never substitute midpoint for executable ask when deciding an entry.
- Missing bid/ask means that side is not executable in the simulation.
- Require visible top-of-book size for the full paper position.
- Keep paper-trading storage separate from \`kalshi.db\`.
- Do not count repeated five-minute observations as independent positions.
- No real-money trading until chronological out-of-sample testing, exact fees, and slippage stress tests are complete.
