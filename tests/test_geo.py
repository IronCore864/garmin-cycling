"""Tests for garmin.geo: haversine, city-key normalisation, centre resolution."""

from garmin import geo
from garmin.geo import (
    CITY_CENTERS,
    haversine_m,
    normalize_city_key,
    resolve_city_center,
)

# --- haversine -------------------------------------------------------------


def test_haversine_zero_distance():
    assert haversine_m(30.0, 104.0, 30.0, 104.0) == 0.0


def test_haversine_one_degree_latitude_is_about_111km():
    # A degree of latitude is ~111 km anywhere on the globe.
    dist = haversine_m(30.0, 104.0, 31.0, 104.0)
    assert 110_000 < dist < 112_000


# --- normalize_city_key ----------------------------------------------------


def test_normalize_city_key_lowercases_and_strips_spaces():
    assert normalize_city_key("  Cheng Du ") == "chengdu"


def test_normalize_city_key_maps_chinese_to_pinyin():
    # "成都" romanises to "chengdu"; the key includes the pinyin form so a
    # Chinese name collapses onto the same registry key as the English one.
    assert "chengdu" in normalize_city_key("成都")


# --- resolve_city_center ---------------------------------------------------


def test_resolve_city_center_from_registry_english():
    assert resolve_city_center("Chengdu", allow_network=False) == CITY_CENTERS[
        "chengdu"
    ]


def test_resolve_city_center_from_registry_chinese():
    assert resolve_city_center("成都", allow_network=False) == CITY_CENTERS[
        "chengdu"
    ]


def test_resolve_city_center_unknown_offline_returns_none():
    assert (
        resolve_city_center("Nowhere-in-particular-12345", allow_network=False)
        is None
    )


def test_resolve_city_center_blank_returns_none():
    assert resolve_city_center("   ", allow_network=False) is None


def test_resolve_city_center_uses_disk_cache(monkeypatch, tmp_path):
    # A previously geocoded, non-registry city is served from the on-disk
    # cache without touching the network.
    cache_file = tmp_path / "geocode.json"
    monkeypatch.setattr(geo, "_GEOCODE_CACHE", cache_file)
    key = normalize_city_key("Springfield")
    cache_file.write_text(f'{{"{key}": [1.5, 2.5]}}', encoding="utf-8")

    def _boom(*_args, **_kwargs):  # network must not be called
        raise AssertionError("network should not be used when cached")

    monkeypatch.setattr(geo, "_geocode_online", _boom)
    assert resolve_city_center("Springfield") == (1.5, 2.5)
