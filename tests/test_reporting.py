"""Tests for cli.reporting text formatters."""

from datetime import date

from cli.reporting import (
    format_gear_report,
    format_lap_report,
    format_workflow_summary,
)
from garmin.gear import GearActivity, GearReport
from garmin.laps import LapResult


def test_format_workflow_summary_contains_sections():
    result = {
        "sync": [
            {
                "status": "synced",
                "activityName": "Morning Ride",
                "startTimeLocal": "2026-06-15 07:00:00",
                "detail": "Synced successfully.",
            }
        ],
        "vo2max": {"vo2max_precise": 55.2, "date": "2026-06-14"},
        "analytics": {1: (320.0, 165.0), 20: (270.0, 158.0)},
        "laps": 3,
        "vo2max_image": "vo2max_past_month.png",
    }
    text = format_workflow_summary(result)
    assert "Workflow Summary" in text
    assert "Morning Ride" in text
    assert "55.2" in text
    assert "3 circles" in text
    assert "vo2max_past_month.png" in text


def test_format_workflow_summary_handles_empty_and_errors():
    result = {
        "sync": None,
        "vo2max": None,
        "analytics": None,
        "laps": None,
        "vo2max_image": None,
        "errors": {"sync": "boom"},
    }
    text = format_workflow_summary(result)
    assert "(no activities synced)" in text
    assert "no data available" in text
    assert "unavailable" in text
    assert "boom" in text


def test_format_workflow_summary_single_circle_singular():
    text = format_workflow_summary({"laps": 1})
    assert "1 circle" in text
    assert "1 circles" not in text


def test_format_gear_report_contains_gear_and_totals():
    a = GearActivity(1, "Ride A", "2026-01-01 08:00", 10.0, 30.0, 20.0)
    b = GearActivity(2, "Ride B", "2026-01-02 08:00", 20.0, 60.0, 20.0)
    report = GearReport(year=2026, by_gear={"Road Bike": [a]}, no_gear=[b])
    text = format_gear_report(report)
    assert "2026 CYCLING ACTIVITIES BY GEAR" in text
    assert "Road Bike" in text
    assert "No Gear Assigned" in text
    assert "TOTAL: 2 rides" in text


def test_format_lap_report():
    results = [
        LapResult(date="2026-01-05", file="2026-01-05_1_x.fit", laps=2),
        LapResult(date="2026-01-20", file="2026-01-20_2_y.fit", laps=1),
    ]
    text = format_lap_report(date(2026, 1, 1), date(2026, 1, 31), results, scanned=5)
    assert "Scanned 5 FIT files" in text
    assert "2026-01-05  2 circles" in text
    assert "2026-01-20  1 circle" in text
    assert "Total: 3 circles from 2 activities" in text
