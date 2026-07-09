## ADDED Requirements

### Requirement: FTHR-based zone boundary calculation

The system SHALL calculate five heart-rate zones from a Functional Threshold
Heart Rate (FTHR), returning for each zone its number and its `start`/`end`
boundaries in bpm. Zone upper bounds MUST be derived as integer-truncated
percentages of FTHR: Zone 1 ≤ 81%, Zone 2 ≤ 89%, Zone 3 ≤ 93%, Zone 4 ≤ 99%,
using `end = int((pct/100) × fthr)`. Zone 5 covers everything above Zone 4's end.

#### Scenario: Zones computed for a numeric FTHR

- **WHEN** `calculate_zones(fthr)` is called with a valid numeric FTHR
- **THEN** it returns five entries (zones 1–5), each with a `zone` number and
  `start`/`end` values, where zones 1–4 end at `int((81|89|93|99 / 100) × fthr)`
  respectively

#### Scenario: Percentage thresholds are truncated to whole bpm

- **WHEN** a percentage of FTHR is not a whole number
- **THEN** the zone end is the integer floor of that value (no rounding up)

### Requirement: Contiguous zone boundaries

The system SHALL make zones contiguous: each zone's `start` MUST be exactly one
bpm greater than the previous zone's `end`, and Zone 1's `start` MUST be the
fixed lower bound (91 bpm, matching the prior logic).

#### Scenario: Adjacent zones do not overlap or gap

- **WHEN** zones are returned for any valid FTHR
- **THEN** for each zone n>1, `start(n) == end(n-1) + 1`, and `start(1) == 91`

### Requirement: Open-ended top zone

The system SHALL represent Zone 5 as open-ended, with a numeric `start` one bpm
above Zone 4's end and an `end` expressed as the string `">{start}"`.

#### Scenario: Zone 5 has no upper bound

- **WHEN** zones are returned for any valid FTHR
- **THEN** Zone 5's `start` equals `end(zone 4) + 1` and its `end` is the string
  `">"` followed by that start value

### Requirement: Input validation

The system SHALL raise `TypeError` when the provided FTHR is not an `int` or
`float`.

#### Scenario: Non-numeric FTHR rejected

- **WHEN** `calculate_zones` is called with a non-numeric value (e.g. a string)
- **THEN** a `TypeError` is raised with a message indicating FTHR must be a number

### Requirement: Human-readable zone table

The system SHALL format the calculated zones into a human-readable table showing
each zone number and its bpm range, with Zone 5 shown as an open-ended range.

#### Scenario: Format zones for display

- **WHEN** the formatter is given the output of `calculate_zones`
- **THEN** it returns a text table with one row per zone (1–5) listing the zone
  number and its `start`–`end` bpm range (Zone 5 shown as `>N`)

### Requirement: Zones CLI command

The system SHALL expose zone calculation through a `zones` CLI subcommand that
takes an FTHR value and prints the formatted zone table. A non-numeric or missing
FTHR MUST produce a clear error message rather than an unhandled traceback.

#### Scenario: Show zones for an FTHR

- **WHEN** the user runs the `zones` command with `--fthr <value>`
- **THEN** the command prints the five FTHR-based zones as a readable table
