"""Tests for garmin.laps: geometry, winding, and lap counting."""

from datetime import date

import numpy as np

from garmin.laps import (
    _SEMI_TO_DEG,
    DEFAULT_LAKE,
    Lake,
    _haversine,
    count_circles,
    count_fit_laps,
    count_laps_in_directory,
)

# --- helpers ---------------------------------------------------------------


def _circle_points(n_loops, num=240, radius_deg=0.01, center=(0.0, 0.0)):
    """(N, 2) array of (lat, lon) tracing ``n_loops`` circuits around center."""
    t = np.linspace(0, 2 * np.pi * n_loops, num)
    lat = center[0] + radius_deg * np.sin(t)
    lon = center[1] + radius_deg * np.cos(t)
    return np.column_stack([lat, lon])


class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Record:
    def __init__(self, lat_deg, lon_deg):
        self.fields = [
            _Field("position_lat", lat_deg / _SEMI_TO_DEG),
            _Field("position_long", lon_deg / _SEMI_TO_DEG),
        ]


class _FakeFitFile:
    def __init__(self, points):
        self._records = [_Record(lat, lon) for lat, lon in points]

    def get_messages(self, _kind):
        return self._records


# --- Lake value object -----------------------------------------------------


def test_lake_properties():
    lake = Lake(30.0, 104.0, 2000.0)
    assert lake.center == (30.0, 104.0)
    assert lake.radius_km == 2.0


def test_default_lake():
    assert DEFAULT_LAKE.radius_km == 2.0
    assert DEFAULT_LAKE.center[0] == DEFAULT_LAKE.latitude


# --- haversine -------------------------------------------------------------


def test_haversine_zero_distance():
    assert _haversine(10.0, 20.0, 10.0, 20.0) == 0.0


def test_haversine_one_degree_longitude_at_equator():
    # ~111.2 km per degree of longitude at the equator.
    dist = _haversine(0.0, 0.0, 0.0, 1.0)
    assert abs(dist - 111195) < 500


# --- count_circles ---------------------------------------------------------


def test_count_circles_single_loop():
    lake = Lake(0.0, 0.0, 2000.0)
    assert count_circles(_circle_points(1), lake) == 1


def test_count_circles_multiple_loops():
    lake = Lake(0.0, 0.0, 2000.0)
    assert count_circles(_circle_points(3), lake) == 3


def test_count_circles_too_few_points():
    lake = Lake(0.0, 0.0, 2000.0)
    assert count_circles(_circle_points(1, num=5), lake) == 0


def test_count_circles_all_points_far_from_lake():
    # A circle of radius ~11 km lies outside 3x the 2 km radius -> no near pts.
    lake = Lake(0.0, 0.0, 2000.0)
    assert count_circles(_circle_points(1, radius_deg=0.1), lake) == 0


# --- count_fit_laps --------------------------------------------------------


def test_count_fit_laps_near_lake():
    lake = Lake(0.0, 0.0, 2000.0)
    fit = _FakeFitFile(_circle_points(2))
    assert count_fit_laps(fit, lake) == 2


def test_count_fit_laps_far_start_gated_to_zero():
    lake = Lake(0.0, 0.0, 2000.0)
    # Circle centred ~166 km away: start is beyond the max-start gate.
    fit = _FakeFitFile(_circle_points(2, center=(1.5, 0.0)))
    assert count_fit_laps(fit, lake) == 0


def test_count_fit_laps_no_points():
    assert count_fit_laps(_FakeFitFile([])) == 0


# --- count_laps_in_directory ----------------------------------------------


def test_count_laps_in_directory_date_filter(tmp_path):
    # Dummy (unparseable) FIT files: parsing fails so each is skipped, but the
    # date-range filter still selects which files are *scanned*.
    for name in (
        "2026-01-05_1_x.fit",
        "2026-01-20_2_y.fit",
        "2026-02-01_3_z.fit",  # out of range
        "2025-12-31_4_w.fit",  # out of range
    ):
        (tmp_path / name).write_bytes(b"not a real fit file")

    results, scanned = count_laps_in_directory(
        tmp_path, date(2026, 1, 1), date(2026, 1, 31)
    )
    assert scanned == 2
    assert results == []


def test_count_laps_in_directory_empty(tmp_path):
    results, scanned = count_laps_in_directory(
        tmp_path, date(2026, 1, 1), date(2026, 12, 31)
    )
    assert scanned == 0
    assert results == []
