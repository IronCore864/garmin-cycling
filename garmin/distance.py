"""Total ridden distance from the Garmin activity list.

The activity list returned by the Garmin API already carries each ride's
``distance`` (metres) and its ``startLatitude`` / ``startLongitude``, so
totalling distance -- optionally for a single city -- needs no file parsing and
returns in seconds. This is intentionally online-only: distance is a quick,
authoritative query against the API, whereas the offline path (parsing local
FIT files) belongs to :mod:`garmin.heatmap`, which works over already-downloaded
activities.

An activity counts for a city when its start lies within a radius of the city
centre (the same geographic test :mod:`garmin.heatmap` uses to group rides).

The public surface is:

* :class:`DistanceReport` -- the aggregate ``(total_km, activities, scanned)``.
* :func:`distance_from_activities` -- sum distance from Garmin activity dicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .geo import haversine_m


@dataclass(frozen=True)
class DistanceReport:
    """Aggregate ridden distance over a set of activities."""

    total_km: float
    activities: int
    scanned: int


def distance_from_activities(
    activities: list[dict[str, Any]],
    center: tuple[float, float] | None = None,
    radius_km: float = 100.0,
) -> DistanceReport:
    """Sum distance from Garmin activity dicts (no file parsing).

    Each activity dict is expected to carry ``distance`` (metres) and, when a
    city filter is used, ``startLatitude`` / ``startLongitude``. When ``center``
    is given, only activities whose start is within ``radius_km`` of it count.

    Args:
        activities: Raw activity dicts (from ``client.get_activities``).
        center: Optional ``(lat, lon)`` city centre.
        radius_km: Radius around ``center`` (default 100 km).

    Returns:
        A :class:`DistanceReport`; ``scanned`` is the number of activities seen.
    """
    radius_m = radius_km * 1000.0
    total_m = 0.0
    counted = 0
    for activity in activities:
        distance_m = activity.get("distance")
        if distance_m is None:
            continue
        if center is not None:
            lat = activity.get("startLatitude")
            lon = activity.get("startLongitude")
            if lat is None or lon is None:
                continue
            if haversine_m(lat, lon, center[0], center[1]) > radius_m:
                continue
        total_m += float(distance_m)
        counted += 1
    return DistanceReport(
        total_km=total_m / 1000.0, activities=counted, scanned=len(activities)
    )
