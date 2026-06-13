"""FastAPI application exposing only the /api/cron endpoint."""

import logging

from garmin.client import make_cn_client, make_global_client
from garmin.config import load_config

logging.basicConfig(level=logging.INFO)

try:
    from fastapi import FastAPI
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "FastAPI is required to run the API. Install with: pip install fastapi uvicorn"
    ) from exc

app = FastAPI(
    title="Garmin Cycling API",
    description="Minimal Garmin sync API.",
)


@app.get("/api/cron")
def run_cron():
    """Sync the latest 3 activities from Garmin CN to Garmin Global."""
    try:
        config = load_config()
        cn_client = make_cn_client(config)
        global_client = make_global_client(config)
        result = cn_client.sync_latest_to(global_client, activities_num=3)
        return {"message": "Sync done.", "result": result}
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
