## 1. Core module

- [x] 1.1 Create `garmin/zones.py` with the FTHR percentage constants (Z1=81, Z2=89, Z3=93, Z4=99) and the fixed `ZONE_1_START = 91`.
- [x] 1.2 Implement `calculate_zones(fthr)` returning `list[dict]` with `zone`/`start`/`end`, using `end = int((pct/100)×fthr)`, contiguous `start = prev end + 1`, and Zone 5 `end = ">{start}"`.
- [x] 1.3 Raise `TypeError("FTHR must be a number.")` when `fthr` is not `int`/`float`.

## 2. Formatting

- [x] 2.1 Implement a table formatter that renders the zones as readable text (one row per zone, bpm range, Zone 5 shown as `>N`).
- [x] 2.2 Export `calculate_zones` and the formatter from `garmin/__init__.py`.

## 3. CLI

- [x] 3.1 Add a `zones --fthr N` subcommand (parser + `run_zones` handler) that prints the formatted zone table and handles bad FTHR gracefully.

## 4. Tests & verification

- [x] 4.1 Unit-test boundary values for a representative FTHR (zones 1–4 ends equal `int((81|89|93|99)/100 × fthr)`).
- [x] 4.2 Unit-test truncation behavior (fractional percentage floors, not rounds).
- [x] 4.3 Unit-test contiguity (`start(n) == end(n-1)+1`, `start(1) == 91`) and Zone 5 open-ended `">{start}"`.
- [x] 4.4 Unit-test `TypeError` on non-numeric FTHR.
- [x] 4.5 Unit-test the formatter output shape (five rows, Zone 5 open-ended).
- [x] 4.6 Run `make lint` and `uv run pytest`; fix any failures.
