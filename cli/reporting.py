"""Plain-text formatters for rendering results as console reports.

These functions are pure: they take already-computed data structures
(produced by :mod:`garmin.workflow`, :mod:`garmin.gear` and
:mod:`garmin.laps`) and return strings. They live in the ``cli`` package
because the formatting (ASCII boxes, emoji, fixed-width columns) is specific
to console output; the ``garmin`` library stays free of presentation concerns.
"""

from __future__ import annotations

from datetime import date

from garmin.gear import GearReport
from garmin.laps import LapResult

_STATUS_ICON = {
    "synced": "✓",
    "exists": "•",
    "error": "✗",
}


def format_workflow_summary(result: dict) -> str:
    """Render the :func:`garmin.workflow.run_workflow` result as text."""
    lines: list[str] = []
    lines.append("=" * 48)
    lines.append("Garmin Cycling - Workflow Summary")
    lines.append("=" * 48)

    # 1. Sync
    lines.append("")
    lines.append("Sync (Garmin CN -> Global):")
    sync = result.get("sync")
    if not sync:
        lines.append("  (no activities synced)")
    else:
        for item in sync:
            icon = _STATUS_ICON.get(item.get("status"), "?")
            name = item.get("activityName") or "Unnamed activity"
            when = item.get("startTimeLocal") or ""
            detail = item.get("detail") or item.get("status") or ""
            lines.append(f"  {icon} {name} ({when})")
            lines.append(f"      {detail}")

    # 2. VO2max
    lines.append("")
    vo2 = result.get("vo2max")
    if vo2:
        lines.append(
            f"Latest cycling VO2max: {vo2.get('vo2max_precise')} "
            f"(on {vo2.get('date')})"
        )
    else:
        lines.append("Latest cycling VO2max: no data available")

    # 3. Analytics (max average power + corresponding HR by duration)
    lines.append("")
    analytics = result.get("analytics")
    if analytics:
        lines.append("Power analytics (latest activity):")
        lines.append(f"  {'Duration':>10s}  {'Max Avg Power':>14s}  {'Avg HR':>7s}")
        for duration in sorted(analytics):
            power, hr = analytics[duration]
            label = f"{duration} min"
            power_str = f"{power:.0f} W" if power is not None else "N/A"
            hr_str = f"{hr:.0f} bpm" if hr is not None else "N/A"
            lines.append(f"  {label:>10s}  {power_str:>14s}  {hr_str:>7s}")
    else:
        lines.append("Power analytics (latest activity): no power/HR data")

    # 4. Laps
    lines.append("")
    laps = result.get("laps")
    if laps is None:
        lines.append("Lake circles (latest activity): unavailable")
    else:
        unit = "circle" if laps == 1 else "circles"
        lines.append(f"Lake circles (latest activity): {laps} {unit}")

    # 5. VO2max image
    lines.append("")
    image = result.get("vo2max_image")
    if image:
        lines.append(f"VO2max image (past month): saved to {image}")
    else:
        lines.append("VO2max image (past month): not generated (no data)")

    # Errors
    errors = result.get("errors")
    if errors:
        lines.append("")
        lines.append("Warnings (some steps failed):")
        for step, msg in errors.items():
            lines.append(f"  ✗ {step}: {msg}")

    lines.append("")
    lines.append("=" * 48)
    return "\n".join(lines)


def format_gear_report(report: GearReport) -> str:
    """Render a :class:`garmin.gear.GearReport` as text."""
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"  {report.year} CYCLING ACTIVITIES BY GEAR (BIKE)")
    lines.append("=" * 70)

    def _activity_lines(activities) -> None:
        for a in sorted(activities, key=lambda x: x.date):
            date_str = a.date[:10] if a.date else "N/A"
            lines.append(
                f"   {date_str}  {a.name:<30s}  "
                f"{a.distance_km:>6.1f} km  "
                f"{a.duration_min:>5.0f} min  "
                f"{a.avg_speed_kmh:>4.1f} km/h"
            )

    def _group_header(label: str, activities) -> None:
        total_distance = sum(a.distance_km for a in activities)
        total_duration = sum(a.duration_min for a in activities)
        lines.append("")
        lines.append(label)
        lines.append(
            f"   Total rides: {len(activities)} | "
            f"Distance: {total_distance:.1f} km | "
            f"Duration: {total_duration:.0f} min"
        )
        lines.append(f"   {'─' * 60}")
        _activity_lines(activities)

    for gear_name, activities in sorted(report.by_gear.items()):
        _group_header(f"🚲 {gear_name}", activities)

    if report.no_gear:
        _group_header("⚠️  No Gear Assigned", report.no_gear)

    lines.append("")
    lines.append("=" * 70)
    lines.append(
        f"  TOTAL: {report.total_rides} rides | "
        f"{report.total_distance_km:.1f} km | "
        f"{report.total_duration_min:.0f} min "
        f"({report.total_duration_min / 60:.1f} hours)"
    )
    lines.append("=" * 70)
    return "\n".join(lines)


def format_lap_report(
    start: date,
    end: date,
    results: list[LapResult],
    scanned: int,
) -> str:
    """Render lake-lap counts from :func:`garmin.laps.count_laps_in_directory`."""
    lines: list[str] = []
    lines.append(f"Scanned {scanned} FIT files from {start} to {end}...")
    lines.append("")
    for r in results:
        unit = "circle" if r.laps == 1 else "circles"
        lines.append(f"  {r.date}  {r.laps} {unit}")
    total_laps = sum(r.laps for r in results)
    lines.append("")
    lines.append(
        f"Total: {total_laps} circles from {len(results)} activities "
        f"({start} to {end})"
    )
    return "\n".join(lines)
