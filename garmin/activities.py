"""Activity listing and download endpoints."""

from __future__ import annotations

from datetime import date
from typing import Any

from ._utils import to_date_str


class ActivitiesMixin:
    """Activity-related Garmin Connect endpoints."""

    def get_activities(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch activities in a date range, with optional type filter.

        Args:
            start_date: Start date (YYYY-MM-DD or date object).
            end_date: End date inclusive. Defaults to today.
            activity_type: Optional filter, e.g. "cycling", "running",
                "swimming", "hiking", "walking", "multi_sport",
                "fitness_equipment", "other".

        Returns:
            List of activity dicts from Garmin Connect.
        """
        start_date = to_date_str(start_date)
        end_date = to_date_str(end_date) if end_date else date.today().isoformat()

        activities: list[dict[str, Any]] = []
        offset = 0
        limit = 20
        while True:
            params: dict[str, str] = {
                "startDate": start_date,
                "endDate": end_date,
                "start": str(offset),
                "limit": str(limit),
            }
            if activity_type:
                params["activityType"] = activity_type
            batch = self.connectapi(
                "/activitylist-service/activities/search/activities",
                params=params,
            )
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < limit:
                break
            offset += limit
        return activities

    def get_latest_activities(
        self,
        start: int = 0,
        limit: int = 20,
        activity_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch the most recent activities by offset/limit.

        Args:
            start: Starting offset where 0 is the most recent activity.
            limit: Number of activities to return.
            activity_type: Optional activity type filter.

        Returns:
            List of activity dicts from Garmin Connect.
        """
        params: dict[str, str] = {"start": str(start), "limit": str(limit)}
        if activity_type:
            params["activityType"] = activity_type
        result = self.connectapi(
            "/activitylist-service/activities/search/activities",
            params=params,
        )
        return result if result else []

    def download_activity(
        self,
        activity_id: int | str,
        fmt: str = "fit",
    ) -> bytes:
        """Download the original/exported file for an activity.

        Args:
            activity_id: The Garmin activity ID.
            fmt: Output format, either "fit" or "tcx".
                "fit" returns the original uploaded file (a ZIP archive
                that usually contains a single .fit file).
                "tcx" returns a TCX (XML) document.

        Returns:
            Raw bytes of the downloaded file.
        """
        fmt = fmt.lower()
        if fmt == "fit":
            path = f"/download-service/files/activity/{activity_id}"
        elif fmt == "tcx":
            path = f"/download-service/export/tcx/activity/{activity_id}"
        else:
            raise ValueError(f"Unsupported format: {fmt!r} (use 'fit' or 'tcx')")
        return self.download(path)
