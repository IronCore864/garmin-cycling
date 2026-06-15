"""Command handlers for the Garmin Cycling CLI subcommands.

Each handler receives the parsed :class:`argparse.Namespace`, orchestrates
calls into the :mod:`garmin` library, and renders output via
:mod:`cli.reporting`.
"""

from __future__ import annotations

import argparse
import calendar
from datetime import date
from pathlib import Path

from garmin import load_config, make_cn_client
from garmin.laps import count_laps_in_directory
from garmin.workflow import run_workflow

from .reporting import (
    format_gear_report,
    format_lap_report,
    format_workflow_summary,
)


def run_sync(args: argparse.Namespace) -> None:
    result = run_workflow(vo2max_image_path=args.vo2max_image)
    print(format_workflow_summary(result))


def run_gear(args: argparse.Namespace) -> None:
    client = make_cn_client(load_config())
    print(f"Fetching cycling activities for {args.year}...")

    def _on_progress(done: int, total: int) -> None:
        if done % 10 == 0:
            print(f"  Processed {done}/{total} activities...")

    report = client.build_gear_report(args.year, on_progress=_on_progress)
    if report.total_rides == 0:
        print(f"No cycling activities found in {args.year}.")
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

    print(
        f"Found {len(activities)} activities. "
        f"Downloading as {args.format.upper()}...\n"
    )

    failures: list[tuple[str, str]] = []
    total_files = 0
    for i, activity in enumerate(activities, start=1):
        activity_id = activity.get("activityId")
        name = activity.get("activityName") or "activity"
        try:
            saved = client.download_activity_to_dir(
                activity, out_dir, fmt=args.format
            )
            total_files += len(saved)
            for p in saved:
                print(f"  [{i}/{len(activities)}] {p.name}")
        except Exception as exc:  # noqa: BLE001 -- report and continue per activity
            print(f"  [{i}/{len(activities)}] FAILED {activity_id} ({name}): {exc}")
            failures.append((str(activity_id), str(exc)))

    print(f"\nDone. Saved {total_files} file(s) to '{out_dir}'.")
    if failures:
        print(f"{len(failures)} activity(ies) failed:")
        for aid, err in failures:
            print(f"  - {aid}: {err}")
