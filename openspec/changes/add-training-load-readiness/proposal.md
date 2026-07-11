## Why

Garmin Connect and Strava's paid tier surface a "should I train or rest today?"
signal built on heart-rate–based training load, but this repo has no equivalent.
Now that the full activity history (1000+ FIT files back to 2019) is downloaded
locally, we can compute the same load/fitness/fatigue trend offline and give a
train-vs-rest recommendation without a subscription — the Chinese ask is
"借助相对负荷度等基于心率的指标来判断什么时候可以训练、什么时候应该休息".

## What Changes

- Add a per-activity **HR-based training load** ("相对负荷度" / relative effort)
  computed from a single FIT file using a Banister TRIMP model (HR-reserve
  weighted), fully offline like the existing `analyze` command.
- Add a **readiness** model that aggregates daily load across a date range into
  rolling **Fitness (CTL)**, **Fatigue (ATL)**, **Form/Freshness (TSB = CTL−ATL)**
  and the **acute:chronic workload ratio (ACWR)**, then maps those to a
  train / easy / rest recommendation with a short rationale.
- Add a new CLI subcommand `readiness` that batch-scans downloaded FIT files in a
  date range (mirroring the `laps` command) and prints the trend plus today's
  recommendation.
- Add HR configuration inputs (resting HR, max HR, sex) needed by the TRIMP model,
  read from the `env` file / environment variables with CLI overrides.
- Add plain-text report formatting for the load trend and recommendation,
  consistent with the existing `cli/reporting.py` formatters.

## Capabilities

### New Capabilities
- `training-load`: Compute a heart-rate–based training-load score ("relative
  effort") for a single activity from its FIT records, with a documented fallback
  when HR is missing and graceful handling of activities that lack HR entirely.
- `training-readiness`: Aggregate per-activity daily load over a date range into
  rolling fitness/fatigue/form and ACWR, and produce a dated train-vs-rest
  recommendation; expose this via a `readiness` CLI subcommand and a text report.

### Modified Capabilities
<!-- None: no existing specs under openspec/specs/. -->

## Impact

- **New code**: `garmin/` training-load module (per-activity load + rolling
  aggregation), a `readiness` handler in `cli/commands.py`, argparse wiring in
  `cli/parser.py`, a formatter in `cli/reporting.py`, and public exports in
  `garmin/__init__.py`.
- **Config**: new HR fields (resting HR, max HR, sex) in `garmin/config.py` and
  the `env` template/README.
- **Dependencies**: none beyond the existing `fitparse` / `pandas` stack.
- **Data**: reads local FIT files under `downloads/` (offline, no network).
- **Docs/Tests**: README section for `readiness`; unit tests for the pure
  load/aggregation math (TRIMP, CTL/ATL/TSB, ACWR, recommendation thresholds).
