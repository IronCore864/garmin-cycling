"""Shared workflow used by both the CLI script and the API /api/cron endpoint."""

import logging

from .client import make_cn_client, make_global_client
from .config import load_config
from .laps import count_latest_activity_laps
from .sync import sync_latest
from .vo2 import get_latest_cycling_vo2max, plot_monthly_vo2max

logger = logging.getLogger("garmin_lite")

DEFAULT_VO2MAX_IMAGE = "vo2max_past_month.png"


def run_workflow(vo2max_image_path: str = DEFAULT_VO2MAX_IMAGE) -> dict:
    """Run the full Garmin workflow and return a structured result.

    Steps:
      1. Sync the latest 3 activities from Garmin CN to Garmin Global.
      2. Fetch the latest cycling VO2max precise value.
      3. Count lake circles for the latest activity.
      4. Generate a cycling VO2max image for the past month.
    """
    config = load_config()
    cn_client = make_cn_client(config)
    global_client = make_global_client(config)

    result: dict = {
        "sync": None,
        "vo2max": None,
        "laps": None,
        "vo2max_image": None,
        "errors": {},
    }

    logger.info("Step 1/4: Syncing latest activities CN -> Global...")
    try:
        result["sync"] = sync_latest(cn_client, global_client, activities_num=3)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Sync step failed.")
        result["errors"]["sync"] = str(exc)

    logger.info("Step 2/4: Fetching latest cycling VO2max...")
    try:
        result["vo2max"] = get_latest_cycling_vo2max(cn_client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("VO2max step failed.")
        result["errors"]["vo2max"] = str(exc)

    logger.info("Step 3/4: Counting lake circles for latest activity...")
    try:
        result["laps"] = count_latest_activity_laps(cn_client)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Laps step failed.")
        result["errors"]["laps"] = str(exc)

    logger.info("Step 4/4: Generating VO2max image for the past month...")
    try:
        result["vo2max_image"] = plot_monthly_vo2max(cn_client, vo2max_image_path)
    except Exception as exc:  # noqa: BLE001
        logger.exception("VO2max image step failed.")
        result["errors"]["vo2max_image"] = str(exc)

    if not result["errors"]:
        del result["errors"]
    return result
