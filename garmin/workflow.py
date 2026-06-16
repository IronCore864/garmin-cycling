"""Shared workflow used by both the CLI script and the API endpoint."""

from __future__ import annotations

import logging

from .client import make_cn_client, make_global_client
from .config import load_config

logger = logging.getLogger("garmin")

DEFAULT_VO2MAX_IMAGE = "vo2max_past_month.png"


def run_workflow(vo2max_image_path: str = DEFAULT_VO2MAX_IMAGE) -> dict:
    """Run the full Garmin workflow and return a structured result.

    Steps:
      1. Sync the latest 3 activities from Garmin CN to Garmin Global.
      2. Fetch the latest cycling VO2max precise value.
      3. Compute power/HR analytics for the latest activity.
      4. Analyze the latest activity (decoupling, critical power/W', coasting).
      5. Count lake circles for the latest activity.
      6. Generate a cycling VO2max image for the past month.
    """
    config = load_config()
    cn_client = make_cn_client(config)
    global_client = make_global_client(config)

    result: dict = {
        "sync": None,
        "vo2max": None,
        "analytics": None,
        "ride_analysis": None,
        "laps": None,
        "vo2max_image": None,
        "errors": {},
    }

    logger.info("Step 1/6: Syncing latest activities CN -> Global...")
    try:
        result["sync"] = cn_client.sync_latest_to(global_client, activities_num=3)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sync step failed.")
        result["errors"]["sync"] = str(exc)

    logger.info("Step 2/6: Fetching latest cycling VO2max...")
    try:
        result["vo2max"] = cn_client.get_latest_cycling_vo2max()
    except Exception as exc:  # noqa: BLE001
        logger.exception("VO2max step failed.")
        result["errors"]["vo2max"] = str(exc)

    logger.info("Step 3/6: Computing power/HR analytics for latest activity...")
    try:
        result["analytics"] = cn_client.analyze_latest_activity()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analytics step failed.")
        result["errors"]["analytics"] = str(exc)

    logger.info("Step 4/6: Analyzing latest activity (decoupling, CP/W', coast)...")
    try:
        result["ride_analysis"] = cn_client.analyze_latest_ride()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ride analysis step failed.")
        result["errors"]["ride_analysis"] = str(exc)

    logger.info("Step 5/6: Counting lake circles for latest activity...")
    try:
        result["laps"] = cn_client.count_latest_activity_laps()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Laps step failed.")
        result["errors"]["laps"] = str(exc)

    logger.info("Step 6/6: Generating VO2max image for the past month...")
    try:
        result["vo2max_image"] = cn_client.plot_monthly_vo2max(vo2max_image_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("VO2max image step failed.")
        result["errors"]["vo2max_image"] = str(exc)

    if not result["errors"]:
        del result["errors"]
    return result
