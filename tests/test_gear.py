"""Tests for garmin.gear value objects and grouping logic."""

from garmin.gear import GearActivity, GearMixin, GearReport, _gear_name


def test_gear_activity_from_activity_computes_derived_fields():
    activity = {
        "activityId": 42,
        "activityName": "Lunch Ride",
        "startTimeLocal": "2026-06-15 12:00:00",
        "distance": 20000,  # metres
        "duration": 3600,  # seconds
    }
    ga = GearActivity.from_activity(activity)
    assert ga.id == 42
    assert ga.name == "Lunch Ride"
    assert ga.distance_km == 20.0
    assert ga.duration_min == 60.0
    assert ga.avg_speed_kmh == 20.0


def test_gear_activity_from_activity_handles_missing_fields():
    ga = GearActivity.from_activity({})
    assert ga.name == "Unnamed"
    assert ga.distance_km == 0
    assert ga.duration_min == 0
    assert ga.avg_speed_kmh == 0


def test_gear_name_prefers_display_name():
    assert _gear_name({"displayName": "Trek", "customMakeModel": "X"}) == "Trek"
    assert _gear_name({"customMakeModel": "Canyon"}) == "Canyon"
    assert _gear_name({}) == "Unknown Gear"


def test_gear_report_totals():
    a = GearActivity(1, "A", "2026-01-01", 10.0, 30.0, 20.0)
    b = GearActivity(2, "B", "2026-01-02", 20.0, 60.0, 20.0)
    c = GearActivity(3, "C", "2026-01-03", 5.0, 15.0, 20.0)
    report = GearReport(year=2026, by_gear={"Bike": [a, b]}, no_gear=[c])
    assert report.total_rides == 3
    assert report.total_distance_km == 35.0
    assert report.total_duration_min == 105.0


class _FakeGearClient(GearMixin):
    """A GearMixin with the two endpoints it depends on stubbed out."""

    def __init__(self, activities, gear_by_activity):
        self._activities = activities
        self._gear_by_activity = gear_by_activity

    def get_activities(self, start_date, end_date=None, activity_type=None):
        return self._activities

    def get_activity_gear(self, activity_id):
        return self._gear_by_activity.get(activity_id, [])


def test_build_gear_report_groups_by_gear_and_no_gear():
    activities = [
        {"activityId": 1, "activityName": "R1", "distance": 10000, "duration": 1800},
        {"activityId": 2, "activityName": "R2", "distance": 20000, "duration": 3600},
        {"activityId": 3, "activityName": "R3", "distance": 5000, "duration": 900},
    ]
    gear_by_activity = {
        1: [{"displayName": "Road Bike"}],
        2: [{"displayName": "Road Bike"}],
        3: [],  # no gear
    }
    client = _FakeGearClient(activities, gear_by_activity)

    report = client.build_gear_report(2026)
    assert set(report.by_gear) == {"Road Bike"}
    assert len(report.by_gear["Road Bike"]) == 2
    assert len(report.no_gear) == 1
    assert report.total_rides == 3


def test_build_gear_report_invokes_progress_callback():
    activities = [
        {"activityId": i, "activityName": f"R{i}", "distance": 1000, "duration": 600}
        for i in range(3)
    ]
    client = _FakeGearClient(activities, {})
    seen = []
    client.build_gear_report(
        2026, on_progress=lambda done, total: seen.append((done, total))
    )
    assert seen == [(1, 3), (2, 3), (3, 3)]
