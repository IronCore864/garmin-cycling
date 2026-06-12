# Garmin FIT Lite

A minimal, database-free rewrite of the Garmin FIT utilities app. It has two parts:

1. **A script** (`script.py`) that runs the full workflow.
2. **An API** (`app.py`) that exposes a single endpoint: `GET /api/cron`, which
   only syncs the latest 3 activities from Garmin CN to Garmin Global.

All configuration comes from environment variables — only Garmin CN and Garmin
Global credentials are needed. There is no database.

## Script workflow

The **script** runs all of these steps:

1. Sync the latest **3** activities from Garmin CN to Garmin Global.
2. Fetch the latest cycling **VO2max precise value** (today → yesterday →
   nearest earlier day within the past month).
3. Count **lake circles** for the latest activity (default lake: Xinglong Lake).
4. Generate a cycling **VO2max image** for the past month.

## API

The **API** exposes only `GET /api/cron`, which performs **step 1 only**:
syncing the latest 3 activities from Garmin CN to Garmin Global.

## Configuration

Set these environment variables (see `.env.example`):

| Variable                | Description              |
| ----------------------- | ------------------------ |
| `GARMIN_CN_EMAIL`       | Garmin CN account email  |
| `GARMIN_CN_PASSWORD`    | Garmin CN password       |
| `GARMIN_GLOBAL_EMAIL`   | Garmin Global email      |
| `GARMIN_GLOBAL_PASSWORD`| Garmin Global password   |

## Install

```bash
pip install -e .
```

## Run the script

```bash
python script.py
# optional: choose the VO2max image output path
python script.py --vo2max-image /tmp/vo2max.png
```

## Run the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
# then:
curl http://localhost:8000/api/cron
```

## Project layout

```
garmin-fit-lite/
├── app.py                 # FastAPI app with only /api/cron
├── script.py              # CLI entry point
├── garmin_lite/
│   ├── config.py          # env-var configuration
│   ├── client.py          # Garmin CN/Global client login helpers
│   ├── sync.py            # CN -> Global activity sync
│   ├── vo2.py             # cycling VO2max fetch + monthly plot
│   ├── laps.py            # lake lap (circle) counting
│   └── workflow.py        # shared workflow used by script + API
└── garminconnect/         # reused Garmin Connect API wrapper
```
