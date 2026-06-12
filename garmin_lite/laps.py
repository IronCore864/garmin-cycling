"""Count laps (circles) around a lake for the latest Garmin CN activity."""

import io
import logging
import math
import zipfile

import fitparse
import numpy as np

from garminconnect import Garmin

logger = logging.getLogger("garmin_lite")

# Default lake: Xinglong Lake.
DEFAULT_LAKE_LATITUDE = 30.40111111111111
DEFAULT_LAKE_LONGITUDE = 104.0861111111111
DEFAULT_LAKE_RADIUS_M = 2000.0

EARTH_RADIUS_M = 6371000
MIN_SEGMENT_POINTS = 12
SEMI_TO_DEG = 180.0 / (2**31)
# Ignore activities whose start is farther than this from the lake.
MAX_START_DISTANCE_M = 100000


def _haversine(lat1, lon1, lat2, lon2) -> float:
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat = lat2_r - lat1_r
    dlon = lon2_r - lon1_r
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_M * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _parse_points(fitfile: fitparse.FitFile) -> np.ndarray:
    lats, lons = [], []
    for record in fitfile.get_messages("record"):
        lat = lon = None
        for field in record.fields:
            if field.name == "position_lat" and field.value is not None:
                lat = field.value * SEMI_TO_DEG
            elif field.name == "position_long" and field.value is not None:
                lon = field.value * SEMI_TO_DEG
        if lat is not None and lon is not None:
            lats.append(lat)
            lons.append(lon)
    if not lats:
        return np.empty((0, 2), dtype=np.float64)
    return np.column_stack([lats, lons])


def _winding_number(points: np.ndarray, center: np.ndarray) -> int:
    dy = points[:, 0] - center[0]
    dx = points[:, 1] - center[1]
    angles = np.arctan2(dy, dx)
    d = np.diff(angles)
    d = (d + np.pi) % (2.0 * np.pi) - np.pi
    return int(np.round(d.sum() / (2.0 * np.pi)))


def _count_circles(
    points: np.ndarray,
    lake_center: tuple[float, float],
    lake_radius_km: float,
) -> int:
    if len(points) < MIN_SEGMENT_POINTS:
        return 0

    center = np.array(lake_center, dtype=np.float64)
    cos_lat = np.cos(np.radians(center[0]))
    dlat_km = (points[:, 0] - center[0]) * 111.0
    dlon_km = (points[:, 1] - center[1]) * 111.0 * cos_lat
    dist_km = np.sqrt(dlat_km**2 + dlon_km**2)

    near = dist_km < lake_radius_km * 3.0
    if near.sum() < MIN_SEGMENT_POINTS:
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
        if e - s < MIN_SEGMENT_POINTS:
            continue
        total += abs(_winding_number(points[s:e], center))
    return total


def count_latest_activity_laps(
    cn_client: Garmin,
    lake_lat: float = DEFAULT_LAKE_LATITUDE,
    lake_lon: float = DEFAULT_LAKE_LONGITUDE,
    lake_radius_m: float = DEFAULT_LAKE_RADIUS_M,
) -> int:
    """Download the latest Garmin CN activity and count lake circles."""
    activities = cn_client.get_activities(0, 1)
    if not activities:
        logger.warning("No activities found to count laps.")
        return 0

    activity_id = activities[0].get("activityId")
    activity_bytes = cn_client.download_activity(
        activity_id, dl_fmt=cn_client.ActivityDownloadFormat.ORIGINAL
    )

    fit_bytes = None
    with zipfile.ZipFile(io.BytesIO(activity_bytes)) as zipf:
        for fname in zipf.namelist():
            if fname.endswith(".fit"):
                with zipf.open(fname) as fit_file:
                    fit_bytes = fit_file.read()
                break
    if not fit_bytes:
        logger.warning("No .fit file in latest activity archive.")
        return 0

    fitfile = fitparse.FitFile(io.BytesIO(fit_bytes))
    points = _parse_points(fitfile)
    if len(points) == 0:
        return 0

    start_lat, start_lon = points[0]
    if _haversine(start_lat, start_lon, lake_lat, lake_lon) > MAX_START_DISTANCE_M:
        logger.info("Latest activity starts far from the lake; counting 0 laps.")
        return 0

    return _count_circles(
        points, (lake_lat, lake_lon), lake_radius_m / 1000.0
    )
