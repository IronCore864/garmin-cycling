"""Plain-text formatters for rendering results as console reports.

These functions are pure: they take already-computed data structures
(produced by :mod:`garmin.workflow`, :mod:`garmin.gear` and
:mod:`garmin.laps`) and return strings. They live in the ``cli`` package
because the formatting (ASCII boxes, emoji, fixed-width columns) is specific
to console output; the ``garmin`` library stays free of presentation concerns.
"""

from __future__ import annotations

from datetime import date

from garmin.badges import compute_badge_stats, sort_badges
from garmin.gear import GearReport
from garmin.laps import LapResult
from garmin.power import RideAnalysis
from garmin.training_load import ReadinessReport

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

    # 3b. Ride analysis (decoupling, critical power/W', coasting)
    lines.append("")
    ride = result.get("ride_analysis")
    if ride is None:
        lines.append("Ride analysis (latest activity): unavailable")
    else:
        lines.append("Ride analysis (latest activity):")
        dec = ride.decoupling
        if dec is None:
            lines.append("  Decoupling: n/a")
        else:
            verdict = "coupled" if dec.is_coupled else "decoupled"
            lines.append(
                f"  Decoupling: {dec.decoupling_pct:.1f}% ({verdict})   "
                f"EF: {dec.efficiency_factor:.2f}"
            )
        cp = ride.critical_power
        if cp is None:
            lines.append("  Critical power: n/a")
        else:
            cp_kg = f" ({cp.cp_per_kg:.2f} W/kg)" if cp.cp_per_kg is not None else ""
            lines.append(
                f"  CP: {cp.cp_watts:.0f} W{cp_kg}   W': {cp.w_prime_kj:.1f} kJ   "
                f"{cp.phenotype}"
            )
        co = ride.coasting
        if co is None:
            lines.append("  Coasting: n/a")
        else:
            lines.append(
                f"  Coasting: {co.coasting_pct:.1f}% of moving   "
                f"Longest: {co.longest_coast_s:.0f} s"
            )

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


def format_ride_analysis(filename: str, analysis: RideAnalysis) -> str:
    """Render a :class:`garmin.power.RideAnalysis` as a console report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append(f"Ride Analysis - {filename}")
    lines.append("=" * 60)
    power_flag = "yes" if analysis.has_power else "no"
    hr_flag = "yes" if analysis.has_hr else "no"
    lines.append(
        f"Duration: {analysis.duration_min:.1f} min  |  "
        f"power: {power_flag}  |  HR: {hr_flag}"
    )

    # 1. Aerobic decoupling + efficiency factor
    lines.append("")
    lines.append("Aerobic decoupling (Pw:Hr):")
    dec = analysis.decoupling
    if dec is None:
        lines.append("  not available (needs continuous power + HR over >= 10 min)")
    else:
        verdict = "coupled" if dec.is_coupled else "decoupled"
        lines.append(
            f"  Efficiency factor (NP/HR): {dec.efficiency_factor:.2f} "
            f"(NP {dec.np_watts:.0f} W / HR {dec.avg_hr:.0f} bpm)"
        )
        lines.append(
            f"  First half: {dec.first_half_ratio:.3f} W/bpm   "
            f"Second half: {dec.second_half_ratio:.3f} W/bpm"
        )
        lines.append(
            f"  Decoupling: {dec.decoupling_pct:.1f}% ({verdict}; "
            "<= 5% indicates good aerobic durability)"
        )

    # 2. Critical power / W' + rider phenotype
    lines.append("")
    lines.append("Critical power model (single-ride estimate):")
    cp = analysis.critical_power
    if cp is None:
        lines.append(
            "  not available (needs >= 3 near-maximal efforts between 2-20 min)"
        )
    else:
        cp_kg = f" ({cp.cp_per_kg:.2f} W/kg)" if cp.cp_per_kg is not None else ""
        lines.append(f"  CP: {cp.cp_watts:.0f} W{cp_kg}   W': {cp.w_prime_kj:.1f} kJ")
        lines.append(
            f"  Fit: r2={cp.r_squared:.3f} over {cp.n_points} efforts (2-20 min)"
        )
        lines.append(f"  Phenotype: {cp.phenotype}")
        lines.append(
            "  Note: only meaningful if the ride included hard efforts across "
            "these durations."
        )

    # 5. Coasting / pedaling breakdown
    lines.append("")
    lines.append("Coasting / pedaling:")
    co = analysis.coasting
    if co is None:
        lines.append("  not available (needs cadence or power)")
    else:
        lines.append(
            f"  Moving: {co.moving_s / 60:.1f} min   "
            f"Stopped: {co.stopped_s / 60:.1f} min"
        )
        lines.append(
            f"  Pedaling: {co.pedaling_s / 60:.1f} min ({co.pedaling_pct:.1f}%)   "
            f"Coasting: {co.coasting_s / 60:.1f} min ({co.coasting_pct:.1f}%)"
        )
        lines.append(f"  Longest coast: {co.longest_coast_s:.0f} s")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_readiness_report(report: ReadinessReport) -> str:
    """Render a :class:`garmin.training_load.ReadinessReport` as text."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Training Load & Readiness")
    lines.append("=" * 60)
    source_label = {
        "local": "local downloads",
        "online": "Garmin CN (online)",
    }.get(report.source, report.source)
    lines.append(
        f"Window: {report.start} to {report.end}  "
        f"({report.scanned} activities, source: {source_label})"
    )

    if report.latest is None or report.recommendation is None:
        lines.append("")
        lines.append("No usable data in range.")
        lines.append("=" * 60)
        return "\n".join(lines)

    # Recent daily trend (last 14 days of the series).
    lines.append("")
    lines.append("Recent trend (Fitness/Fatigue/Form + ACWR):")
    lines.append(
        f"  {'Date':>10s}  {'Load':>5s}  {'Fit':>5s}  {'Fatig':>5s}  "
        f"{'Form':>5s}  {'ACWR':>5s}"
    )
    for m in report.days[-14:]:
        acwr_str = f"{m.acwr:.2f}" if m.acwr is not None else "  -"
        lines.append(
            f"  {m.day.isoformat():>10s}  {m.load:>5d}  {m.ctl:>5.0f}  "
            f"{m.atl:>5.0f}  {m.tsb:>5.0f}  {acwr_str:>5s}"
        )

    latest = report.latest
    rec = report.recommendation
    acwr_str = f"{latest.acwr:.2f}" if latest.acwr is not None else "n/a"
    lines.append("")
    lines.append(f"As of {latest.day.isoformat()}:")
    lines.append(
        f"  Fitness (CTL): {latest.ctl:.0f}   Fatigue (ATL): {latest.atl:.0f}   "
        f"Form (TSB): {latest.tsb:.0f}   ACWR: {acwr_str}"
    )
    flag = "  [CAUTION: load spiking]" if rec.caution else ""
    lines.append(f"  Recommendation: {rec.recommendation.upper()}{flag}")
    lines.append(f"  {rec.rationale}")

    lines.append("")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_badge_summary(badges: list[dict]) -> str:
    """Render a text summary of earned badges."""
    stats = compute_badge_stats(badges)
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("Garmin Badges - Summary")
    lines.append("=" * 60)
    lines.append(f"Total earned : {stats.total_badges} (counting repeats)")
    lines.append(f"Unique       : {stats.unique_badges}")
    lines.append(f"Total points : {stats.total_points}")
    lines.append(f"Earned span  : {stats.date_span}")

    top = sort_badges(badges, by="points")[:5]
    if top:
        lines.append("")
        lines.append("Highest-value badges:")
        for b in top:
            name = b.get("badgeName") or "Unnamed badge"
            pts = int(b.get("badgePoints") or 0)
            lines.append(f"  {pts:>3d} pts  {name}")

    repeated = [b for b in badges if int(b.get("badgeEarnedNumber") or 1) > 1]
    repeated.sort(key=lambda b: int(b.get("badgeEarnedNumber") or 1), reverse=True)
    if repeated:
        lines.append("")
        lines.append("Most-repeated badges:")
        for b in repeated[:5]:
            name = b.get("badgeName") or "Unnamed badge"
            times = int(b.get("badgeEarnedNumber") or 1)
            lines.append(f"  x{times:<3d}  {name}")

    lines.append("=" * 60)
    return "\n".join(lines)
