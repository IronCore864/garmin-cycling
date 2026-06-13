# Garmin Cycling

Garmin Connect utilities focused on cycling. It provides a reusable
`garmin` package plus a few entry points:

- **`main.py`** — unified CLI with three subcommands:
  - `sync`: full workflow — sync CN→Global, latest cycling VO2max,
    power/HR analytics, lake lap counting, and a past-month VO2max image.
  - `gear`: list a year's cycling activities grouped by gear (bike).
  - `download`: bulk-download activities in a date range as FIT/TCX.
- **`app.py`** — FastAPI app exposing `GET /api/cron`, which syncs the latest
  3 activities from Garmin CN to Garmin Global.

## The `garmin` package

Organised by functionality rather than one large class:

```
garmin/
├── __init__.py     # public exports
├── _base.py        # BaseClient: auth + low-level connectapi/download/upload
├── _utils.py       # shared date helpers
├── activities.py   # ActivitiesMixin: list + download activities
├── gear.py         # GearMixin: gear (bike) endpoints + stats
├── vo2.py          # VO2Mixin + cycling VO2max plotting
├── laps.py         # lake lap (circle) counting from FIT GPS tracks
├── sync.py         # CN -> Global activity sync
├── config.py       # credential configuration
├── workflow.py     # combined sync + analysis workflow
└── client.py       # composed GarminClient + login factories
```

`GarminClient` composes the endpoint groups, so a single instance exposes
`get_activities`, `download_activity`, `get_gear`, `get_vo2max`, etc. Each
client owns its own `garth` session, so multiple accounts (CN + Global) can
be used at the same time.

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
uv run python main.py download --start 2026-04-22 --end 2026-06-12 --format fit
```

## Run the sync API

```bash
uv run uvicorn app:app --host 0.0.0.0 --port 8000
# then:
curl http://localhost:8000/api/cron
```
