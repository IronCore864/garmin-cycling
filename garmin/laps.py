"""Count laps (circles) around a lake from a Garmin activity's GPS track.

The public surface is:

* :class:`Lake` / :data:`DEFAULT_LAKE` -- the lake to count circuits of.
* :func:`count_circles` -- circles for an array of GPS points.
* :func:`count_fit_laps` -- circles for a parsed ``fitparse.FitFile``.
* :func:`count_laps_in_directory` -- batch-count a folder of FIT files.
* :class:`LapsMixin` -- ``count_latest_activity_laps`` on a client.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path

from ._fit import extract_fit_bytes

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


@dataclass(frozen=True)
class Lake:
    """A circular lake to count circuits around.

    Bundles what were previously three loose values (latitude, longitude and
    radius) into one cohesive, immutable value object.
    """

    latitude: float
    longitude: float
    radius_m: float = DEFAULT_LAKE_RADIUS_M

    @property
    def center(self) -> tuple[float, float]:
        """The lake centre as a ``(latitude, longitude)`` pair."""
        return (self.latitude, self.longitude)

    @property
    def radius_km(self) -> float:
        """The lake radius in kilometres."""
        return self.radius_m / 1000.0


DEFAULT_LAKE = Lake(
    DEFAULT_LAKE_LATITUDE, DEFAULT_LAKE_LONGITUDE, DEFAULT_LAKE_RADIUS_M
)


@dataclass(frozen=True)
class LapResult:
    """Lap count for a single FIT file discovered on disk."""

    date: str
    file: str
    laps: int


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two lat/lon points, in metres."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return _EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_points(fitfile):
    """Extract an ``(N, 2)`` array of ``(lat, lon)`` degrees from a FIT file."""
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
    """Signed number of full turns ``points`` make around ``center``."""
    import numpy as np

    dy = points[:, 0] - center[0]
    dx = points[:, 1] - center[1]
    angles = np.arctan2(dy, dx)
    d = np.diff(angles)
    d = (d + np.pi) % (2.0 * np.pi) - np.pi
    return int(np.round(d.sum() / (2.0 * np.pi)))


def count_circles(points, lake: Lake = DEFAULT_LAKE) -> int:
    """Count full circuits an array of GPS points makes around ``lake``.

    Points are split into segments that stay near the lake (within three
    radii); the absolute winding number of each long-enough segment is summed.

    Args:
        points: ``(N, 2)`` array of ``(lat, lon)`` in degrees.
        lake: The lake to count circuits of.

    Returns:
        Total number of full circles detected.
    """
    import numpy as np

    if len(points) < _MIN_SEGMENT_POINTS:
        return 0

    center = np.array(lake.center, dtype=np.float64)
    cos_lat = np.cos(np.radians(center[0]))
    dlat_km = (points[:, 0] - center[0]) * 111.0
    dlon_km = (points[:, 1] - center[1]) * 111.0 * cos_lat
    dist_km = np.sqrt(dlat_km**2 + dlon_km**2)

    near = dist_km < lake.radius_km * 3.0
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
    for s, e in zip(starts, ends, strict=False):
        if e - s < _MIN_SEGMENT_POINTS:
            continue
        total += abs(_winding_number(points[s:e], center))
    return total


def count_fit_laps(fitfile, lake: Lake = DEFAULT_LAKE) -> int:
    """Count laps around ``lake`` for a parsed ``fitparse.FitFile``.

    Returns 0 when the track has no GPS points or starts farther than
    :data:`_MAX_START_DISTANCE_M` from the lake (i.e. a different ride).
    """
    points = _parse_points(fitfile)
    if len(points) == 0:
        return 0
    start_lat, start_lon = points[0]
    if _haversine(start_lat, start_lon, lake.latitude, lake.longitude) > (
        _MAX_START_DISTANCE_M
    ):
        return 0
    return count_circles(points, lake)


def count_laps_in_directory(
    directory: str | Path,
    start,
    end,
    lake: Lake = DEFAULT_LAKE,
) -> tuple[list[LapResult], int]:
    """Count laps for every FIT file in ``directory`` within a date range.

    Files are matched by a leading ``YYYY-MM-DD`` in their name (the naming
    convention produced by the ``download`` command). Unreadable files are
    skipped.

    Args:
        directory: Folder containing ``*.fit`` files.
        start: Inclusive start date (anything with ``.isoformat()``).
        end: Inclusive end date.
        lake: The lake to count circuits of.

    Returns:
        ``(results, scanned)`` where ``results`` holds one :class:`LapResult`
        per file with at least one lap, and ``scanned`` is the number of files
        considered.
    """
    import fitparse

    directory = Path(directory)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    fit_files = sorted(
        f
        for f in directory.glob("*.fit")
        if len(f.name) >= 10 and start_iso <= f.name[:10] <= end_iso
    )

    results: list[LapResult] = []
    for fp in fit_files:
        try:
            fitfile = fitparse.FitFile(str(fp))
            laps = count_fit_laps(fitfile, lake)
        except Exception:  # noqa: BLE001 -- skip any unreadable/corrupt file
            logger.debug("Skipping unreadable FIT file: %s", fp.name)
            continue
        if laps > 0:
            results.append(LapResult(date=fp.name[:10], file=fp.name, laps=laps))
    return results, len(fit_files)


class LapsMixin:
    """Lake lap (circle) counting from activity GPS tracks."""

    def count_latest_activity_laps(self, lake: Lake = DEFAULT_LAKE) -> int:
        """Download the latest activity and count laps around ``lake``.

        Args:
            lake: The lake to count circuits of (defaults to Xinglong Lake).

        Returns:
            The number of full circles detected (0 if the activity is far
            from the lake or has no GPS track).
        """
        import io

        import fitparse

        activities = self.get_latest_activities(0, 1)
        if not activities:
            logger.warning("No activities found to count laps.")
            return 0

        activity_id = activities[0].get("activityId")
        activity_bytes = self.download_activity(activity_id, fmt="fit")

        fit_bytes = extract_fit_bytes(activity_bytes)
        if not fit_bytes:
            logger.warning("No .fit file in latest activity archive.")
            return 0

        fitfile = fitparse.FitFile(io.BytesIO(fit_bytes))
        return count_fit_laps(fitfile, lake)
