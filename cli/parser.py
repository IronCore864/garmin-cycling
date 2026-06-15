"""Argument-parser construction for the Garmin Cycling CLI."""

from __future__ import annotations

import argparse
from datetime import date

from garmin.workflow import DEFAULT_VO2MAX_IMAGE

from .commands import run_download, run_gear, run_laps, run_sync


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
        "gear", help="List a year's cycling activities categorized by gear."
    )
    gear_parser.add_argument(
        "--year",
        type=int,
        default=date.today().year,
        help="Year to report on (default: current year).",
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
    download_parser.set_defaults(func=run_download)

    return parser
