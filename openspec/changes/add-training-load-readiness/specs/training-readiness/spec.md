## ADDED Requirements

### Requirement: Daily load aggregation over a fixed recent window

The system SHALL assess readiness over a fixed recent window ending today (the
lookback covers the rolling-metric needs, i.e. at least the 42-day fitness
constant), without requiring the user to specify dates. It MUST aggregate
per-activity training-load scores into a daily load series over that window,
summing the load of all activities on the same calendar day and treating days
with no activity (or activities lacking HR-based load) as zero load. Every day
in the window MUST appear in the series.

#### Scenario: Multiple activities on one day

- **WHEN** a day contains two activities with HR-based loads of 80 and 40
- **THEN** that day's aggregated load is 120

#### Scenario: Rest day with no activity

- **WHEN** a date in the window has no activities
- **THEN** that day's aggregated load is 0 and the day still appears in the series

### Requirement: Automatic data-source selection

The system SHALL choose its data source automatically so the result is always
current. If the local downloads directory already contains an activity dated
today, the system MUST reuse local FIT files for the window (offline). Otherwise
it MUST fetch the window's activities online from Garmin (downloaded in memory,
without requiring the user to pre-download files).

#### Scenario: Local data is up to date

- **WHEN** the downloads directory contains at least one activity file dated today
- **THEN** the system computes readiness from local files without going online

#### Scenario: Local data is stale or absent

- **WHEN** the downloads directory has no activity dated today
- **THEN** the system fetches the recent window online (in memory) to ensure the
  assessment reflects the latest activities

### Requirement: Rolling fitness, fatigue and form

The system SHALL compute, for each day in the series, an exponentially-weighted
**Fitness (CTL)** using a 42-day time constant, a **Fatigue (ATL)** using a 7-day
time constant, and **Form (TSB)** as the previous day's CTL minus ATL. These
values MUST be derived from the daily load series so that adding load raises
fatigue faster than fitness, and rest lowers fatigue faster than fitness.

#### Scenario: Sustained load builds fitness and fatigue

- **WHEN** a block of consecutive high-load days is processed
- **THEN** both CTL and ATL increase, and ATL increases faster than CTL

#### Scenario: Rest reduces fatigue and raises form

- **WHEN** several consecutive zero-load days follow a hard block
- **THEN** ATL falls faster than CTL and TSB (Form) rises

### Requirement: Acute-to-chronic workload ratio

The system SHALL compute the acute:chronic workload ratio (ACWR) as the ratio of
recent acute load to longer-term chronic load (for example 7-day acute over
28-day chronic average). When chronic load is zero the ratio MUST be reported as
undefined rather than dividing by zero.

#### Scenario: Balanced load

- **WHEN** acute and chronic loads are approximately equal
- **THEN** the reported ACWR is approximately 1.0

#### Scenario: Chronic load is zero

- **WHEN** chronic load over the window is zero
- **THEN** ACWR is reported as undefined and no division-by-zero error occurs

### Requirement: Train-vs-rest recommendation

The system SHALL map the latest day's Form (TSB) and ACWR to a discrete
recommendation of `rest`, `easy`, or `train` (with an optional `caution`
overload flag), accompanied by a short human-readable rationale. High fatigue
(strongly negative TSB) or an ACWR above the high-risk threshold MUST bias the
recommendation toward rest/easy; fresh form within a safe ACWR range MUST allow
`train`.

#### Scenario: Deep fatigue recommends rest

- **WHEN** the latest TSB is strongly negative and/or ACWR exceeds the high-risk
  threshold
- **THEN** the recommendation is `rest` (or `easy`) and the rationale cites the
  fatigue/overload signal

#### Scenario: Fresh and balanced recommends training

- **WHEN** the latest TSB is neutral-to-positive and ACWR is within the safe range
- **THEN** the recommendation is `train` and the rationale cites adequate recovery

#### Scenario: Rapid load spike flags caution

- **WHEN** ACWR rises above the high-risk threshold even though TSB is not deeply
  negative
- **THEN** the result carries a caution/overload flag warning of injury risk

### Requirement: Readiness CLI command and report

The system SHALL expose the readiness analysis through a `readiness` CLI
subcommand that requires no date, directory, or window flags: it assesses the
current state over the fixed recent window and prints a plain-text report of the
recent load trend, the data source used, and today's recommendation. Optional
heart-rate override flags (resting HR, max HR, sex, age) MAY be accepted. When no
activities are available for the window (locally or online), the command MUST
print a clear "no data" message instead of failing.

#### Scenario: Default invocation

- **WHEN** the user runs `readiness` with no arguments
- **THEN** the command assesses the fixed recent window (selecting local or online
  data automatically) and prints the CTL/ATL/TSB and ACWR trend plus a dated
  train-vs-rest recommendation

#### Scenario: No activities available

- **WHEN** neither local files nor the online account yield activities in the
  window
- **THEN** the command prints a "no data" message and exits without error
