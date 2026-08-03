"""Command handlers for the Garmin Cycling CLI subcommands.

Each handler receives the parsed :class:`argparse.Namespace`, orchestrates
calls into the :mod:`garmin` library, and renders output via
:mod:`cli.reporting`.
"""

from __future__ import annotations

import argparse
import calendar
from dataclasses import replace
from datetime import date
from pathlib import Path

from garmin import calculate_zones, format_zones, load_config, make_cn_client
from garmin._utils import safe_filename
from garmin.config import load_athlete_profile
from garmin.distance import distance_from_activities, distance_in_directory
from garmin.geo import resolve_city_center
from garmin.heatmap import build_heatmap_html, load_tracks
from garmin.laps import count_laps_in_directory
from garmin.power import analyze_ride
from garmin.training_load import analyze_readiness
from garmin.workflow import run_workflow

from .reporting import (
    format_badge_summary,
    format_distance_report,
    format_gear_report,
    format_heatmap_summary,
    format_lap_report,
    format_readiness_report,
    format_ride_analysis,
    format_workflow_summary,
)


def run_sync(args: argparse.Namespace) -> None:
    result = run_workflow(vo2max_image_path=args.vo2max_image)
    print(format_workflow_summary(result))


def _resolve_gear_date_range(args: argparse.Namespace) -> tuple[date, date]:
    """Resolve the gear command's date range from year/start/end flags."""
    if args.start:
        return date.fromisoformat(args.start), date.fromisoformat(args.end)
    year = args.year or date.today().year
    return date(year, 1, 1), date(year, 12, 31)


def run_gear(args: argparse.Namespace) -> None:
    start, end = _resolve_gear_date_range(args)
    client = make_cn_client(load_config())
    print(f"Fetching cycling activities from {start} to {end}...")

    def _on_progress(done: int, total: int) -> None:
        print(f"  Checked {done}/{total} bikes...")

    report = client.build_gear_report(start, end, on_progress=_on_progress)
    if report.total_rides == 0:
        print(f"No cycling activities found from {start} to {end}.")
        return
    print("\n" + format_gear_report(report))


def _resolve_lap_date_range(args: argparse.Namespace) -> tuple[date, date]:
    """Resolve the laps command's date range from year/month/start/end flags."""
    today = date.today()
    if args.year and args.month:
        last_day = calendar.monthrange(args.year, args.month)[1]
        return date(args.year, args.month, 1), date(args.year, args.month, last_day)
    if args.year:
        return date(args.year, 1, 1), date(args.year, 12, 31)
    if args.month:
        last_day = calendar.monthrange(today.year, args.month)[1]
        return (
            date(today.year, args.month, 1),
            date(today.year, args.month, last_day),
        )
    return date.fromisoformat(args.start), date.fromisoformat(args.end)


def run_laps(args: argparse.Namespace) -> None:
    start, end = _resolve_lap_date_range(args)
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"Directory not found: {directory}")
        return

    results, scanned = count_laps_in_directory(directory, start, end)
    if scanned == 0:
        print(f"No FIT files found in {directory} for {start} to {end}.")
        return
    print(format_lap_report(start, end, results, scanned))


def _heatmap_output_name(city: str | None, year: int | None) -> str:
    """Default heatmap filename derived from the active city/year filters."""
    parts: list[str] = []
    if city:
        parts.append(safe_filename(city).lower())
    if year is not None:
        parts.append(str(year))
    return f"{'_'.join(parts) if parts else 'heatmap'}.html"


def run_heatmap(args: argparse.Namespace) -> None:
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"Directory not found: {directory}")
        return

    scope = " ".join(
        str(s) for s in (args.year, args.city) if s is not None
    )
    print(f"Loading GPS tracks from {directory} (parsing FIT files)...")

    def _on_progress(done: int, total: int) -> None:
        if done == total or done % 25 == 0:
            print(f"  Resolved {done}/{total} FIT files...")

    tracks = load_tracks(
        directory,
        year=args.year,
        city=args.city,
        max_points=args.max_points,
        radius_km=args.radius,
        allow_geocode=not args.no_geocode,
        on_progress=_on_progress,
        use_cache=not args.no_cache,
    )
    if not tracks:
        where = f" for {scope}" if scope else ""
        print(f"No GPS tracks found in {directory}{where}.")
        return

    out_path = args.out or _heatmap_output_name(args.city, args.year)
    print(f"Rendering heatmap for {len(tracks)} activities...")
    out = build_heatmap_html(tracks, out_path)
    print(format_heatmap_summary(tracks, out))


def run_distance(args: argparse.Namespace) -> None:
    center = None
    geo_filtered = True
    if args.city:
        center = resolve_city_center(args.city, allow_network=not args.no_geocode)
        geo_filtered = center is not None
        if not geo_filtered:
            print(f"Could not resolve a centre for '{args.city}'.")

    if args.local:
        report = _distance_local(args, center)
    else:
        report = _distance_from_api(args, center)
    if report is None:
        return

    print(
        format_distance_report(
            report,
            city=args.city,
            year=args.year,
            radius_km=args.radius,
            geo_filtered=geo_filtered,
        )
    )


def _distance_from_api(
    args: argparse.Namespace, center: tuple[float, float] | None
):
    """Total distance from the Garmin activity list (fast: one paged request)."""
    if args.year:
        start, end = f"{args.year}-01-01", f"{args.year}-12-31"
    else:
        start, end = "1970-01-01", date.today().isoformat()

    client = make_cn_client(load_config())
    print(f"Fetching activities {start} to {end} from Garmin...")
    activities = client.get_activities(
        start, end, activity_type=args.type or None
    )
    print(f"Summing distance over {len(activities)} activities...")
    return distance_from_activities(
        activities, center=center, radius_km=args.radius
    )


def _distance_local(args: argparse.Namespace, center: tuple[float, float] | None):
    """Total distance from local FIT files (offline, parsed in parallel)."""
    directory = Path(args.dir)
    if not directory.is_dir():
        print(f"Directory not found: {directory}")
        return None

    print(f"Reading distances from FIT files in {directory}...")

    def _on_progress(done: int, total: int) -> None:
        if done == total or done % 50 == 0:
            print(f"  Processed {done}/{total} activities...")

    return distance_in_directory(
        directory,
        center=center,
        radius_km=args.radius,
        year=args.year,
        on_progress=_on_progress,
    )


def _downloaded_activity_ids(out_dir: Path) -> set[str]:
    """Activity IDs already present in ``out_dir``.

    Downloads are named ``{date}_{activityId}_{safe-name}.{ext}``, so the ID is
    the token between the first two underscores.
    """
    ids: set[str] = set()
    if not out_dir.is_dir():
        return ids
    for path in out_dir.iterdir():
        if not path.is_file():
            continue
        parts = path.name.split("_")
        if len(parts) >= 2 and parts[1].isdigit():
            ids.add(parts[1])
    return ids


def run_download(args: argparse.Namespace) -> None:
    today = date.today()
    if args.all:
        start, end = "1970-01-01", today.isoformat()
    elif args.ytd:
        start, end = f"{today.year}-01-01", today.isoformat()
    else:
        start, end = args.start, args.end

    out_dir = Path(args.out)
    client = make_cn_client(load_config())

    print(f"Fetching activities {start} to {end}...")
    activities = client.get_activities(start, end, activity_type=args.type)
    if not activities:
        print("No activities found in the given date range.")
        return

    existing = set() if args.force else _downloaded_activity_ids(out_dir)
    pending = [a for a in activities if str(a.get("activityId")) not in existing]
    skipped = len(activities) - len(pending)

    if not pending:
        print(
            f"Found {len(activities)} activities; all already downloaded "
            f"in '{out_dir}'. Nothing to do."
        )
        return

    print(
        f"Found {len(activities)} activities "
        f"({skipped} already downloaded, {len(pending)} to fetch). "
        f"Downloading as {args.format.upper()}...\n"
    )

    failures: list[tuple[str, str]] = []
    total_files = 0
    for i, activity in enumerate(pending, start=1):
        activity_id = activity.get("activityId")
        name = activity.get("activityName") or "activity"
        try:
            saved = client.download_activity_to_dir(
                activity, out_dir, fmt=args.format
            )
            total_files += len(saved)
            for p in saved:
                print(f"  [{i}/{len(pending)}] {p.name}")
        except Exception as exc:  # noqa: BLE001 -- report and continue per activity
            print(f"  [{i}/{len(pending)}] FAILED {activity_id} ({name}): {exc}")
            failures.append((str(activity_id), str(exc)))

    print(f"\nDone. Saved {total_files} file(s) to '{out_dir}'.")
    if skipped:
        print(f"Skipped {skipped} already-downloaded activity(ies).")
    if failures:
        print(f"{len(failures)} activity(ies) failed:")
        for aid, err in failures:
            print(f"  - {aid}: {err}")


def run_readiness(args: argparse.Namespace) -> None:
    profile = load_athlete_profile()
    # Apply CLI overrides (only when provided) on top of configured values.
    overrides = {
        k: v
        for k, v in (
            ("resting_hr", args.resting_hr),
            ("max_hr", args.max_hr),
            ("sex", args.sex),
            ("age", args.age),
        )
        if v is not None
    }
    if overrides:
        profile = replace(profile, **overrides)

    def _client_factory():
        return make_cn_client(load_config())

    try:
        report = analyze_readiness(profile, client_factory=_client_factory)
    except RuntimeError as exc:
        print(f"Cannot assess readiness: {exc}")
        return

    if report.scanned == 0:
        print("No recent activities found to assess readiness.")
        return
    print(format_readiness_report(report))


def run_zones(args: argparse.Namespace) -> None:
    try:
        zones = calculate_zones(args.fthr)
    except TypeError as exc:
        print(str(exc))
        return
    print(f"Heart-rate zones for FTHR {args.fthr:.0f} bpm:")
    print(format_zones(zones))


def run_analyze(args: argparse.Namespace) -> None:
    import fitparse

    path = Path(args.file)
    if not path.is_file():
        print(f"File not found: {path}")
        return
    try:
        fitfile = fitparse.FitFile(str(path))
    except Exception as exc:  # noqa: BLE001 -- report unreadable/corrupt files
        print(f"Could not read FIT file '{path}': {exc}")
        return

    analysis = analyze_ride(fitfile, weight_kg=args.weight)
    print(format_ride_analysis(path.name, analysis))


def run_weight(args: argparse.Namespace) -> None:
    client = make_cn_client(load_config())
    start, end = args.start, args.end

    print(f"Fetching weight data {start} to {end}...")
    records = client.get_weight_range(start, end)
    if not records:
        print("No weight data found in the given date range.")
        return

    out = client.plot_weight(args.out, start, end)
    first, last = records[0], records[-1]
    print(
        f"Found {len(records)} weigh-ins "
        f"({first['Date']}: {first['Weight']:.1f} kg "
        f"-> {last['Date']}: {last['Weight']:.1f} kg)."
    )
    print(f"Saved weight graph to '{out}'.")


def run_badges(args: argparse.Namespace) -> None:
    client = make_cn_client(load_config())

    print("Fetching earned badges...")
    badges = client.get_earned_badges()
    if not badges:
        print("No earned badges found.")
        return

    print(f"Found {len(badges)} badges. Downloading artwork and building poster...")
    out = client.plot_badges(
        args.out,
        style=args.style,
        sort_by=args.sort,
        columns=args.columns,
        res=args.res,
    )
    print("\n" + format_badge_summary(badges))
    if out:
        print(f"\nSaved badges poster to '{out}'.")
    else:
        print("\nCould not render the badges poster.")
