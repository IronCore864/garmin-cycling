"""Tests for garmin.distance: FIT summary + directory aggregation with filters."""

import struct

import pytest

from garmin.distance import (
    DistanceReport,
    distance_from_activities,
    distance_in_directory,
    summarize_fit,
)

_SEMI_TO_DEG = 180.0 / (2**31)


# --- FIT fakes (mirroring tests/test_laps.py / test_heatmap.py) ------------


class _Field:
    def __init__(self, name, value):
        self.name = name
        self.value = value


class _Msg:
    def __init__(self, fields):
        self.fields = fields


class _FakeFitFile:
    """Minimal stand-in exposing ``session`` and ``record`` messages."""

    def __init__(self, points, *, session_total_m=None, record_dists=None):
        self._records = []
        for i, (lat, lon) in enumerate(points):
            fields = [
                _Field("position_lat", lat / _SEMI_TO_DEG),
                _Field("position_long", lon / _SEMI_TO_DEG),
            ]
            if record_dists is not None:
                fields.append(_Field("distance", record_dists[i]))
            self._records.append(_Msg(fields))
        self._sessions = []
        if session_total_m is not None:
            self._sessions.append(
                _Msg([_Field("total_distance", session_total_m)])
            )

    def get_messages(self, kind):
        return self._sessions if kind == "session" else self._records


# --- summarize_fit ---------------------------------------------------------


def test_summarize_fit_prefers_session_total():
    fit = _FakeFitFile(
        [(30.5, 104.0), (30.6, 104.1)],
        session_total_m=42000.0,
        record_dists=[0.0, 1000.0],
    )
    start, distance_m = summarize_fit(fit)
    assert start == pytest.approx((30.5, 104.0))
    assert distance_m == 42000.0


def test_summarize_fit_falls_back_to_last_record_distance():
    fit = _FakeFitFile(
        [(30.5, 104.0), (30.6, 104.1), (30.7, 104.2)],
        record_dists=[0.0, 500.0, 1500.0],
    )
    start, distance_m = summarize_fit(fit)
    assert start == pytest.approx((30.5, 104.0))
    assert distance_m == 1500.0


def test_summarize_fit_no_gps_returns_none_start():
    fit = _FakeFitFile([], session_total_m=1000.0)
    start, distance_m = summarize_fit(fit)
    assert start is None
    assert distance_m == 1000.0


# --- distance_in_directory (with a monkeypatched FIT parser) ---------------


def _write_stub_fit(path):
    """Write a tiny non-empty file; content is irrelevant (parser is faked)."""
    path.write_bytes(struct.pack("<I", 0))


def test_distance_in_directory_filters_by_city_center(monkeypatch, tmp_path):
    # Two Chengdu rides + one Munich ride; only Chengdu should be counted.
    fits = {
        "2026-01-01_1_a.fit": _FakeFitFile(
            [(30.60, 104.10)], session_total_m=30000.0
        ),
        "2026-01-02_2_b.fit": _FakeFitFile(
            [(30.55, 104.30)], session_total_m=20000.0
        ),
        "2026-01-03_3_munich.fit": _FakeFitFile(
            [(48.1351, 11.5820)], session_total_m=99000.0
        ),
    }
    for name in fits:
        _write_stub_fit(tmp_path / name)

    import sys

    class _FakeFitParse:
        def FitFile(self, path_str, check_crc=False):  # noqa: N802 - mimic API
            from pathlib import Path

            return fits[Path(path_str).name]

    monkeypatch.setitem(sys.modules, "fitparse", _FakeFitParse())

    chengdu = (30.5728, 104.0668)
    report = distance_in_directory(tmp_path, center=chengdu, radius_km=100.0)
    assert isinstance(report, DistanceReport)
    assert report.scanned == 3
    assert report.activities == 2
    assert report.total_km == pytest.approx(50.0)


def test_distance_in_directory_no_center_counts_all(monkeypatch, tmp_path):
    fits = {
        "2026-01-01_1_a.fit": _FakeFitFile([(0.0, 0.0)], session_total_m=1000.0),
        "2025-01-01_2_b.fit": _FakeFitFile([(0.0, 0.0)], session_total_m=2000.0),
    }
    for name in fits:
        _write_stub_fit(tmp_path / name)

    class _FakeFitParse:
        def FitFile(self, path_str, check_crc=False):  # noqa: N802 - mimic API
            from pathlib import Path

            return fits[Path(path_str).name]

    monkeypatch.setitem(
        __import__("sys").modules, "fitparse", _FakeFitParse()
    )

    # Year filter keeps only the 2026 file.
    report = distance_in_directory(tmp_path, year=2026)
    assert report.scanned == 1
    assert report.activities == 1
    assert report.total_km == pytest.approx(1.0)


# --- distance_from_activities (Garmin API dicts) ---------------------------


def test_distance_from_activities_no_center_sums_all():
    activities = [
        {"distance": 10000, "startLatitude": 30.6, "startLongitude": 104.1},
        {"distance": 20000, "startLatitude": 48.1, "startLongitude": 11.6},
        {"distance": None},  # ignored (no distance)
    ]
    report = distance_from_activities(activities)
    assert report.scanned == 3
    assert report.activities == 2
    assert report.total_km == pytest.approx(30.0)


def test_distance_from_activities_filters_by_center():
    chengdu = (30.5728, 104.0668)
    activities = [
        {"distance": 30000, "startLatitude": 30.60, "startLongitude": 104.10},
        {"distance": 20000, "startLatitude": 30.55, "startLongitude": 104.30},
        {"distance": 99000, "startLatitude": 48.1351, "startLongitude": 11.5820},
        {"distance": 5000},  # no start coords -> excluded when filtering
    ]
    report = distance_from_activities(activities, center=chengdu, radius_km=100.0)
    assert report.scanned == 4
    assert report.activities == 2
    assert report.total_km == pytest.approx(50.0)
