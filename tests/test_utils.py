"""Tests for garmin._utils pure helpers."""

from datetime import date

from garmin._utils import (
    activity_in_range,
    parse_date,
    safe_filename,
    to_date_str,
)


def test_to_date_str_from_date():
    assert to_date_str(date(2026, 1, 2)) == "2026-01-02"


def test_to_date_str_passthrough_string():
    assert to_date_str("2026-03-04") == "2026-03-04"


def test_parse_date_from_string():
    assert parse_date("2026-05-06") == date(2026, 5, 6)


def test_parse_date_passthrough_date():
    d = date(2026, 7, 8)
    assert parse_date(d) is d


def test_activity_in_range_inside():
    activity = {"startTimeLocal": "2026-06-15 08:00:00"}
    assert activity_in_range(activity, date(2026, 6, 1), date(2026, 6, 30))


def test_activity_in_range_outside():
    activity = {"startTimeLocal": "2026-07-01 08:00:00"}
    assert not activity_in_range(activity, date(2026, 6, 1), date(2026, 6, 30))


def test_activity_in_range_missing_or_bad():
    assert not activity_in_range({}, date(2026, 1, 1), date(2026, 12, 31))
    assert not activity_in_range(
        {"startTimeLocal": "not-a-date"}, date(2026, 1, 1), date(2026, 12, 31)
    )


def test_safe_filename_replaces_unsafe_chars():
    assert safe_filename("Morning Ride #1 @Lake!") == "Morning_Ride__1__Lake_"


def test_safe_filename_keeps_allowed_chars():
    assert safe_filename("ride-2026_01.02") == "ride-2026_01.02"


def test_safe_filename_empty_fallback():
    assert safe_filename("") == "activity"
    assert safe_filename("   ") == "activity"  # stripped to empty


def test_safe_filename_unsafe_only_becomes_underscores():
    # Non-empty result is kept as-is (only an empty result falls back).
    assert safe_filename("///") == "___"
