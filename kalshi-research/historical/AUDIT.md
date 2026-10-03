# Historical build audit

Before fitting or validating the multi-year model, build a deliberately small
window and inspect the forecast/observation pairs.

From \`kalshi-research/\`:

\`\`\`bash
python -m historical.build_nbm_history \
  --start 2026-09-01 \
  --end 2026-09-30 \
  --output data/historical/nbm_nyc_2026-09.csv

python -m historical.audit_dataset \
  data/historical/nbm_nyc_2026-09.csv
\`\`\`

The audit checks:

- every stored error equals \`actual - forecast\`
- no duplicate target-date/runtime records
- lead times fall near the expected 12/24/36/48/60/72 hour buckets
- row/day coverage
- bias, MAE, RMSE, residual standard deviation, and mean NBM \`XND\` by lead
- the largest absolute forecast misses for manual inspection

Do not scale the build to multiple years until the one-month audit passes and
the listed forecast/actual examples are plausible.
