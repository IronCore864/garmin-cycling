## 1. Configuration (athlete HR profile)

- [x] 1.1 Add an `AthleteProfile` dataclass to `garmin/config.py` (resting HR, max HR, sex, optional age) and parse new `env` keys (e.g. `GARMIN_RESTING_HR`, `GARMIN_MAX_HR`, `GARMIN_SEX`, `GARMIN_AGE`) in `load_config`.
- [x] 1.2 Implement max-HR resolution: use configured max HR, else estimate from age (Tanaka `208 − 0.7·age`); raise a clear error when neither is available.
- [x] 1.3 Document the new `env` keys in `README.md` and the `env` example table.

## 2. Per-activity training load (`training-load` capability)

- [x] 2.1 Create `garmin/training_load.py` with a pure `activity_load(fit_file, profile)` that sums HR-reserve–weighted Banister TRIMP over elapsed sample intervals and returns an integer score.
- [x] 2.2 Clamp HR reserve to `[0, 1]` and select the sex coefficient `k` (1.92 male / 1.67 female); weight each sample by elapsed minutes since the previous sample.
- [x] 2.3 Return an explicit "no HR data" result for activities lacking usable `heart_rate`, without raising.

## 3. Rolling readiness model (`training-readiness` capability)

- [x] 3.1 Implement `aggregate_daily_load(...)` that scans a directory of FIT files in a date range (reusing the `laps` filename-date pattern), sums per-day load, and zero-fills gap days into a continuous series.
- [x] 3.2 Implement `rolling_metrics(series)` computing EWMA CTL (τ=42) and ATL (τ=7) and `TSB = CTL(prev) − ATL(prev)` per day.
- [x] 3.3 Implement `acwr(series)` for 7-day acute / 28-day chronic ratio, returning `undefined` when chronic load is zero.
- [x] 3.4 Implement `recommend(tsb, acwr)` mapping to `rest | easy | train` plus a `caution` overload flag, with named threshold constants and a short rationale string.
- [x] 3.5 Add a directory batch helper (mirroring `count_laps_in_directory`) returning the daily series, latest metrics, and recommendation; handle empty ranges gracefully.

## 4. CLI integration

- [x] 4.1 Add a `readiness` subparser in `cli/parser.py` with `--start/--end/--year/--month/--dir` (matching `laps`) plus optional `--max-hr/--resting-hr/--sex/--age` overrides.
- [x] 4.2 Add `run_readiness` in `cli/commands.py`: load config/profile, run the batch helper, print the report; print a "no data" message on empty ranges.
- [x] 4.3 Add `format_readiness_report(...)` in `cli/reporting.py` showing the recent CTL/ATL/TSB + ACWR trend and today's dated recommendation.
- [x] 4.4 Export the new public functions/classes from `garmin/__init__.py`.

## 5. Tests & verification

- [x] 5.1 Unit-test `activity_load`: continuous HR yields positive score, higher average HR ⇒ higher load, irregular sample gaps weighted by elapsed time, and no-HR ⇒ "no HR data".
- [x] 5.2 Unit-test aggregation & metrics: multi-activity day sums, zero-fill rest days, ATL rises faster than CTL under load and falls faster under rest, ACWR ≈ 1.0 balanced and `undefined` on zero chronic.
- [x] 5.3 Unit-test `recommend`: deep-fatigue ⇒ rest/easy, fresh+balanced ⇒ train, high ACWR ⇒ caution flag.
- [x] 5.4 Run `make lint` and `uv run pytest`; fix any failures.
- [x] 5.5 Smoke-test `uv run python main.py readiness --dir downloads` against the downloaded history and sanity-check the output.
