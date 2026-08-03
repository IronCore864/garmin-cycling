"""Generate a Strava-style route heatmap (HTML) from local FIT files.

Local activity FIT files contain a GPS track (``record`` messages with
``position_lat``/``position_long`` in semicircles). This module reads those
tracks and renders them as overlapping, semi-transparent polylines on a dark
map: roads ridden repeatedly accumulate opacity and light up, just like a
personal Strava heatmap.

The public surface is:

* :class:`GpsTrack` -- one activity's decimated GPS track plus its label.
* :func:`extract_track` -- ``(lat, lon)`` points from a parsed ``FitFile``.
* :func:`load_tracks` -- read + filter a folder of FIT files into tracks.
* :func:`build_heatmap_html` -- render tracks to a self-contained HTML map.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .geo import haversine_m, resolve_city_center

logger = logging.getLogger("garmin")

_SEMI_TO_DEG = 180.0 / (2**31)

# Default radius around a city centre within which an activity's *start* point
# is considered to belong to that city (matches laps.py's start-distance test).
_DEFAULT_CITY_RADIUS_KM = 100.0

# On-disk cache of parsed tracks so repeat runs skip re-parsing FIT files.
_CACHE_FILENAME = ".heatmap_cache.json"
_CACHE_VERSION = 1
# Fidelity at which tracks are parsed and cached. Rendering decimates further
# to the caller's ``max_points`` in-memory, so changing display resolution
# never triggers a re-parse.
_CACHE_MAX_POINTS = 2000
# Parse this many files or fewer inline; above it, use a process pool.
_PARALLEL_THRESHOLD = 2

# Filename convention produced by the ``download`` command:
# ``{YYYY-MM-DD}_{activityId}_{Location_words}_{Sport_words}``.
_FILENAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d+)_(.*)$")

# Trailing words that describe the sport, not the place; stripped to guess the
# location from an activity label.
_SPORT_TOKENS = frozenset(
    {
        "road",
        "cycling",
        "mountain",
        "biking",
        "bike",
        "gravel",
        "unpaved",
        "paved",
        "running",
        "run",
        "ride",
        "riding",
        "walking",
        "hiking",
        "indoor",
        "virtual",
        "e-bike",
        "ebike",
    }
)


@dataclass(frozen=True)
class GpsTrack:
    """One activity's GPS track, ready for heatmap rendering."""

    date: str
    name: str
    location: str
    points: list[tuple[float, float]]


def parse_filename(stem: str) -> tuple[str, str, str]:
    """Split a download filename stem into ``(date, activity_id, label)``.

    Falls back to an empty date/id and the underscore-cleaned stem as the
    label when the name does not match the download naming convention.
    """
    match = _FILENAME_RE.match(stem)
    if not match:
        return "", "", stem.replace("_", " ").strip()
    date_str, activity_id, rest = match.groups()
    return date_str, activity_id, rest.replace("_", " ").strip()


def location_from_label(label: str) -> str:
    """Best-effort place name from an activity label (drops trailing sports).

    ``"Chengdu Road Cycling"`` -> ``"Chengdu"``. When only sport words remain
    (e.g. ``"Running"``) the original label is returned so nothing is lost.
    """
    tokens = [t for t in label.split() if t]
    trimmed = list(tokens)
    while trimmed and trimmed[-1].lower() in _SPORT_TOKENS:
        trimmed.pop()
    return " ".join(trimmed) if trimmed else label.strip()


def _decimate(
    points: list[tuple[float, float]], max_points: int
) -> list[tuple[float, float]]:
    """Down-sample ``points`` to at most ``max_points`` while keeping the ends."""
    if max_points <= 0 or len(points) <= max_points:
        return points
    step = (len(points) + max_points - 1) // max_points
    decimated = points[::step]
    if decimated[-1] != points[-1]:
        decimated.append(points[-1])
    return decimated


def extract_track(fitfile, max_points: int = 500) -> list[tuple[float, float]]:
    """Extract a decimated ``(lat, lon)`` track (degrees) from a FIT file.

    Args:
        fitfile: A parsed ``fitparse.FitFile``.
        max_points: Cap on points per track (decimation keeps the file small
            while preserving the road shape). ``0`` disables decimation.

    Returns:
        A list of ``(lat, lon)`` tuples in degrees; empty if the track has no
        GPS data.
    """
    points: list[tuple[float, float]] = []
    for record in fitfile.get_messages("record"):
        lat = lon = None
        for fld in record.fields:
            if fld.name == "position_lat" and fld.value is not None:
                lat = fld.value * _SEMI_TO_DEG
            elif fld.name == "position_long" and fld.value is not None:
                lon = fld.value * _SEMI_TO_DEG
        if lat is not None and lon is not None:
            points.append((round(lat, 5), round(lon, 5)))
    return _decimate(points, max_points)


def _extract_points_from_path(
    path_str: str, max_points: int
) -> list[tuple[float, float]]:
    """Parse one FIT file into a decimated track (module-level for pickling).

    Returns an empty list for unreadable/corrupt files. ``check_crc=False``
    skips CRC validation, which is a meaningful speed-up for large tracks.
    """
    import fitparse

    try:
        fitfile = fitparse.FitFile(path_str, check_crc=False)
        return extract_track(fitfile, max_points=max_points)
    except Exception:  # noqa: BLE001 -- skip any unreadable/corrupt file
        logger.debug("Skipping unreadable FIT file: %s", path_str)
        return []


def _pinyin(text: str) -> str:
    """Romanize Chinese characters to plain (toneless) pinyin.

    Non-Chinese text passes through unchanged. Returns ``""`` if ``pypinyin``
    is unavailable, so matching gracefully degrades to a plain substring.
    """
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:  # pragma: no cover - pypinyin is a declared dependency
        return ""
    return "".join(lazy_pinyin(text, style=Style.NORMAL))


def _location_match_key(location: str) -> str:
    """Space-stripped, lowercased location plus its pinyin, for city matching.

    Combining the raw name with its romanization lets an English/pinyin query
    (``"chengdu"``) match a Chinese location (``"成都市"``) and vice versa.
    """
    return (location.lower() + _pinyin(location).lower()).replace(" ", "")


def filter_tracks(
    tracks: list[GpsTrack],
    year: int | None = None,
    city: str | None = None,
    center: tuple[float, float] | None = None,
    radius_km: float = _DEFAULT_CITY_RADIUS_KM,
) -> list[GpsTrack]:
    """Keep tracks matching an optional ``year`` and/or city.

    City matching works two ways:

    * **Geographic** (preferred): when ``center`` is a ``(lat, lon)`` pair, a
      track is kept if its *start* point lies within ``radius_km`` of that
      centre. This catches rides whose location words never mention the city
      (e.g. a Chengdu ride labelled ``天府大道``).
    * **Name** (fallback): when ``center`` is ``None`` but ``city`` is given, a
      case-insensitive substring test is run against the location name *and*
      its pinyin, so ``"chengdu"`` matches both ``"Chengdu"`` and ``"成都市"``.
    """
    needle = (
        city.lower().replace(" ", "")
        if city is not None and center is None
        else None
    )
    radius_m = radius_km * 1000.0
    result = []
    for track in tracks:
        if year is not None and not track.date.startswith(str(year)):
            continue
        if center is not None:
            if not track.points:
                continue
            start_lat, start_lon = track.points[0]
            if haversine_m(start_lat, start_lon, center[0], center[1]) > radius_m:
                continue
        elif needle is not None and needle not in _location_match_key(
            track.location
        ):
            continue
        result.append(track)
    return result


def load_tracks(
    directory: str | Path,
    year: int | None = None,
    city: str | None = None,
    max_points: int = 500,
    radius_km: float = _DEFAULT_CITY_RADIUS_KM,
    allow_geocode: bool = True,
    on_progress: Callable[[int, int], None] | None = None,
    use_cache: bool = True,
) -> list[GpsTrack]:
    """Read FIT files from ``directory`` into filtered :class:`GpsTrack` objects.

    Parsing FIT files is the slow part, so results are cached on disk (keyed by
    file size + mtime) and any files that still need parsing are decoded in
    parallel across CPU cores.

    Args:
        directory: Folder of ``*.fit`` files (the ``download`` output).
        year: Optional year filter (matched against the filename date prefix,
            so files are skipped before parsing).
        city: Optional city filter. Resolved to a ``(lat, lon)`` centre; any
            activity whose GPS track *starts* within ``radius_km`` of it is
            kept. Falls back to a case-insensitive name/pinyin substring match
            when the city centre cannot be resolved.
        max_points: Per-track display cap. Tracks are cached at a fixed high
            fidelity and decimated to this value in-memory, so changing it is
            instant (no re-parse). Lower values suit wide-area maps.
        radius_km: Radius around the resolved city centre for the geographic
            filter (default 100 km).
        allow_geocode: Allow online geocoding when the city is not in the
            built-in registry or on-disk cache. Set ``False`` to stay offline.
        on_progress: Optional callback invoked as ``(done, total)`` as files
            are resolved (from cache or freshly parsed).
        use_cache: Read/write the on-disk parse cache (``.heatmap_cache.json``
            in ``directory``). Set ``False`` to force a full re-parse.

    Returns:
        Tracks that have GPS data and pass the filters, in filename order.
    """
    directory = Path(directory)
    candidates = [
        fp
        for fp in sorted(directory.glob("*.fit"))
        if year is None or fp.name.startswith(str(year))
    ]
    total = len(candidates)

    cache_path = directory / _CACHE_FILENAME
    cache = _read_cache(cache_path) if use_cache else {}
    updated_cache = dict(cache)  # preserve entries outside this run's filter

    points_by_name: dict[str, list[tuple[float, float]]] = {}
    to_parse: list[Path] = []
    for fp in candidates:
        stat = fp.stat()
        entry = cache.get(fp.name)
        if (
            entry
            and entry.get("mtime_ns") == stat.st_mtime_ns
            and entry.get("size") == stat.st_size
        ):
            points_by_name[fp.name] = [tuple(p) for p in entry["points"]]
        else:
            to_parse.append(fp)

    done = total - len(to_parse)
    if on_progress is not None and done:
        on_progress(done, total)

    def _record(fp: Path, points: list[tuple[float, float]]) -> None:
        nonlocal done
        points_by_name[fp.name] = points
        stat = fp.stat()
        updated_cache[fp.name] = {
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
            "points": points,
        }
        done += 1
        if on_progress is not None:
            on_progress(done, total)

    if len(to_parse) <= _PARALLEL_THRESHOLD:
        for fp in to_parse:
            _record(fp, _extract_points_from_path(str(fp), _CACHE_MAX_POINTS))
    else:
        with ProcessPoolExecutor() as executor:
            futures = {
                executor.submit(
                    _extract_points_from_path, str(fp), _CACHE_MAX_POINTS
                ): fp
                for fp in to_parse
            }
            for future in as_completed(futures):
                _record(futures[future], future.result())

    if use_cache and to_parse:
        _write_cache(cache_path, updated_cache)

    tracks: list[GpsTrack] = []
    for fp in candidates:
        points = points_by_name.get(fp.name)
        if not points:
            continue
        date_str, _activity_id, label = parse_filename(fp.stem)
        tracks.append(
            GpsTrack(
                date=date_str or fp.name[:10],
                name=label or fp.stem,
                location=location_from_label(label),
                points=_decimate(points, max_points),
            )
        )
    if city is not None:
        center = resolve_city_center(city, allow_network=allow_geocode)
        if center is not None:
            logger.info(
                "Filtering by start point within %.0f km of %s (%.4f, %.4f).",
                radius_km,
                city,
                center[0],
                center[1],
            )
            tracks = filter_tracks(tracks, center=center, radius_km=radius_km)
        else:
            logger.info(
                "Could not resolve a centre for %r; falling back to a "
                "name-based match.",
                city,
            )
            tracks = filter_tracks(tracks, city=city)
    return tracks


def _read_cache(cache_path: Path) -> dict[str, dict]:
    """Load the parse cache, ignoring it if the version or fidelity differs."""
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if (
        data.get("version") != _CACHE_VERSION
        or data.get("max_points") != _CACHE_MAX_POINTS
    ):
        return {}
    return data.get("entries", {})


def _write_cache(cache_path: Path, entries: dict[str, dict]) -> None:
    """Persist the parse cache; failures are non-fatal (debug-logged)."""
    payload = {
        "version": _CACHE_VERSION,
        "max_points": _CACHE_MAX_POINTS,
        "entries": entries,
    }
    try:
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logger.debug("Could not write heatmap cache: %s", cache_path)


def summarize_locations(tracks: list[GpsTrack]) -> dict[str, int]:
    """Count activities per location, most common first."""
    counts = Counter((t.location or "Unknown") for t in tracks)
    return dict(counts.most_common())


def build_heatmap_html(
    tracks: list[GpsTrack],
    out_path: str | Path,
    *,
    color: str = "#FC4C02",
    weight: int = 2,
    opacity: float = 0.5,
    tiles: str = "CartoDB dark_matter",
) -> Path:
    """Render ``tracks`` as an overlapping-polyline heatmap and save as HTML.

    Args:
        tracks: Tracks to draw (from :func:`load_tracks`).
        out_path: Destination ``.html`` file (parent dirs are created).
        color: Route colour; the default is Strava orange on a dark basemap.
        weight: Line thickness in pixels.
        opacity: Per-line opacity; overlapping roads accumulate and brighten.
        tiles: Folium/Leaflet basemap tile name.

    Returns:
        The path written.

    Raises:
        ValueError: If ``tracks`` contains no GPS points.
    """
    import folium

    lats = [lat for t in tracks for lat, _ in t.points]
    lons = [lon for t in tracks for _, lon in t.points]
    if not lats:
        raise ValueError("No GPS points to plot.")

    center = (sum(lats) / len(lats), sum(lons) / len(lons))
    fmap = folium.Map(location=center, tiles=tiles, zoom_start=5)
    for track in tracks:
        if len(track.points) < 2:
            continue
        folium.PolyLine(
            track.points,
            color=color,
            weight=weight,
            opacity=opacity,
            tooltip=f"{track.date} {track.name}",
        ).add_to(fmap)

    fmap.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    out_path = Path(out_path)
    if out_path.parent != Path():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    fmap.save(str(out_path))
    return out_path
