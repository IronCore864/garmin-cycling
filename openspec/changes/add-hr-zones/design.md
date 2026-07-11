## Context

The user supplied a concrete `zones.py` implementation that computes five HR
zones as integer-truncated percentages of FTHR (Z1 ≤81%, Z2 ≤89%, Z3 ≤93%,
Z4 ≤99%, Z5 above), with contiguous boundaries and an open-ended Zone 5. This
change adopts that logic as the source of truth. The module is pure arithmetic
with no I/O, matching the offline, dependency-light style of existing helpers
like `garmin/_utils.py`.

## Goals / Non-Goals

**Goals:**
- Implement `calculate_zones(fthr)` exactly per the supplied logic and shape
  (`list[dict]` with `zone`, `start`, `end`).
- Provide a readable table formatter for the zones.
- Validate input type (`TypeError` on non-numeric FTHR).
- Full unit coverage of boundaries, contiguity, Zone 5 open end, and errors.

**Non-Goals:**
- No zone-based load or time-in-zone computation (future work; may build on this).
- No auto-detection/estimation of FTHR — the value is an explicit input.
- No power or pace zones; heart-rate only.
- No CLI command in this change unless trivially wired via existing reporting.

## Decisions

**1. Adopt the supplied algorithm verbatim.**
Percentage constants (81/89/93/99) and `end = int((pct/100)×fthr)` truncation are
kept as given so results match the user's prior tooling. Truncation (`int()`)
rather than rounding is intentional and specified.

**2. Contiguous boundaries via running start.**
Each zone's `start = previous end + 1`; Zone 5's `end` is the string `">{start}"`.
This preserves the exact output contract other code/tests may depend on.

**3. Keep the `list[dict]` return shape.**
Rather than introduce a dataclass, retain the dict shape from the supplied code
to stay drop-in compatible. A typed wrapper can be added later if needed.

**4. Module placement.**
Add as `garmin/zones.py` (pure helper) and export `calculate_zones` +
the formatter from `garmin/__init__.py`, consistent with how other pure helpers
are organized.

## Risks / Trade-offs

- **[Fixed Zone-1 lower bound of 91 bpm]** → `ZONE_1_START = 91` is independent of
  FTHR, so for low FTHR values Zone 1's `start` (91) can exceed its computed
  `end` (`int(0.81×fthr)`), producing an inverted/empty Zone 1. The supplied code
  comments this as "arbitrary, matches prior logic." Mitigation: spec and
  implement it as given for compatibility, but surface this in Open Questions for
  a decision on whether to make the lower bound FTHR-relative later.
- **[Truncation vs rounding]** → `int()` floors boundaries, so a zone end can sit
  1 bpm lower than a rounded value. Kept intentionally for parity; documented in
  the spec.
- **[Dict shape is stringly-typed for Zone 5 end]** → `end` is an int for zones
  1–4 but a string for Zone 5, which callers must handle. Documented; acceptable
  for drop-in parity.

## Open Questions

- Should the fixed 91 bpm Zone-1 lower bound become FTHR-relative (e.g. a
  percentage) to avoid inverted zones at low FTHR? Deferred — current change
  preserves the supplied behavior.
- Should zones be exposed via a dedicated CLI subcommand (e.g. `zones --fthr N`),
  or only as a library function for now? **Resolved:** a `zones --fthr N`
  subcommand is provided so the feature is usable from the CLI. FTHR is a
  required argument for now (an `env`/`GARMIN_FTHR` default could be added later).
