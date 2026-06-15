"""Shared helpers used across the garmin package."""

from __future__ import annotations

from datetime import date, datetime


def to_date_str(d: str | date) -> str:
    """Convert a date or string to a YYYY-MM-DD string."""
    if isinstance(d, date):
        return d.isoformat()
    return d


def parse_date(d: str | date) -> date:
    """Parse a date string or return the date object unchanged."""
    if isinstance(d, date):
        return d
    return datetime.strptime(d, "%Y-%m-%d").date()


def activity_in_range(activity: dict, start: date, end: date) -> bool:
    """Check whether an activity's start date falls within a range."""
    start_time = activity.get("startTimeLocal", "")
    if not start_time:
        return False
    try:
        activity_date = datetime.strptime(start_time[:10], "%Y-%m-%d").date()
        return start <= activity_date <= end
    except (ValueError, TypeError):
        return False


def safe_filename(text: str) -> str:
    """Make a string safe to use as a filename component.

    Alphanumerics and ``-_. `` are kept; everything else becomes ``_``. Spaces
    are collapsed to underscores. Falls back to ``"activity"`` when the result
    would be empty.
    """
    keep = "-_. "
    cleaned = "".join(c if c.isalnum() or c in keep else "_" for c in text)
    return cleaned.strip().replace(" ", "_") or "activity"
