"""Argument-parser construction for the Garmin Cycling CLI."""

from __future__ import annotations

import argparse
from datetime import date

from garmin.workflow import DEFAULT_VO2MAX_IMAGE

from .commands import (
    run_analyze,
    run_badges,
    run_download,
    run_gear,
    run_heatmap,
    run_laps,
    run_readiness,
    run_sync,
    run_weight,
    run_zones,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argument parser with all subcommands wired up."""
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
    sync_parser.set_defaults(func=run_sync)

    gear_parser = subparsers.add_parser(
        "gear",
        help="List cycling activities categorized by gear, for a year or a "
        "date range.",
    )
    gear_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Report on a full calendar year (default: current year unless "
        "--start is given).",
    )
    gear_parser.add_argument(
        "--start",
        default=None,
        help="Start date YYYY-MM-DD (inclusive). Overrides --year.",
    )
    gear_parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (inclusive, default: today). Used with --start.",
    )
    gear_parser.set_defaults(func=run_gear)

    laps_parser = subparsers.add_parser(
        "laps", help="Count lake laps from local FIT files in a date range."
    )
    laps_parser.add_argument(
        "--start", default="2026-01-01", help="Start date YYYY-MM-DD (inclusive)."
    )
    laps_parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (inclusive, default: today).",
    )
    laps_parser.add_argument("--year", type=int, help="Count for a specific year.")
    laps_parser.add_argument(
        "--month", type=int, help="Count for a specific month (1-12)."
    )
    laps_parser.add_argument(
        "--dir", default="downloads", help="Directory containing FIT files."
    )
    laps_parser.set_defaults(func=run_laps)

    heatmap_parser = subparsers.add_parser(
        "heatmap",
        help="Render a Strava-style route heatmap (HTML) from local FIT files.",
    )
    heatmap_parser.add_argument(
        "--dir", default="downloads", help="Directory containing FIT files."
    )
    heatmap_parser.add_argument(
        "--out", default="heatmap.html", help="Output HTML file path."
    )
    heatmap_parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Only include activities from this year (default: all data).",
    )
    heatmap_parser.add_argument(
        "--city",
        default=None,
        help="Only include activities whose location matches this name "
        "(case-insensitive, e.g. Chengdu).",
    )
    heatmap_parser.add_argument(
        "--max-points",
        type=int,
        default=500,
        help="Max GPS points kept per activity (decimation; default 500).",
    )
    heatmap_parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the on-disk parse cache and re-parse every FIT file.",
    )
    heatmap_parser.set_defaults(func=run_heatmap)

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
    download_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download activities even if already present in --out "
        "(default: skip already-downloaded activities).",
    )
    download_parser.set_defaults(func=run_download)

    readiness_parser = subparsers.add_parser(
        "readiness",
        help="HR-based training load & readiness (train vs rest) for today.",
    )
    readiness_parser.add_argument(
        "--resting-hr", type=int, default=None, help="Override resting HR (bpm)."
    )
    readiness_parser.add_argument(
        "--max-hr", type=int, default=None, help="Override max HR (bpm)."
    )
    readiness_parser.add_argument(
        "--sex", choices=["male", "female"], default=None, help="Override sex."
    )
    readiness_parser.add_argument(
        "--age", type=int, default=None, help="Age (used to estimate max HR)."
    )
    readiness_parser.set_defaults(func=run_readiness)

    zones_parser = subparsers.add_parser(
        "zones",
        help="Show FTHR-based heart-rate training zones.",
    )
    zones_parser.add_argument(
        "--fthr",
        type=float,
        required=True,
        help="Functional Threshold Heart Rate (bpm).",
    )
    zones_parser.set_defaults(func=run_zones)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Analyze a single local FIT file: aerobic decoupling, critical "
        "power / W', and coasting (offline, no network).",
    )
    analyze_parser.add_argument(
        "--file", required=True, help="Path to a local .fit file to analyze."
    )
    analyze_parser.add_argument(
        "--weight",
        type=float,
        default=None,
        help="Rider weight in kg (enables W/kg and a weight-aware phenotype).",
    )
    analyze_parser.set_defaults(func=run_analyze)

    weight_parser = subparsers.add_parser(
        "weight",
        help="Fetch body-weight history from Garmin CN and plot it.",
    )
    weight_parser.add_argument(
        "--start", default="2022-07-01", help="Start date YYYY-MM-DD (inclusive)."
    )
    weight_parser.add_argument(
        "--end",
        default=date.today().isoformat(),
        help="End date YYYY-MM-DD (inclusive, default: today).",
    )
    weight_parser.add_argument(
        "--out", default="weight.png", help="Output path for the weight image."
    )
    weight_parser.set_defaults(func=run_weight)

    badges_parser = subparsers.add_parser(
        "badges",
        help="Fetch earned Garmin badges and render a show-off poster image.",
    )
    badges_parser.add_argument(
        "--out", default="badges.png", help="Output path for the badges poster."
    )
    badges_parser.add_argument(
        "--style",
        choices=["grid", "color"],
        default="grid",
        help="Poster style: uniform grid, or a colour-sorted bicycle shape "
        "(default: grid).",
    )
    badges_parser.add_argument(
        "--sort",
        choices=["points", "date", "category"],
        default="points",
        help="Badge ordering in the grid (default: points).",
    )
    badges_parser.add_argument(
        "--columns",
        type=int,
        default=16,
        help="Number of badges per row (default: 16).",
    )
    badges_parser.add_argument(
        "--res",
        choices=["mdpi", "hdpi", "xhdpi", "xxhdpi"],
        default="xxhdpi",
        help="Badge artwork resolution (default: xxhdpi, highest).",
    )
    badges_parser.set_defaults(func=run_badges)

    return parser
