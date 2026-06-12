"""FastAPI application exposing only the /api/cron endpoint."""

import logging

from dotenv import load_dotenv

load_dotenv(override=True)

from fastapi import FastAPI

from garmin_lite.client import make_cn_client, make_global_client
from garmin_lite.config import load_config
from garmin_lite.sync import sync_latest

logging.basicConfig(level=logging.INFO)

app = FastAPI(
    title="Garmin FIT Lite API",
    description="Minimal Garmin sync API.",
)


@app.get("/api/cron")
def run_cron():
    """Sync the latest 3 activities from Garmin CN to Garmin Global."""
    try:
        config = load_config()
        cn_client = make_cn_client(config)
        global_client = make_global_client(config)
        result = sync_latest(cn_client, global_client, activities_num=3)
        return {"message": "Sync done.", "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
