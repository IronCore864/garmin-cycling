"""Gear (bike) endpoints and aggregated gear stats."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from ._utils import activity_in_range, parse_date


@dataclass(frozen=True)
class GearActivity:
    """A cycling activity summarised for per-gear reporting."""

    id: int | str | None
    name: str
    date: str
    distance_km: float
    duration_min: float
    avg_speed_kmh: float

    @classmethod
    def from_activity(cls, activity: dict[str, Any]) -> GearActivity:
        """Build a :class:`GearActivity` from a raw Garmin activity dict."""
        distance_m = activity.get("distance", 0) or 0
        duration_s = activity.get("duration", 0) or 0
        return cls(
            id=activity.get("activityId"),
            name=activity.get("activityName", "Unnamed"),
            date=activity.get("startTimeLocal", ""),
            distance_km=round(distance_m / 1000, 2) if distance_m else 0,
            duration_min=round(duration_s / 60, 1) if duration_s else 0,
            avg_speed_kmh=(
                round((distance_m / 1000) / (duration_s / 3600), 1)
                if duration_s and distance_m
                else 0
            ),
        )


@dataclass(frozen=True)
class GearReport:
    """A year's cycling activities grouped by the gear (bike) used."""

    year: int
    by_gear: dict[str, list[GearActivity]]
    no_gear: list[GearActivity]

    @property
    def groups(self) -> list[list[GearActivity]]:
        """All activity groups, including the no-gear bucket."""
        return list(self.by_gear.values()) + [self.no_gear]

    @property
    def total_rides(self) -> int:
        return sum(len(group) for group in self.groups)

    @property
    def total_distance_km(self) -> float:
        return sum(a.distance_km for group in self.groups for a in group)

    @property
    def total_duration_min(self) -> float:
        return sum(a.duration_min for group in self.groups for a in group)


def _gear_name(gear: dict[str, Any]) -> str:
    """Best display name for a gear dict."""
    return gear.get("displayName") or gear.get("customMakeModel") or "Unknown Gear"


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

    def build_gear_report(
        self,
        year: int,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> GearReport:
        """Group a year's cycling activities by the gear (bike) used.

        Args:
            year: Calendar year to report on.
            on_progress: Optional callback invoked as ``(done, total)`` after
                each activity, so callers (e.g. a CLI) can show progress.

        Returns:
            A :class:`GearReport` with activities grouped per gear plus a
            no-gear bucket.
        """
        activities = self.get_activities(
            f"{year}-01-01", f"{year}-12-31", activity_type="cycling"
        )

        by_gear: dict[str, list[GearActivity]] = defaultdict(list)
        no_gear: list[GearActivity] = []
        total = len(activities)
        for i, activity in enumerate(activities, start=1):
            info = GearActivity.from_activity(activity)
            gear_list = self.get_activity_gear(info.id)
            if gear_list:
                for gear in gear_list:
                    by_gear[_gear_name(gear)].append(info)
            else:
                no_gear.append(info)
            if on_progress is not None:
                on_progress(i, total)

        return GearReport(year=year, by_gear=dict(by_gear), no_gear=no_gear)
