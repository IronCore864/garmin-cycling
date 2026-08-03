# Garmin Cycling

Garmin Connect utilities focused on cycling. It provides a reusable
`garmin` package plus a few entry points:

- **`main.py`** — thin launcher for the unified CLI (implemented in the
  `cli` package) with subcommands:
  - `sync`: full workflow — sync CN→Global, latest cycling VO2max,
    power/HR analytics, single-ride analysis (decoupling, critical power/W′,
    coasting), lake lap counting, and a past-month VO2max image.
  - `gear`: list cycling activities grouped by gear (bike) for a year or a
    date range.
  - `laps`: count lake laps (circles) from downloaded FIT files in a date range.
  - `heatmap`: render a Strava-style route heatmap (HTML) from local FIT
    files, for all data, a given `--year`, or a single `--city` (matched
    geographically — see below).
  - `distance`: total ridden distance, optionally for one city (rides that
    *start* within a radius of the city centre). Uses the Garmin API by
    default (fast); `--local` totals local FIT files instead.
  - `download`: bulk-download activities in a date range as FIT/TCX,
    skipping any already present in the output directory (use `--force` to
    re-download).
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
├── badges.py       # BadgesMixin + earned-badge poster rendering
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
uv run python main.py gear --start 2025-09-13            # from a date to today
uv run python main.py gear --start 2025-09-13 --end 2025-12-13
uv run python main.py laps             # lake laps from ./downloads (year to date)
uv run python main.py laps --year 2025
uv run python main.py laps --month 5 --dir downloads
uv run python main.py heatmap          # route heatmap of all local FIT files
uv run python main.py heatmap --year 2026
uv run python main.py heatmap --city Chengdu             # -> chengdu.html
uv run python main.py heatmap --city 成都 --radius 80    # rides starting <=80km from Chengdu
uv run python main.py heatmap --city Chengdu --year 2026 # -> chengdu_2026.html
uv run python main.py download --start 2026-04-22 --end 2026-06-12 --format fit
uv run python main.py download --all    # skips activities already in ./downloads
uv run python main.py download --all --force  # re-download everything
uv run python main.py distance                 # total distance (all activities, via API)
uv run python main.py distance --city Chengdu  # km starting <=100km from Chengdu
uv run python main.py distance --city 成都 --year 2026 --radius 80
uv run python main.py distance --local         # total from local FIT files (offline)
uv run python main.py readiness        # today's HR training load & train/rest advice
uv run python main.py readiness --max-hr 190 --resting-hr 48
uv run python main.py zones --fthr 165 # FTHR-based heart-rate training zones
uv run python main.py analyze --file downloads/2026-05-01_123_Ride.fit
uv run python main.py analyze --file downloads/2026-05-01_123_Ride.fit --weight 70
uv run python main.py badges            # poster of all earned Garmin badges
uv run python main.py badges --sort date --columns 20 --out my_badges.png
```

## Route heatmap (`heatmap`)

`heatmap` reads the GPS tracks from your local FIT files and draws them as
overlapping, semi-transparent polylines on a dark basemap — roads ridden
repeatedly light up, like a personal Strava heatmap. It runs fully offline
over the `download` output.

`--city` filters **geographically**, not by filename. The city name is
resolved to a centre coordinate and any activity whose track *starts* within
`--radius` km (default 100) of that centre is kept. This is far more reliable
than the old filename match: a Chengdu ride recorded as `天府大道` or `龙泉山`
has no "Chengdu" in its name but still starts inside the radius, so it is
included.

City names are resolved in this order:

1. A small built-in registry of common cities (English/pinyin and Chinese,
   e.g. `chengdu`, `成都`) — instant and offline.
2. A cached online lookup (OpenStreetMap Nominatim) for anything else; the
   result is cached under `~/.cache/garmin-cycling/geocode.json`, so each city
   only hits the network once. Pass `--no-geocode` to stay fully offline
   (built-in + cached only).

If a centre cannot be resolved at all, it falls back to the previous
case-insensitive name/pinyin substring match, so nothing breaks offline.

```bash
uv run python main.py heatmap                    # all local rides
uv run python main.py heatmap --year 2026        # one year
uv run python main.py heatmap --city Chengdu     # rides starting <=100km from Chengdu
uv run python main.py heatmap --city 成都 --radius 80
uv run python main.py heatmap --city Munich --no-geocode  # offline only
```

## Total distance (`distance`)

`distance` totals how far you've ridden, optionally for a single city using the
same geographic filter as `heatmap` (a ride counts for a city when it *starts*
within `--radius` km of the city centre, so `天府大道` / `龙泉山` rides count
for Chengdu).

By default it reads the Garmin activity list over the API — one paged request
that already carries each ride's distance and start coordinates, so there is no
file parsing and it returns in seconds. `--type` picks the activity type
(default `cycling`; pass an empty string for all types).

`--local` totals your downloaded FIT files instead (fully offline). That path
parses every FIT file, so it is slower, but the files are decoded in parallel
across CPU cores and progress is printed as it goes.

```bash
uv run python main.py distance                    # all cycling, via API
uv run python main.py distance --city Chengdu     # rides starting <=100km from Chengdu
uv run python main.py distance --city 成都 --year 2026 --radius 80
uv run python main.py distance --type ""          # all activity types
uv run python main.py distance --local            # from local FIT files (offline)
uv run python main.py distance --local --city Chengdu --year 2026
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

## Badges poster (`badges`)

`badges` fetches every badge you've earned on Garmin Connect and renders a
single poster image showing them all off. It downloads the official badge
artwork (cached under `~/.cache/garmin-cycling/badges`) and lays it out in a
grid over a dark gradient, with a header summarising your totals:

```
============================================================
Garmin Badges - Summary
============================================================
Total earned : 307 (counting repeats)
Unique       : 304
Total points : 490
Earned span  : 2020-10-31 -> 2026-07-06

Highest-value badges:
    8 pts  100-Mile Ride
    8 pts  Intense 300
    ...
============================================================
```

Repeatable badges earned more than once get an `xN` chip in the corner. Sort
the grid by `points` (default), `date`, or `category`, and tweak `--columns`
and `--res` (`mdpi`/`hdpi`/`xhdpi`/`xxhdpi`, default highest) as desired.

Two poster styles are available via `--style`:

- `grid` (default) — every badge at a uniform size in a tidy grid.
- `color` — badges arranged by their dominant colour along a bicycle
  outline (two wheels + frame, a single badge thick), so the machine sweeps
  across the spectrum from front to back.

```bash
uv run python main.py badges
uv run python main.py badges --style color --out badges_bike.png
uv run python main.py badges --sort date --columns 20 --out my_badges.png
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
