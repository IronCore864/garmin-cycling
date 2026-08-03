"""Geographic helpers: distances and resolving a city name to its centre.

The heatmap groups activities by *city*. Matching on the location words in a
filename is unreliable -- a Chengdu ride labelled ``天府大道`` or ``龙泉山``
does not contain the word "Chengdu" at all. Instead we resolve a city name to
a ``(latitude, longitude)`` centre and keep any activity whose GPS track
*starts* within a radius of it (the same start-point + great-circle test
:mod:`garmin.laps` uses to decide whether a ride is "at" a lake).

Resolution order for a city name:

1. A small built-in registry (:data:`CITY_CENTERS`) -- instant and offline,
   with English/pinyin and Chinese aliases.
2. Cached online geocoding via OpenStreetMap's Nominatim -- covers any city,
   the result is cached on disk so it only hits the network once, and any
   failure (no network, timeout) degrades gracefully to ``None``.

The public surface is:

* :func:`haversine_m` -- great-circle distance between two points, in metres.
* :data:`CITY_CENTERS` -- built-in ``key -> (lat, lon)`` registry.
* :func:`resolve_city_center` -- city name -> ``(lat, lon)`` or ``None``.
* :func:`normalize_city_key` -- normalise a name for registry lookup.
"""

from __future__ import annotations

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger("garmin")

_EARTH_RADIUS_M = 6371000.0

# On-disk cache for geocoded city centres, so a name is only looked up once.
_CACHE_DIR = Path.home() / ".cache" / "garmin-cycling"
_GEOCODE_CACHE = _CACHE_DIR / "geocode.json"

# Built-in city centres, keyed by their normalised name (see
# ``normalize_city_key``). Values are ``(latitude, longitude)`` in degrees.
# Seed the cities ridden most; anything else falls back to online geocoding.
CITY_CENTERS: dict[str, tuple[float, float]] = {
    "chengdu": (30.5728, 104.0668),
    "chongqing": (29.5630, 106.5516),
    "beijing": (39.9042, 116.4074),
    "shanghai": (31.2304, 121.4737),
    "guangzhou": (23.1291, 113.2644),
    "shenzhen": (22.5431, 114.0579),
    "hangzhou": (30.2741, 120.1551),
    "xian": (34.3416, 108.9398),
    "qingdao": (36.0671, 120.3826),
    "munich": (48.1351, 11.5820),
}


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
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


def _pinyin(text: str) -> str:
    """Romanize Chinese characters to plain (toneless) pinyin.

    Non-Chinese text passes through unchanged. Returns ``""`` if ``pypinyin``
    is unavailable, so lookups degrade to the raw name.
    """
    try:
        from pypinyin import Style, lazy_pinyin
    except ImportError:  # pragma: no cover - pypinyin is a declared dependency
        return ""
    return "".join(lazy_pinyin(text, style=Style.NORMAL))


def normalize_city_key(name: str) -> str:
    """Normalise a city name for registry lookup.

    Romanizes to pinyin (Latin text passes through unchanged), lowercases, and
    keeps only alphanumerics. A Chinese name (``"成都"``) and its pinyin/English
    (``"Chengdu"`` / ``"Cheng Du"``) all collapse to the same key ``"chengdu"``.
    """
    romanized = _pinyin(name) or name
    return "".join(c for c in romanized.lower() if c.isalnum())


def _read_geocode_cache() -> dict[str, list[float]]:
    """Load the on-disk geocode cache (``{}`` if missing/unreadable)."""
    try:
        return json.loads(_GEOCODE_CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _write_geocode_cache(cache: dict[str, list[float]]) -> None:
    """Persist the geocode cache; failures are non-fatal (debug-logged)."""
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        _GEOCODE_CACHE.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        logger.debug("Could not write geocode cache: %s", _GEOCODE_CACHE)


def _geocode_online(name: str, *, timeout: float = 10.0) -> tuple[float, float] | None:
    """Geocode a city name via OpenStreetMap Nominatim (or ``None`` on failure).

    Kept dependency-free (stdlib ``urllib``) and fully guarded: any network,
    parsing, or service error returns ``None`` so the caller can fall back.
    """
    import urllib.parse
    import urllib.request

    query = urllib.parse.urlencode(
        {"q": name, "format": "json", "limit": 1}
    )
    url = f"https://nominatim.openstreetmap.org/search?{query}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "garmin-cycling/0.1 (heatmap city filter)"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:  # noqa: BLE001 -- any failure degrades to no result
        logger.debug("Online geocoding failed for %r", name)
        return None
    if not payload:
        return None
    try:
        return float(payload[0]["lat"]), float(payload[0]["lon"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


def resolve_city_center(
    name: str, *, allow_network: bool = True
) -> tuple[float, float] | None:
    """Resolve a city name to a ``(latitude, longitude)`` centre.

    Checks the built-in :data:`CITY_CENTERS` registry first (instant, offline),
    then the on-disk geocode cache, then -- when ``allow_network`` is set --
    online geocoding (whose result is cached). Returns ``None`` when the name
    cannot be resolved, letting callers fall back to name-based matching.
    """
    if not name or not name.strip():
        return None

    key = normalize_city_key(name)
    if key in CITY_CENTERS:
        return CITY_CENTERS[key]

    cache = _read_geocode_cache()
    cached = cache.get(key)
    if cached and len(cached) == 2:
        return float(cached[0]), float(cached[1])

    if not allow_network:
        return None

    center = _geocode_online(name)
    if center is not None:
        cache[key] = [center[0], center[1]]
        _write_geocode_cache(cache)
    return center
