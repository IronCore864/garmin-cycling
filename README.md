# Garmin Cycling

Garmin Connect utilities focused on cycling. It provides a reusable
`garmin` package plus a few entry points:

- **`main.py`** — thin launcher for the unified CLI (implemented in the
  `cli` package) with four subcommands:
  - `sync`: full workflow — sync CN→Global, latest cycling VO2max,
    power/HR analytics, lake lap counting, and a past-month VO2max image.
  - `gear`: list a year's cycling activities grouped by gear (bike).
  - `laps`: count lake laps (circles) from downloaded FIT files in a date range.
  - `download`: bulk-download activities in a date range as FIT/TCX.
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
├── commands.py   # one handler per subcommand (sync/gear/laps/download)
└── reporting.py  # plain-text report formatters (workflow/gear/laps)
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

The legacy `env` keys `username` / `password` are still accepted as aliases
for the Garmin CN account.

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
grouping, config loading, and report formatting) and need no network access.
