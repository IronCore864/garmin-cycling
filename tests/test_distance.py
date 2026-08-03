"""Tests for garmin.distance: summing distance from Garmin activity dicts."""

import pytest

from garmin.distance import DistanceReport, distance_from_activities


def test_distance_from_activities_no_center_sums_all():
    activities = [
        {"distance": 10000, "startLatitude": 30.6, "startLongitude": 104.1},
        {"distance": 20000, "startLatitude": 48.1, "startLongitude": 11.6},
        {"distance": None},  # ignored (no distance)
    ]
    report = distance_from_activities(activities)
    assert isinstance(report, DistanceReport)
    assert report.scanned == 3
    assert report.activities == 2
    assert report.total_km == pytest.approx(30.0)


def test_distance_from_activities_filters_by_center():
    chengdu = (30.5728, 104.0668)
    activities = [
        # Labelled elsewhere, but starts in Chengdu -> counted.
        {"distance": 30000, "startLatitude": 30.60, "startLongitude": 104.10},
        {"distance": 20000, "startLatitude": 30.55, "startLongitude": 104.30},
        # Munich -> far away -> excluded.
        {"distance": 99000, "startLatitude": 48.1351, "startLongitude": 11.5820},
        # No start coords -> excluded when a city filter is active.
        {"distance": 5000},
    ]
    report = distance_from_activities(activities, center=chengdu, radius_km=100.0)
    assert report.scanned == 4
    assert report.activities == 2
    assert report.total_km == pytest.approx(50.0)


def test_distance_from_activities_respects_radius():
    chengdu = (30.5728, 104.0668)
    activities = [
        {"distance": 10000, "startLatitude": 31.9, "startLongitude": 104.0}
    ]  # ~150 km north
    assert (
        distance_from_activities(
            activities, center=chengdu, radius_km=100.0
        ).activities
        == 0
    )
    assert (
        distance_from_activities(
            activities, center=chengdu, radius_km=200.0
        ).activities
        == 1
    )


def test_distance_from_activities_empty():
    report = distance_from_activities([])
    assert report == DistanceReport(total_km=0.0, activities=0, scanned=0)
