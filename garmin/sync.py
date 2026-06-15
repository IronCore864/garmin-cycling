"""Sync the latest activities from one Garmin account to another."""

from __future__ import annotations

import logging
import os
import tempfile

from ._fit import extract_fit_bytes

logger = logging.getLogger("garmin")

DEFAULT_ACTIVITIES_NUM = 3


class SyncMixin:
    """Sync activities from this account to another Garmin account."""

    def sync_latest_to(
        self,
        target_client,
        activities_num: int = DEFAULT_ACTIVITIES_NUM,
    ) -> list[dict]:
        """Download this account's latest activities and upload to another.

        Typically used to sync Garmin CN activities to Garmin Global.

        Args:
            target_client: Logged-in GarminClient to upload to (e.g. Global).
            activities_num: Number of most-recent activities to sync.

        Returns:
            A list of per-activity result dicts with status/detail.
        """
        logger.info("Fetching latest %d activities from source...", activities_num)
        activities = self.get_latest_activities(0, activities_num)

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
                logger.info("Downloading activity %s from source...", activity_id)
                activity_bytes = self.download_activity(activity_id, fmt="fit")
                fit_bytes = extract_fit_bytes(activity_bytes)
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
                with tempfile.NamedTemporaryFile(
                    delete=False, suffix=".fit"
                ) as tmpfile:
                    tmpfile.write(fit_bytes)
                    tmpfilepath = tmpfile.name
                logger.info("Uploading activity %s to target...", activity_id)
                with open(tmpfilepath, "rb") as fp:
                    target_client.upload(fp)
                result["status"] = "synced"
                result["detail"] = "Synced successfully."
            except Exception as exc:  # noqa: BLE001
                text = str(exc).lower()
                if "conflict" in text or "409" in text:
                    result["status"] = "exists"
                    result["detail"] = "Activity already exists on target."
                else:
                    result["status"] = "error"
                    result["detail"] = str(exc)
            finally:
                if tmpfilepath and os.path.isfile(tmpfilepath):
                    os.remove(tmpfilepath)

            results.append(result)

        return results
