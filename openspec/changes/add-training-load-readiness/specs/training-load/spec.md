## ADDED Requirements

### Requirement: Per-activity heart-rate training load

The system SHALL compute a single heart-rate–based training-load score (the
"relative effort" / "相对负荷度" value) for one activity from its FIT `record`
messages, using a Banister TRIMP model weighted by heart-rate reserve. The
computation MUST be pure and offline (no network access).

Heart-rate reserve for a sample MUST be computed as
`HRr = (HR − restingHR) / (maxHR − restingHR)`, clamped to `[0, 1]`. The
per-sample TRIMP contribution MUST use the standard exponential weighting
`duration_min × HRr × 0.64 × e^(k × HRr)`, where `k = 1.92` for male and
`k = 1.67` for female. The activity load MUST be the sum of per-sample
contributions, rounded to an integer.

#### Scenario: Activity with continuous HR data

- **WHEN** an activity's FIT records contain valid `timestamp` and `heart_rate`
  values and the athlete's resting HR, max HR and sex are provided
- **THEN** the system returns a positive integer training-load score computed by
  summing HR-reserve–weighted TRIMP over the elapsed sample intervals

#### Scenario: Higher intensity yields higher load

- **WHEN** two equal-duration activities are compared and one sustains a higher
  average heart rate
- **THEN** the higher-average-HR activity MUST receive a strictly greater
  training-load score

#### Scenario: Sample intervals drive duration weighting

- **WHEN** consecutive HR samples are separated by irregular time gaps
- **THEN** each sample's contribution MUST be weighted by the elapsed time since
  the previous sample (in minutes), not by a fixed per-sample constant

### Requirement: Heart-rate parameter configuration

The system SHALL obtain resting HR, max HR and sex from configuration
(the `env` file and/or environment variables), with optional CLI overrides taking
precedence. When max HR is not configured, the system MAY estimate it from age if
age is provided; otherwise load computation for HR-based scoring MUST report that
required parameters are missing rather than guessing silently.

#### Scenario: Parameters supplied via configuration

- **WHEN** resting HR, max HR and sex are present in configuration
- **THEN** the load computation uses those values without requiring CLI flags

#### Scenario: CLI override wins

- **WHEN** a max-HR value is provided both in configuration and as a CLI flag
- **THEN** the CLI flag value is used for the computation

#### Scenario: Missing required parameters

- **WHEN** neither max HR nor a means to derive it is available
- **THEN** the system reports that HR-based load cannot be computed and does not
  emit a fabricated score

### Requirement: Graceful handling of activities without heart rate

The system SHALL handle activities that contain no usable heart-rate data without
raising an error, reporting such activities as having no HR-based load so that
batch processing over mixed activity types can continue.

#### Scenario: Activity has no HR samples

- **WHEN** an activity's FIT records contain no `heart_rate` values
- **THEN** the system returns a "no HR data" result for that activity and
  processing of remaining activities continues
