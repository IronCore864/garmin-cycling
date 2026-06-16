"""Tests for cli.reporting text formatters."""

from datetime import date

from cli.reporting import (
    format_gear_report,
    format_lap_report,
    format_ride_analysis,
    format_workflow_summary,
)
from garmin.gear import GearActivity, GearReport
from garmin.laps import LapResult
from garmin.power import Coasting, CriticalPower, Decoupling, RideAnalysis


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
        "ride_analysis": RideAnalysis(
            duration_min=60.0,
            has_power=True,
            has_hr=True,
            decoupling=Decoupling(1.70, 210.0, 124.0, 1.75, 1.66, 5.1),
            critical_power=CriticalPower(250.0, 18000.0, 0.98, 6, "All-rounder", 3.5),
            coasting=Coasting(3600.0, 3400.0, 200.0, 3000.0, 400.0, 60.0),
        ),
        "laps": 3,
        "vo2max_image": "vo2max_past_month.png",
    }
    text = format_workflow_summary(result)
    assert "Workflow Summary" in text
    assert "Morning Ride" in text
    assert "55.2" in text
    assert "3 circles" in text
    assert "vo2max_past_month.png" in text
    assert "Ride analysis (latest activity):" in text
    assert "Decoupling: 5.1%" in text
    assert "CP: 250 W" in text
    assert "All-rounder" in text


def test_format_workflow_summary_handles_empty_and_errors():
    result = {
        "sync": None,
        "vo2max": None,
        "analytics": None,
        "ride_analysis": None,
        "laps": None,
        "vo2max_image": None,
        "errors": {"sync": "boom"},
    }
    text = format_workflow_summary(result)
    assert "(no activities synced)" in text
    assert "no data available" in text
    assert "unavailable" in text
    assert "Ride analysis (latest activity): unavailable" in text
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


def test_format_ride_analysis_full():
    analysis = RideAnalysis(
        duration_min=73.5,
        has_power=True,
        has_hr=True,
        decoupling=Decoupling(1.72, 218.0, 127.0, 1.78, 1.69, 4.8),
        critical_power=CriticalPower(256.0, 18400.0, 0.992, 7, "All-rounder", 3.66),
        coasting=Coasting(4410.0, 4090.0, 320.0, 3655.0, 435.0, 95.0),
    )
    text = format_ride_analysis("ride.fit", analysis)
    assert "Ride Analysis - ride.fit" in text
    assert "73.5 min" in text
    assert "Decoupling: 4.8%" in text
    assert "coupled" in text
    assert "CP: 256 W (3.66 W/kg)" in text
    assert "18.4 kJ" in text
    assert "All-rounder" in text
    assert "Coasting:" in text


def test_format_ride_analysis_missing_sections():
    analysis = RideAnalysis(
        duration_min=12.0,
        has_power=False,
        has_hr=False,
        decoupling=None,
        critical_power=None,
        coasting=None,
    )
    text = format_ride_analysis("nodata.fit", analysis)
    assert "power: no" in text
    assert text.count("not available") == 3
