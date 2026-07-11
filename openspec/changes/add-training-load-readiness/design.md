## Context

The repo already downloads every activity as a FIT file into `downloads/`, named
`YYYY-MM-DD_<activityId>_<name>.fit`. Two existing patterns are directly reusable:

- **Offline single-FIT analysis** (`garmin/power.py` + `analyze` CLI): parse one
  `fitparse.FitFile`, compute pure metrics, format text — no network.
- **Batch-over-a-directory-in-a-range** (`garmin/laps.py::count_laps_in_directory`
  + `laps` CLI): iterate FIT files, filter by the date embedded in the filename,
  aggregate results.

`garmin/analytics.py` already shows how to pull `timestamp` / `heart_rate` from
`record` messages via pandas. `garmin/config.py` loads typed config from `env` +
environment variables. This feature reuses all of these; the only genuinely new
logic is the load math (TRIMP) and the rolling fitness/fatigue/form model.

Strava's "Relative Effort" and the Fitness/Freshness (CTL/ATL/TSB) trend, plus
sports-science ACWR, are the reference models. All are computable from HR alone.

## Goals / Non-Goals

**Goals:**
- Per-activity HR-based load score computable offline from one FIT file.
- A daily-aggregated rolling trend (Fitness/Fatigue/Form + ACWR) over a date range
  from local FIT files, with a dated train / easy / rest recommendation.
- A `readiness` CLI command mirroring `laps` ergonomics (`--start/--end/--year/
  --month/--dir`), plus a text report matching `cli/reporting.py` style.
- Pure, unit-testable math with no new dependencies.

**Non-Goals:**
- No power-based TSS/NP load model (HR-only for this change; power can come later).
- No GUI/plot output (the existing VO2max image path is out of scope here).
- No per-second physiological modeling beyond TRIMP; no HRV/sleep inputs.
- No user-facing date/range/window flags: readiness answers "how am I today?" over
  a fixed lookback it manages itself.

## Decisions

**1. Load metric: Banister HR-reserve TRIMP.**
Chosen over Edwards zone-TRIMP and Lucia's TRIMP because it needs only resting HR,
max HR and sex (no lactate-threshold test or zone table) while still weighting
intensity exponentially. Formula per sample:
`Σ dt_min × HRr × 0.64 × e^(k·HRr)`, `HRr=(HR−rest)/(max−rest)` clamped `[0,1]`,
`k=1.92` male / `1.67` female. This is the "相对负荷度" score.
_Alternatives:_ Edwards (needs zone boundaries), TSS from power (needs FTP + power
meter — not all activities have power). TRIMP maximizes coverage of the dataset.

**2. Daily aggregation keyed by filename date.**
Reuse the `laps` pattern: derive the activity date from the `YYYY-MM-DD` filename
prefix rather than re-parsing session timestamps, keeping directory scans cheap
and consistent with existing code. Sum all activities per calendar day; fill gap
days with zero so the EWMA series is continuous.
_Alternative:_ read `startTimeLocal` from FIT session — rejected as redundant and
slower; the downloader already encodes the date in the name.

**3. Fitness/Fatigue/Form via EWMA (CTL/ATL/TSB).**
Standard exponentially-weighted moving averages: CTL time constant 42 days, ATL 7
days, `TSB(today) = CTL(yesterday) − ATL(yesterday)`. Implemented as a simple
recurrence `x_today = x_yesterday + (load_today − x_yesterday)/τ` over the
zero-filled daily series, so it is deterministic and testable without pandas.
_Alternative:_ simple rolling sums — rejected; EWMA is the established
fitness/freshness model and reacts smoothly.

**4. ACWR as a complementary acute/chronic guardrail.**
Compute acute (7-day) vs chronic (28-day average) load ratio; report `undefined`
when chronic is zero. ACWR catches rapid ramp-ups that TSB alone may miss, and the
0.8–1.3 "sweet spot" / >1.5 high-risk bands are well documented.

**5. Recommendation = rules over (TSB, ACWR).**
A small, transparent threshold table maps `(TSB, ACWR)` → `rest | easy | train`
plus a `caution` overload flag, each with a one-line rationale. Thresholds live as
named constants so they are easy to tune and unit-test. Kept rule-based (not ML)
for explainability and zero dependencies.

**6. Fixed recent window + automatic source selection.**
Readiness is a "current state" question, so the command takes no date/range/dir
flags: it uses a fixed 42-day lookback ending today (enough for CTL and ACWR).
To stay current without forcing a manual sync, it auto-selects its source: if the
`downloads/` folder already has an activity dated today, it reuses local FIT
files (offline, fast); otherwise it downloads the window's activities online from
Garmin CN in memory. This trades the earlier strict-offline stance for
always-current results, and means the online path requires CN credentials.
_Alternative:_ always online (simpler, but slower and needs credentials every
run) or always offline (fast, but silently stale) — the hybrid gets the best of
both with a today's-file freshness check.

**7. Module & CLI layout.**
New `garmin/training_load.py` holding pure functions (`activity_load`,
`aggregate_daily_load`, `rolling_metrics`, `acwr`, `recommend`) + a
`TrainingLoadMixin`/directory batch helper mirroring `laps.py`. Wire a `readiness`
subcommand in `cli/parser.py`, a handler in `cli/commands.py`, a
`format_readiness_report` in `cli/reporting.py`, and exports in
`garmin/__init__.py`. HR params added to `garmin/config.py` (`AthleteProfile`:
resting HR, max HR, sex, optional age) read from new `env` keys with CLI overrides.

## Risks / Trade-offs

- **[TRIMP needs accurate HR params]** → Wrong resting/max HR skews all scores.
  Mitigation: require max HR (or age to estimate) and document defaults in README;
  fail loud when unavailable rather than fabricating a score.
- **[Mixed-sport dataset]** → Strength/swim/elliptical FITs may lack or misreport
  HR. Mitigation: spec requires no-HR activities to contribute zero and never
  break the batch; load is intensity-agnostic across sports (HR-only), which is
  acceptable for a train/rest signal.
- **[Short history at range start]** → EWMA/ACWR are unreliable until ~42 days of
  data precede the first reported day. Mitigation: seed the series from earlier
  files when present and note a "warm-up" caveat in the report for short ranges.
- **[Threshold tuning is subjective]** → Recommendation bands are heuristic.
  Mitigation: constants are named and unit-tested; easy to adjust without touching
  the math.
- **[Filename-date trust]** → Non-conforming filenames would be skipped.
  Mitigation: same assumption the working `laps` command already relies on.

## Open Questions

- Default max-HR estimate when only age is known: `208 − 0.7·age` (Tanaka) vs the
  classic `220 − age`? Leaning Tanaka; confirm during implementation.
- Should the report optionally emit a small daily CSV/series for later plotting,
  or stay text-only for this change? (Currently scoped text-only.)
