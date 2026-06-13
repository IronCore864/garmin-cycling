"""Gear (bike) endpoints and aggregated gear stats."""

from __future__ import annotations

from datetime import date
from typing import Any

from ._utils import activity_in_range, parse_date


class GearMixin:
    """Gear-related Garmin Connect endpoints."""

    def get_gear(self) -> list[dict[str, Any]]:
        """Get all gear for the current user.

        Returns:
            List of gear dicts with keys like uuid, displayName,
            customMakeModel, gearTypePk, dateBegin, dateEnd, etc.
        """
        profile = self.connectapi("/userprofile-service/socialProfile")
        user_profile_pk = profile.get("profileId")
        if not user_profile_pk:
            raise RuntimeError("Could not determine user profile ID")
        result = self.connectapi(
            "/gear-service/gear/filterGear",
            params={"userProfilePk": str(user_profile_pk)},
        )
        return result if result else []

    def get_activity_gear(self, activity_id: int | str) -> list[dict[str, Any]]:
        """Get gear associated with a specific activity.

        Args:
            activity_id: The Garmin activity ID.

        Returns:
            List of gear dicts used in that activity.
        """
        result = self.connectapi(
            "/gear-service/gear/filterGear",
            params={"activityId": str(activity_id)},
        )
        return result if result else []

    def get_gear_activities(
        self,
        gear_uuid: str,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> list[dict[str, Any]]:
        """Get all activities where a specific gear was used.

        Args:
            gear_uuid: UUID of the gear.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            List of activity dicts. If start_date/end_date provided,
            results are filtered to that range.
        """
        result = self.connectapi(
            f"/activitylist-service/activities/{gear_uuid}/gear",
            params={"start": "0", "limit": "1000"},
        )
        activities = result if result else []

        if start_date or end_date:
            start_dt = parse_date(start_date) if start_date else date.min
            end_dt = parse_date(end_date) if end_date else date.max
            activities = [
                a for a in activities if activity_in_range(a, start_dt, end_dt)
            ]
        return activities

    def get_gear_stats(
        self,
        gear_uuid: str,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
    ) -> dict[str, Any]:
        """Get aggregated stats for a gear (total km, hours, rides).

        Args:
            gear_uuid: UUID of the gear.
            start_date: Optional start date filter.
            end_date: Optional end date filter.

        Returns:
            Dict with keys: total_activities, total_distance_km,
            total_duration_hours, total_elevation_m.
        """
        activities = self.get_gear_activities(gear_uuid, start_date, end_date)
        total_distance = sum(a.get("distance", 0) for a in activities)
        total_duration = sum(a.get("duration", 0) for a in activities)
        total_elevation = sum(a.get("elevationGain", 0) for a in activities)
        return {
            "total_activities": len(activities),
            "total_distance_km": round(total_distance / 1000, 2),
            "total_duration_hours": round(total_duration / 3600, 2),
            "total_elevation_m": round(total_elevation, 1),
        }
