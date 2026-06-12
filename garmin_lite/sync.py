"""Sync the latest activities from Garmin CN to Garmin Global."""

import io
import logging
import os
import tempfile
import zipfile

from garminconnect import Garmin

logger = logging.getLogger("garmin_lite")

DEFAULT_ACTIVITIES_NUM = 3


def _extract_fit_bytes(activity_bytes: bytes) -> bytes | None:
    zip_bytes = io.BytesIO(activity_bytes)
    with zipfile.ZipFile(zip_bytes) as zipf:
        for fname in zipf.namelist():
            if fname.endswith(".fit"):
                with zipf.open(fname) as fit_file:
                    return fit_file.read()
    return None


def sync_latest(
    cn_client: Garmin,
    global_client: Garmin,
    activities_num: int = DEFAULT_ACTIVITIES_NUM,
) -> list[dict]:
    """Download the latest activities from CN and upload them to Global.

    Returns a list of per-activity result dicts.
    """
    logger.info("Fetching latest %d activities from Garmin CN...", activities_num)
    activities = cn_client.get_activities(0, activities_num)

    results: list[dict] = []
    for activity in activities:
        activity_id = activity.get("activityId")
        result = {
            "activityId": activity_id,
            "activityName": activity.get("activityName"),
            "startTimeLocal": activity.get("startTimeLocal"),
            "status": None,
            "detail": None,
        }
        try:
            logger.info("Downloading activity %s from Garmin CN...", activity_id)
            activity_bytes = cn_client.download_activity(
                activity_id,
                dl_fmt=cn_client.ActivityDownloadFormat.ORIGINAL,
            )
            fit_bytes = _extract_fit_bytes(activity_bytes)
        except Exception as exc:  # noqa: BLE001
            result["status"] = "error"
            result["detail"] = f"Download failed: {exc}"
            results.append(result)
            continue

        if not fit_bytes:
            result["status"] = "error"
            result["detail"] = "No .fit file in archive."
            results.append(result)
            continue

        tmpfilepath = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".fit") as tmpfile:
                tmpfile.write(fit_bytes)
                tmpfilepath = tmpfile.name
            logger.info("Uploading activity %s to Garmin Global...", activity_id)
            global_client.upload_activity(tmpfilepath)
            result["status"] = "synced"
            result["detail"] = "Synced successfully."
        except Exception as exc:  # noqa: BLE001
            if "Conflict for url" in str(exc):
                result["status"] = "exists"
                result["detail"] = "Activity already exists on Garmin Global."
            else:
                result["status"] = "error"
                result["detail"] = str(exc)
        finally:
            if tmpfilepath and os.path.isfile(tmpfilepath):
                os.remove(tmpfilepath)

        results.append(result)

    return results
