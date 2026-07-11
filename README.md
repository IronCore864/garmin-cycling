# Garmin Cycling

Garmin Connect utilities focused on cycling. It provides a reusable
`garmin` package plus a few entry points:

- **`main.py`** — thin launcher for the unified CLI (implemented in the
  `cli` package) with five subcommands:
  - `sync`: full workflow — sync CN→Global, latest cycling VO2max,
    power/HR analytics, single-ride analysis (decoupling, critical power/W′,
    coasting), lake lap counting, and a past-month VO2max image.
  - `gear`: list a year's cycling activities grouped by gear (bike).
  - `laps`: count lake laps (circles) from downloaded FIT files in a date range.
  - `download`: bulk-download activities in a date range as FIT/TCX.
  - `analyze`: analyze a single local FIT file offline — aerobic decoupling
    (Pw:Hr) + efficiency factor, critical power / W′ + rider phenotype, and a
    coasting/pedaling breakdown.
- **`app.py`** — FastAPI app exposing `GET /api/cron`, which syncs the latest
  3 activities from Garmin CN to Garmin Global.

## The `garmin` package

Organised by functionality rather than one large class:

```
garmin/
├── __init__.py     # public exports
├── _base.py        # BaseClient: auth + low-level connectapi/download/upload
├── _utils.py       # shared date + filename helpers
├── _fit.py         # FIT archive helpers (extract/write), shared by modules
├── activities.py   # ActivitiesMixin: list + download activities (+ to-dir)
├── analytics.py    # AnalyticsMixin: max average power + HR by duration
├── power.py        # single-FIT analysis: decoupling/EF, critical power/W′, coasting
├── gear.py         # GearMixin + GearActivity/GearReport (rides grouped by bike)
├── vo2.py          # VO2Mixin + cycling VO2max plotting
├── laps.py         # Lake value object + lake lap (circle) counting from GPS
├── sync.py         # CN -> Global activity sync
├── config.py       # credential configuration
├── workflow.py     # combined sync + analysis workflow
└── client.py       # composed GarminClient + login factories
```

`GarminClient` composes the endpoint groups, so a single instance exposes
`get_activities`, `download_activity`, `get_gear`, `get_vo2max`, etc. Each
client owns its own `garth` session, so multiple accounts (CN + Global) can
be used at the same time.

## The `cli` package

The terminal frontend is separated from the library, so `main.py` stays a
trivial launcher and the parsing/handling/presentation each have a home:

```
cli/
├── __init__.py   # main(): build the parser and dispatch to a subcommand
├── parser.py     # argparse wiring (build_parser)
├── commands.py   # one handler per subcommand (sync/gear/laps/download/analyze)
└── reporting.py  # plain-text report formatters (workflow/gear/laps/ride analysis)
```

## Configuration

Credentials are read from the `env` file (repo root) and/or environment
variables. Environment variables take precedence.

| Variable                 | Description                          |
| ------------------------ | ------------------------------------ |
| `GARMIN_CN_EMAIL`        | Garmin CN account email              |
| `GARMIN_CN_PASSWORD`     | Garmin CN password                   |
| `GARMIN_GLOBAL_EMAIL`    | Garmin Global email (sync only)      |
| `GARMIN_GLOBAL_PASSWORD` | Garmin Global password (sync only)   |
| `GARMIN_RESTING_HR`      | Resting HR in bpm (`readiness` load) |
| `GARMIN_MAX_HR`          | Max HR in bpm (`readiness` load)     |
| `GARMIN_SEX`             | `male` or `female` (TRIMP weighting) |
| `GARMIN_AGE`             | Age; used to estimate max HR if unset|

The legacy `env` keys `username` / `password` are still accepted as aliases
for the Garmin CN account. The HR keys are only needed for the `readiness`
command (heart-rate training load); they can also be passed as CLI overrides.

Example `env`:

```
GARMIN_CN_EMAIL=you@example.com
GARMIN_CN_PASSWORD=...
GARMIN_GLOBAL_EMAIL=you@example.com
GARMIN_GLOBAL_PASSWORD=...
```

## Install

```bash
uv sync
```

## Run the CLI

```bash
uv run python main.py                  # show help (no default action)
uv run python main.py sync             # sync + analysis workflow
uv run python main.py sync --vo2max-image /tmp/vo2max.png
uv run python main.py gear             # this year's activities grouped by gear
uv run python main.py gear --year 2025
uv run python main.py laps             # lake laps from ./downloads (year to date)
uv run python main.py laps --year 2025
uv run python main.py laps --month 5 --dir downloads
uv run python main.py download --start 2026-04-22 --end 2026-06-12 --format fit
uv run python main.py readiness        # today's HR training load & train/rest advice
uv run python main.py readiness --max-hr 190 --resting-hr 48
uv run python main.py zones --fthr 165 # FTHR-based heart-rate training zones
uv run python main.py analyze --file downloads/2026-05-01_123_Ride.fit
uv run python main.py analyze --file downloads/2026-05-01_123_Ride.fit --weight 70
```

## Single-file ride analysis (`analyze`)

`analyze` works on one local FIT file, fully offline, and reports three things
Garmin Connect does not surface per ride:

- **Aerobic decoupling (Pw:Hr) + efficiency factor** — splits the ride in half
  and compares normalized-power-to-heart-rate between halves. Low decoupling
  (≤ 5%) indicates good aerobic durability.
- **Critical power / W′ + rider phenotype** — fits the 2-parameter
  critical-power model (`work = CP·t + W′`) to the ride's mean-maximal power
  curve to estimate sustainable power (CP) and anaerobic work capacity (W′),
  then labels a rough phenotype. Only meaningful when the ride contains
  near-maximal efforts across the 2–20 min range.
- **Coasting / pedaling breakdown** — moving vs stopped time, and how much of
  the moving time was spent freewheeling versus pedaling.

Pass `--weight <kg>` to get CP in W/kg and a weight-aware phenotype. Sections
with insufficient data (e.g. no power meter) are reported as not available.

```
============================================================
Ride Analysis - 2026-05-01_123_Ride.fit
============================================================
Duration: 73.5 min  |  power: yes  |  HR: yes

Aerobic decoupling (Pw:Hr):
  Efficiency factor (NP/HR): 1.72 (NP 218 W / HR 127 bpm)
  First half: 1.780 W/bpm   Second half: 1.690 W/bpm
  Decoupling: 4.8% (coupled; <= 5% indicates good aerobic durability)

Critical power model (single-ride estimate):
  CP: 256 W (3.66 W/kg)   W': 18.4 kJ
  Fit: r2=0.992 over 7 efforts (2-20 min)
  Phenotype: All-rounder
  Note: only meaningful if the ride included hard efforts across these durations.

Coasting / pedaling:
  Moving: 68.2 min   Stopped: 5.3 min
  Pedaling: 60.9 min (89.4%)   Coasting: 7.2 min (10.6%)
  Longest coast: 95 s
============================================================
```

## Run the sync API

```bash
uv run uvicorn app:app --host 0.0.0.0 --port 8000
# then:
curl http://localhost:8000/api/cron
```

## Development

Dev dependencies (pytest) install with the project via `uv sync`.

```bash
uv run pytest          # run the unit tests (or: make test)
make lint              # ruff check . (lint)
make fmt               # ruff check --fix . (lint + import sorting)
```

Ruff and pytest are configured in `pyproject.toml`. The tests cover the pure
logic (date/filename helpers, FIT extraction, lake-lap geometry/winding, gear
grouping, config loading, single-ride power analysis — decoupling, critical
power and coasting — and report formatting) and need no network access.
