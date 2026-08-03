"""Total ridden distance from local FIT files, optionally filtered by city.

This reuses the geographic city filter from :mod:`garmin.geo`: an activity is
counted for a city when its GPS track *starts* within a radius of that city's
centre. Distance itself is read from the FIT file's own recorded total (the
``session`` ``total_distance``), so it is accurate rather than an estimate off
the decimated heatmap track.

The public surface is:

* :class:`DistanceReport` -- the aggregate ``(total_km, activities, scanned)``.
* :func:`distance_from_activities` -- sum distance from Garmin activity dicts
  (fast: no file parsing, uses the API's own ``distance`` + start coordinates).
* :func:`summarize_fit` -- ``(start_point, distance_m)`` for a parsed FIT file.
* :func:`distance_in_directory` -- sum a folder of FIT files with filters
  (offline fallback; parses files in parallel across CPU cores).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .geo import haversine_m

logger = logging.getLogger("garmin")

_SEMI_TO_DEG = 180.0 / (2**31)

# Parse this many files or fewer inline; above it, use a process pool.
_PARALLEL_THRESHOLD = 4


@dataclass(frozen=True)
class DistanceReport:
    """Aggregate ridden distance over a set of FIT files."""

    total_km: float
    activities: int
    scanned: int


def distance_from_activities(
    activities: list[dict[str, Any]],
    center: tuple[float, float] | None = None,
    radius_km: float = 100.0,
) -> DistanceReport:
    """Sum distance from Garmin activity dicts (no file parsing).

    The activity list returned by the Garmin API already carries each ride's
    ``distance`` (metres) and its ``startLatitude`` / ``startLongitude``, so
    this is far faster than parsing FIT files. When ``center`` is given, only
    activities whose start is within ``radius_km`` of it are counted.

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


def summarize_fit(fitfile) -> tuple[tuple[float, float] | None, float]:
    """Return ``(start_point, distance_m)`` for a parsed ``fitparse.FitFile``.

    ``start_point`` is the first GPS fix as ``(lat, lon)`` in degrees (or
    ``None`` if the track has no GPS). ``distance_m`` prefers the sum of the
    ``session`` messages' ``total_distance`` and falls back to the last
    cumulative ``record`` ``distance`` when no session total is present.
    """
    session_total = 0.0
    has_session = False
    for session in fitfile.get_messages("session"):
        for field in session.fields:
            if field.name == "total_distance" and field.value is not None:
                session_total += float(field.value)
                has_session = True

    start: tuple[float, float] | None = None
    last_record_dist = 0.0
    for record in fitfile.get_messages("record"):
        lat = lon = None
        for field in record.fields:
            if field.name == "position_lat" and field.value is not None:
                lat = field.value * _SEMI_TO_DEG
            elif field.name == "position_long" and field.value is not None:
                lon = field.value * _SEMI_TO_DEG
            elif field.name == "distance" and field.value is not None:
                last_record_dist = float(field.value)
        if start is None and lat is not None and lon is not None:
            start = (lat, lon)

    distance_m = session_total if has_session else last_record_dist
    return start, distance_m


def _summarize_path(path_str: str) -> tuple[tuple[float, float] | None, float] | None:
    """Parse one FIT file into ``(start, distance_m)`` (module-level for pickling).

    Returns ``None`` for an unreadable/corrupt file so the caller can skip it.
    """
    import fitparse

    try:
        fitfile = fitparse.FitFile(path_str, check_crc=False)
        return summarize_fit(fitfile)
    except Exception:  # noqa: BLE001 -- skip any unreadable/corrupt file
        logger.debug("Skipping unreadable FIT file: %s", path_str)
        return None


def distance_in_directory(
    directory: str | Path,
    center: tuple[float, float] | None = None,
    radius_km: float = 100.0,
    year: int | None = None,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int | None = None,
) -> DistanceReport:
    """Sum ridden distance across FIT files in ``directory`` (offline fallback).

    Parsing FIT files is the slow part, so files are decoded in parallel across
    CPU cores. Prefer :func:`distance_from_activities` when online.

    Args:
        directory: Folder of ``*.fit`` files (the ``download`` output).
        center: Optional ``(lat, lon)`` city centre. When given, only
            activities whose track starts within ``radius_km`` of it count.
        radius_km: Radius around ``center`` (default 100 km).
        year: Optional year filter (matched against the filename date prefix).
        on_progress: Optional callback invoked as ``(done, total)`` after each
            FIT file is parsed, so callers can show progress on a slow scan.
        max_workers: Process-pool size (defaults to the number of CPU cores).

    Returns:
        A :class:`DistanceReport` with the total distance in km, the number of
        activities counted, and the number of FIT files scanned.
    """
    directory = Path(directory)
    files = sorted(
        fp
        for fp in directory.glob("*.fit")
        if year is None or fp.name.startswith(str(year))
    )
    total = len(files)
    radius_m = radius_km * 1000.0

    results: dict[Path, tuple[tuple[float, float] | None, float] | None] = {}
    done = 0

    def _record(fp: Path, res) -> None:
        nonlocal done
        results[fp] = res
        done += 1
        if on_progress is not None:
            on_progress(done, total)

    if total <= _PARALLEL_THRESHOLD:
        for fp in files:
            _record(fp, _summarize_path(str(fp)))
    else:
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_summarize_path, str(fp)): fp for fp in files}
            for future in as_completed(futures):
                _record(futures[future], future.result())

    total_m = 0.0
    activities = 0
    for fp in files:
        res = results.get(fp)
        if res is None:
            continue
        start, distance_m = res
        if center is None or (
            start is not None
            and haversine_m(start[0], start[1], center[0], center[1]) <= radius_m
        ):
            total_m += distance_m
            activities += 1

    return DistanceReport(
        total_km=total_m / 1000.0, activities=activities, scanned=total
    )
