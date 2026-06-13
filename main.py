#!/usr/bin/env python3
"""Unified Garmin Cycling CLI.

Subcommands:
  sync      Run the full workflow: sync latest activities CN -> Global, fetch
            latest cycling VO2max, compute power/HR analytics, count lake
            circles, and generate a past-month cycling VO2max image.
  gear      List a year's cycling activities from Garmin CN, categorized by
            gear (bike), with per-gear and overall totals.
  download  Download activities in a date range as FIT or TCX files.

Credentials are read from the ``env`` file or environment variables:
  GARMIN_CN_EMAIL, GARMIN_CN_PASSWORD,
  GARMIN_GLOBAL_EMAIL, GARMIN_GLOBAL_PASSWORD
"""

import argparse
import io
import logging
import zipfile
from collections import defaultdict
from datetime import date
from pathlib import Path

from garmin import load_config, make_cn_client
from garmin.workflow import DEFAULT_VO2MAX_IMAGE, run_workflow

_STATUS_ICON = {
    "synced": "✓",
    "exists": "•",
    "error": "✗",
}


def _format_result(result: dict) -> str:
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


def _format_gear_report(year: int, gear_activities: dict, no_gear: list) -> str:
    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(f"  {year} CYCLING ACTIVITIES BY GEAR (BIKE)")
    lines.append("=" * 70)

    def _activity_lines(acts: list) -> None:
        for a in sorted(acts, key=lambda x: x["date"]):
            date_str = a["date"][:10] if a["date"] else "N/A"
            lines.append(
                f"   {date_str}  {a['name']:<30s}  "
                f"{a['distance_km']:>6.1f} km  "
                f"{a['duration_min']:>5.0f} min  "
                f"{a['avg_speed_kmh']:>4.1f} km/h"
            )

    for gear_name, acts in sorted(gear_activities.items()):
        total_distance = sum(a["distance_km"] for a in acts)
        total_duration = sum(a["duration_min"] for a in acts)
        lines.append("")
        lines.append(f"🚲 {gear_name}")
        lines.append(
            f"   Total rides: {len(acts)} | "
            f"Distance: {total_distance:.1f} km | "
            f"Duration: {total_duration:.0f} min"
        )
        lines.append(f"   {'─' * 60}")
        _activity_lines(acts)

    if no_gear:
        total_distance = sum(a["distance_km"] for a in no_gear)
        total_duration = sum(a["duration_min"] for a in no_gear)
        lines.append("")
        lines.append("⚠️  No Gear Assigned")
        lines.append(
            f"   Total rides: {len(no_gear)} | "
            f"Distance: {total_distance:.1f} km | "
            f"Duration: {total_duration:.0f} min"
        )
        lines.append(f"   {'─' * 60}")
        _activity_lines(no_gear)

    all_groups = list(gear_activities.values()) + [no_gear]
    total_rides = sum(len(acts) for acts in all_groups)
    total_km = sum(a["distance_km"] for acts in all_groups for a in acts)
    total_min = sum(a["duration_min"] for acts in all_groups for a in acts)
    lines.append("")
    lines.append("=" * 70)
    lines.append(
        f"  TOTAL: {total_rides} rides | "
        f"{total_km:.1f} km | "
        f"{total_min:.0f} min ({total_min / 60:.1f} hours)"
    )
    lines.append("=" * 70)
    return "\n".join(lines)


def _run_sync(args: argparse.Namespace) -> None:
    result = run_workflow(vo2max_image_path=args.vo2max_image)
    print(_format_result(result))


def _run_gear(args: argparse.Namespace) -> None:
    year = args.year
    client = make_cn_client(load_config())

    print(f"Fetching cycling activities for {year}...")
    activities = client.get_activities(
        f"{year}-01-01", f"{year}-12-31", activity_type="cycling"
    )

    if not activities:
        print(f"No cycling activities found in {year}.")
        return

    print(f"Found {len(activities)} cycling activities in {year}.\n")

    gear_activities: dict[str, list] = defaultdict(list)
    no_gear: list = []

    for i, activity in enumerate(activities):
        activity_id = activity.get("activityId")
        distance_m = activity.get("distance", 0)
        duration_s = activity.get("duration", 0)

        activity_info = {
            "id": activity_id,
            "name": activity.get("activityName", "Unnamed"),
            "date": activity.get("startTimeLocal", ""),
            "distance_km": round(distance_m / 1000, 2) if distance_m else 0,
            "duration_min": round(duration_s / 60, 1) if duration_s else 0,
            "avg_speed_kmh": (
                round((distance_m / 1000) / (duration_s / 3600), 1)
                if duration_s and distance_m
                else 0
            ),
        }

        gear_list = client.get_activity_gear(activity_id)
        if gear_list:
            for gear in gear_list:
                gear_name = (
                    gear.get("displayName")
                    or gear.get("customMakeModel")
                    or "Unknown Gear"
                )
                gear_activities[gear_name].append(activity_info)
        else:
            no_gear.append(activity_info)

        if (i + 1) % 10 == 0:
            print(f"  Processed {i + 1}/{len(activities)} activities...")

    print("\n" + _format_gear_report(year, gear_activities, no_gear))


def _safe_name(text: str) -> str:
    """Make a string safe to use in a filename."""
    keep = "-_. "
    cleaned = "".join(c if c.isalnum() or c in keep else "_" for c in text)
    return cleaned.strip().replace(" ", "_") or "activity"


def _save_fit(content: bytes, base_path: Path) -> list[Path]:
    """Save FIT content. The download is usually a ZIP holding .fit file(s)."""
    saved: list[Path] = []
    if content[:2] == b"PK":  # ZIP archive
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            for i, name in enumerate(names):
                suffix = Path(name).suffix or ".fit"
                out = base_path.with_suffix(suffix)
                if len(names) > 1:
                    out = base_path.with_name(f"{base_path.name}_{i}{suffix}")
                out.write_bytes(zf.read(name))
                saved.append(out)
    else:
        out = base_path.with_suffix(".fit")
        out.write_bytes(content)
        saved.append(out)
    return saved


def _run_download(args: argparse.Namespace) -> None:
    today = date.today()
    if args.all:
        start, end = "1970-01-01", today.isoformat()
    elif args.ytd:
        start, end = f"{today.year}-01-01", today.isoformat()
    else:
        start, end = args.start, args.end

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

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
        start_time = activity.get("startTimeLocal", "")
        date_str = start_time[:10] if start_time else "nodate"

        base_name = f"{date_str}_{activity_id}_{_safe_name(name)}"
        base_path = out_dir / base_name

        try:
            content = client.download_activity(activity_id, fmt=args.format)
            if args.format == "fit":
                saved = _save_fit(content, base_path)
            else:
                out = base_path.with_suffix(".tcx")
                out.write_bytes(content)
                saved = [out]
            total_files += len(saved)
            for p in saved:
                print(f"  [{i}/{len(activities)}] {p.name}")
        except Exception as e:  # noqa: BLE001
            print(f"  [{i}/{len(activities)}] FAILED {activity_id} ({name}): {e}")
            failures.append((str(activity_id), str(e)))

    print(f"\nDone. Saved {total_files} file(s) to '{out_dir}'.")
    if failures:
        print(f"{len(failures)} activity(ies) failed:")
        for aid, err in failures:
            print(f"  - {aid}: {err}")


def main() -> None:
    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(description="Garmin Cycling CLI.")
    subparsers = parser.add_subparsers(dest="command")

    sync_parser = subparsers.add_parser(
        "sync", help="Run the full sync + analysis workflow."
    )
    sync_parser.add_argument(
        "--vo2max-image",
        default=DEFAULT_VO2MAX_IMAGE,
        help="Output path for the past-month cycling VO2max image.",
    )
    sync_parser.set_defaults(func=_run_sync)

    gear_parser = subparsers.add_parser(
        "gear", help="List a year's cycling activities categorized by gear."
    )
    gear_parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year to report on (default: current year).",
    )
    gear_parser.set_defaults(func=_run_gear)

    download_parser = subparsers.add_parser(
        "download", help="Download activities in a date range as FIT or TCX."
    )
    download_parser.add_argument(
        "--start", default="2026-01-01", help="Start date YYYY-MM-DD (inclusive)."
    )
    download_parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (inclusive, default: today).",
    )
    download_parser.add_argument(
        "--format",
        choices=["fit", "tcx"],
        default="fit",
        help="Download format (default: fit).",
    )
    download_parser.add_argument(
        "--out", default="downloads", help="Output directory."
    )
    download_parser.add_argument(
        "--all",
        action="store_true",
        help="Download all activities from the beginning to today "
        "(overrides --start/--end).",
    )
    download_parser.add_argument(
        "--ytd",
        action="store_true",
        help="Download activities from Jan 1 of this year to today "
        "(overrides --start/--end).",
    )
    download_parser.add_argument(
        "--type",
        default=None,
        help="Optional activity type filter (e.g. cycling, running).",
    )
    download_parser.set_defaults(func=_run_download)

    args = parser.parse_args()

    # Require an explicit subcommand; show help and exit otherwise.
    if not getattr(args, "command", None):
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
