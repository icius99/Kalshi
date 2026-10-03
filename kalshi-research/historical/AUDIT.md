# Historical build audit

Before fitting or validating the multi-year model, build a deliberately small
window and inspect the forecast/observation pairs.

From `kalshi-research/`:

```bash
python -m historical.build_nbm_history \
  --start 2026-09-01 \
  --end 2026-09-30 \
  --output data/historical/nbm_nyc_2026-09.csv

python -m historical.audit_dataset \
  data/historical/nbm_nyc_2026-09.csv
```

The audit reports both:

- every archived six-hour NBM run; and
- the independent sample actually used by model fitting, with at most one
  forecast per target date / nominal lead bucket.

It checks:

- every stored error equals `actual - forecast`
- no duplicate target-date/runtime records
- lead times fall near the expected 12/24/36/48/60/72 hour buckets
- row/day coverage
- bias, MAE, RMSE, residual standard deviation, and mean NBM `XND` by lead
- the largest absolute errors in the independent sampled set

## Multi-year pipeline

Once the one-month audit passes, run the full workflow with dated outputs:

```bash
python -m historical.run_research_pipeline \
  --start 2021-01-01 \
  --end 2026-09-30 \
  --test-start 2025-01-01
```

The pipeline runs, in order:

1. historical NBM/CLI build
2. structural/statistical audit
3. chronological holdout validation
4. empirical error-model fitting

It creates date-stamped dataset, validation, and model files. It deliberately
does **not** overwrite `data/models/nbm_error_model.json`.

After reviewing the validation output, the exact same completed dataset can be
reused without downloading again:

```bash
python -m historical.run_research_pipeline \
  --start 2021-01-01 \
  --end 2026-09-30 \
  --test-start 2025-01-01 \
  --skip-build \
  --promote-model
```

Promotion is explicit so an experimental or failed research run cannot silently
become the model used by live paper-signal analysis.
