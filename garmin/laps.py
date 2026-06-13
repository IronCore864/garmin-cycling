"""Count laps (circles) around a lake for a Garmin activity."""

from __future__ import annotations

import io
import logging
import math
import zipfile

logger = logging.getLogger("garmin")

# Default lake: Xinglong Lake.
DEFAULT_LAKE_LATITUDE = 30.40111111111111
DEFAULT_LAKE_LONGITUDE = 104.0861111111111
DEFAULT_LAKE_RADIUS_M = 2000.0

_EARTH_RADIUS_M = 6371000
_MIN_SEGMENT_POINTS = 12
_SEMI_TO_DEG = 180.0 / (2**31)
# Ignore activities whose start is farther than this from the lake.
_MAX_START_DISTANCE_M = 100000


def _haversine(lat1, lon1, lat2, lon2) -> float:
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _extract_fit_bytes(activity_bytes: bytes) -> bytes | None:
    with zipfile.ZipFile(io.BytesIO(activity_bytes)) as zipf:
        for fname in zipf.namelist():
            if fname.endswith(".fit"):
                with zipf.open(fname) as fit_file:
                    return fit_file.read()
    return None


def _parse_points(fitfile):
    import numpy as np

    lats, lons = [], []
    for record in fitfile.get_messages("record"):
        lat = lon = None
        for field in record.fields:
            if field.name == "position_lat" and field.value is not None:
                lat = field.value * _SEMI_TO_DEG
            elif field.name == "position_long" and field.value is not None:
                lon = field.value * _SEMI_TO_DEG
        if lat is not None and lon is not None:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return np.empty((0, 2), dtype=np.float64)
    return np.column_stack([lats, lons])


def _winding_number(points, center) -> int:
    import numpy as np

    dy = points[:, 0] - center[0]
    dx = points[:, 1] - center[1]
    angles = np.arctan2(dy, dx)
    d = np.diff(angles)
    d = (d + np.pi) % (2.0 * np.pi) - np.pi
    return int(np.round(d.sum() / (2.0 * np.pi)))


def _count_circles(points, lake_center, lake_radius_km: float) -> int:
    import numpy as np

    if len(points) < _MIN_SEGMENT_POINTS:
        return 0

    center = np.array(lake_center, dtype=np.float64)
    cos_lat = np.cos(np.radians(center[0]))
    dlat_km = (points[:, 0] - center[0]) * 111.0
    dlon_km = (points[:, 1] - center[1]) * 111.0 * cos_lat
    dist_km = np.sqrt(dlat_km**2 + dlon_km**2)

    near = dist_km < lake_radius_km * 3.0
    if near.sum() < _MIN_SEGMENT_POINTS:
        return 0

    padded = np.empty(len(near) + 2, dtype=bool)
    padded[0] = False
    padded[-1] = False
    padded[1:-1] = near
    edges = np.diff(padded.view(np.uint8).astype(np.int8))
    starts = np.where(edges == 1)[0]
    ends = np.where(edges == -1)[0]

    total = 0
    for s, e in zip(starts, ends):
        if e - s < _MIN_SEGMENT_POINTS:
            continue
        total += abs(_winding_number(points[s:e], center))
    return total


class LapsMixin:
    """Lake lap (circle) counting from activity GPS tracks."""

    def count_latest_activity_laps(
        self,
        lake_lat: float = DEFAULT_LAKE_LATITUDE,
        lake_lon: float = DEFAULT_LAKE_LONGITUDE,
        lake_radius_m: float = DEFAULT_LAKE_RADIUS_M,
    ) -> int:
        """Download the latest activity and count laps (circles) around a lake.

        Args:
            lake_lat: Lake center latitude.
            lake_lon: Lake center longitude.
            lake_radius_m: Approximate lake radius in metres.

        Returns:
            The number of full circles detected (0 if the activity is far
            from the lake or has no GPS track).
        """
        import fitparse

        activities = self.get_latest_activities(0, 1)
        if not activities:
            logger.warning("No activities found to count laps.")
            return 0

        activity_id = activities[0].get("activityId")
        activity_bytes = self.download_activity(activity_id, fmt="fit")

        fit_bytes = _extract_fit_bytes(activity_bytes)
        if not fit_bytes:
            logger.warning("No .fit file in latest activity archive.")
            return 0

        fitfile = fitparse.FitFile(io.BytesIO(fit_bytes))
        points = _parse_points(fitfile)
        if len(points) == 0:
            return 0

        start_lat, start_lon = points[0]
        if (
            _haversine(start_lat, start_lon, lake_lat, lake_lon)
            > _MAX_START_DISTANCE_M
        ):
            logger.info("Latest activity starts far from the lake; counting 0 laps.")
            return 0

        return _count_circles(points, (lake_lat, lake_lon), lake_radius_m / 1000.0)
