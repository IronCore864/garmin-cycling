## Why

Heart-rate–based analysis in this repo has no notion of training zones, so ride
data can't be labeled by intensity (endurance vs threshold vs VO2max). Zones
derived from Functional Threshold Heart Rate (FTHR) give a personalized,
widely-used framework for that, and are a prerequisite for zone-based load and
time-in-zone reporting.

## What Changes

- Add an FTHR-based **heart-rate zone calculation** that returns the five
  zones with their bpm `start`/`end` boundaries, using the supplied percentage
  thresholds of FTHR (Z1 ≤81%, Z2 ≤89%, Z3 ≤93%, Z4 ≤99%, Z5 above FTHR).
- Add human-readable **table formatting** of those zones.
- Boundaries are contiguous (each zone starts one bpm above the previous zone's
  end); Zone 5 is open-ended (`>N`).
- Input validation: a non-numeric FTHR raises `TypeError`.

## Capabilities

### New Capabilities
- `hr-zones`: Calculate the five FTHR-based heart-rate zone boundaries (in bpm)
  from a given FTHR, and format them into a readable table. Pure/offline, no
  external inputs beyond the FTHR value.

### Modified Capabilities
<!-- None: no existing specs under openspec/specs/. -->

## Impact

- **New code**: a `zones.py` module exposing `calculate_zones(fthr)` and a table
  formatter; public export from `garmin/__init__.py` (or a CLI reporting hook).
- **Dependencies**: none (pure Python arithmetic).
- **Related**: complements the pending `add-training-load-readiness` change
  (both are HR-based); zones can later feed time-in-zone / zone-weighted load,
  but this change is self-contained.
- **Tests**: unit tests for boundary math, contiguity, Zone 5 open end, and the
  `TypeError` path.
