# Historical NYC high-temperature model

This directory builds the first independent probability model for the Kalshi
`KXHIGHNY` daily-high market.

## Why NBS/NBM for the first baseline?

The live collector stores the public NWS point forecast, but the public
`api.weather.gov` endpoint is not a historical forecast archive. For historical
verification we start with the NWS National Blend of Models (NBS text guidance)
archived by Iowa State's IEM. It provides:

- `TXN`: 18-hour max/min temperature guidance
- `XND`: standard deviation of the max/min guidance
- archived model runs, so there is no look-ahead bias

Realized highs come from IEM's NWSCLI daily climate summaries for `KNYC`
(Central Park).

This baseline is intentionally separate from `collector.py`; no historical
research code modifies the live database or timer.

## Build a dataset

From `kalshi-research/`:

```bash
source .venv/bin/activate
python -m historical.build_nbm_history \
  --start 2021-01-01 \
  --end 2026-09-30
```

Output defaults to:

```
data/historical/nbm_nyc_daily_high.csv
```

The script requests NWSCLI observations year-by-year and retries IEM 429/5xx
responses with bounded backoff. This matters even for small probes: the service
can throttle closely spaced CGI requests.

## Fit the empirical error model

```bash
python -m historical.forecast_error \
  data/historical/nbm_nyc_daily_high.csv
```

This selects one forecast per target date for each nominal 12/24/36/48/60-hour
lead, then stores both summary statistics and the full integer-Fahrenheit error
histogram. The empirical histogram is the live probability baseline; historical
mean bias is retained as diagnostics but is not applied to the current NBM
forecast. The JSON model is written to:

```
data/models/nbm_error_model.json
```

## Important modeling notes

1. The dataset uses the **forecast that existed at the time**, not a reforecast.
2. NOAA's NBM station-card definition reports TXN minimums at 12Z and TXN
   maximums at 00Z on the following day. We therefore use only 00Z TXN records
   for KNYC daily-high modeling and map each one to the preceding target date.
3. Lead time is measured to 3 PM America/New_York on the target date. That is an
   analysis convention, not a claim that the high always occurs at 3 PM.
4. The fitted normal distribution is only a baseline. We should test empirical
   residual distributions, seasonality, precipitation regimes, and NBM's own
   `XND` uncertainty before using model probabilities for paper trading.
5. NWS climate-summary day boundaries can differ subtly from a strict midnight
   local calendar day during DST. This should be audited against Kalshi's actual
   Weather Company settlement history before real-money use.

## Next research steps

- Validate the generated rows around DST transitions and known hot/cold days.
- Compare model `XND` against realized error; it may outperform one global sigma.
- Add out-of-sample splits by calendar time.
- Add a current-market comparator that maps the model distribution into the six
  Kalshi temperature buckets and measures edge against executable asks.
- Add raw archived NDFD as a second independent model, not as a dependency of
  this baseline.


## Live IEM schema smoke test

Before starting a multi-year download, verify that IEM's live/archive CSV schema
still matches the parser assumptions:

```bash
python -m historical.probe_iem --date 2026-09-25
```

The probe is intentionally tiny. It prints the returned MOS and daily-climate
column names, separates 00Z TXN maxima from 12Z TXN minima, shows one maximum
`TXN/XND` sample, and exits non-zero if required fields are missing.

## Chronological out-of-sample validation

After building the historical dataset, validate without fitting on the test
period:

```bash
python -m historical.validate_chronological \
  data/historical/nbm_nyc_daily_high.csv
```

By default the earliest 75% of distinct target dates are used for training and
the latest 25% are held out. You can freeze a specific cutoff instead:

```bash
python -m historical.validate_chronological \
  data/historical/nbm_nyc_daily_high.csv \
  --test-start 2025-01-01
```

The report includes raw/corrected RMSE, probabilistic log score, and 50/80/90%
interval coverage for each lead-time bucket. A useful model should not merely
reduce RMSE; its uncertainty should also be reasonably calibrated. Persistent
under-coverage means the model is overconfident and should not be used to infer
market edge.

## Fee-aware paper signals

As of the July 7, 2026 general Kalshi fee schedule, standard event-contract
taker fees are modeled as `0.07 * C * P * (1-P)`, rounded up to the next cent
for the batch. KXHIGHNY is not listed as a non-standard series in that schedule.
Paper-signal edge therefore subtracts both the modeled taker fee and a separate
configurable slippage/execution reserve.

The fee schedule can change; verify the active Kalshi fee schedule before any
real-money use.


## Empirical baseline decision

A chronological 2021-2026 holdout comparison found that the empirical integer
residual distribution improved exact-temperature log loss at 12h and 24h,
essentially tied the unshifted normal at 36h, improved at 48h, and was only
slightly worse at 60h. Applying the training-period mean bias worsened holdout
RMSE at every tested horizon.

Accordingly the default live model:

- uses the empirical historical error distribution;
- applies light Laplace smoothing to avoid zero-probability tails;
- does **not** shift today's NBM forecast by the historical mean error;
- supports 12-60h nominal leads by default;
- refuses to stretch the nearest calibration by more than six hours.

The 72h bucket remains available for research but is excluded from the default
model because the historical archive had materially thinner coverage there.
