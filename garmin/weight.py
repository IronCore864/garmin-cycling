"""Body-weight retrieval and weight-history plotting.

Weigh-ins are pulled from Garmin Connect's weight service. The raw API stores
weight in grams; this module normalises everything to kilograms.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from ._utils import parse_date, to_date_str

logger = logging.getLogger("garmin")

# The weight dateRange endpoint can be flaky over very long spans, so requests
# are split into chunks of at most this many days.
_CHUNK_DAYS = 365


class WeightMixin:
    """Body-weight Garmin Connect endpoints + plotting."""

    def get_weigh_ins(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
    ) -> dict[str, Any]:
        """Get the raw weight dateRange payload for a (short) date range.

        Args:
            start_date: Start date (YYYY-MM-DD or date object).
            end_date: End date. Defaults to today.

        Returns:
            The raw API dict (keys include ``dateWeightList`` and
            ``totalAverage``), or ``{}`` if nothing is returned.
        """
        start = to_date_str(start_date)
        end = to_date_str(end_date) if end_date else date.today().isoformat()
        result = self.connectapi(
            "/weight-service/weight/dateRange",
            params={"startDate": start, "endDate": end},
        )
        return result if isinstance(result, dict) else {}

    def get_weight_range(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
    ) -> list[dict[str, Any]]:
        """Get weigh-in history as ``[{"Date", "Weight"}]`` (weight in kg).

        The range is fetched in yearly chunks (the API can be unreliable over
        multi-year spans) and de-duplicated by calendar date.

        Args:
            start_date: Start date (YYYY-MM-DD or date object).
            end_date: End date. Defaults to today.

        Returns:
            Records sorted by date, each ``{"Date": "YYYY-MM-DD",
            "Weight": <kg float>}``.
        """
        start = parse_date(start_date)
        end = parse_date(end_date) if end_date else date.today()

        by_date: dict[str, float] = {}
        chunk_start = start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=_CHUNK_DAYS - 1), end)
            payload = self.get_weigh_ins(chunk_start, chunk_end)
            for record in _weight_records(payload):
                by_date[record["Date"]] = record["Weight"]
            chunk_start = chunk_end + timedelta(days=1)

        return [
            {"Date": d, "Weight": w} for d, w in sorted(by_date.items())
        ]

    def get_latest_weight(
        self,
        lookback_days: int = 30,
    ) -> dict[str, Any] | None:
        """Return the most recent weigh-in as ``{"date", "weight_kg"}``.

        Searches ``lookback_days`` back from today; returns None if none found.
        """
        today = date.today()
        records = self.get_weight_range(today - timedelta(days=lookback_days), today)
        if not records:
            return None
        latest = records[-1]
        return {"date": latest["Date"], "weight_kg": latest["Weight"]}

    def plot_weight(
        self,
        out_path: str,
        start_date: str | date,
        end_date: str | date | None = None,
        dpi: int = 150,
    ) -> str | None:
        """Generate a body-weight history image for a date range.

        Args:
            out_path: File path to write the PNG to.
            start_date: Start date (YYYY-MM-DD or date object).
            end_date: End date. Defaults to today.
            dpi: Output image resolution.

        Returns:
            The output path, or None if there is no data to plot.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        records = self.get_weight_range(start_date, end_date)
        if not records:
            logger.warning("No weight data available for the requested range.")
            return None

        fig = _build_figure(pd.DataFrame(records))
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        return out_path


# ------------------------------------------------------------------
# Parsing
# ------------------------------------------------------------------


def _weight_records(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract ``[{"Date", "Weight"}]`` (kg) from a weight dateRange payload."""
    records: list[dict[str, Any]] = []
    entries = (payload or {}).get("dateWeightList") or []
    for entry in entries:
        grams = entry.get("weight")
        if grams is None:
            continue
        cal_date = entry.get("calendarDate")
        if not cal_date:
            ts = entry.get("date")
            if ts is None:
                continue
            cal_date = datetime.utcfromtimestamp(ts / 1000).date().isoformat()
        records.append({"Date": cal_date, "Weight": grams / 1000.0})
    return records


# ------------------------------------------------------------------
# Plotting
# ------------------------------------------------------------------

# Plot constants (mirrors vo2.py styling).
_BACKGROUND = "#F5F5F5"
_SCATTER_CMAP = "RdYlGn_r"  # reversed: lower weight = greener
_SCATTER_SIZE = 80


def _build_figure(df):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd

    df = df.dropna(subset=["Weight", "Date"])
    df = df.sort_values("Date")
    df["Date"] = pd.to_datetime(df["Date"])
    df_weekly = df.resample("W-SUN", on="Date").mean(numeric_only=True).reset_index()
    if len(df_weekly) > 60:
        df_avg = df.resample("ME", on="Date").mean(numeric_only=True).reset_index()
        label = "Monthly Avg"
    else:
        df_avg = df_weekly
        label = "Weekly Avg"

    fig, ax = plt.subplots(figsize=(15, 7))
    fig.patch.set_facecolor(_BACKGROUND)
    ax.set_facecolor(_BACKGROUND)
    ax.scatter(
        df["Date"],
        df["Weight"],
        color="#A3C1DA",
        alpha=0.35,
        s=36,
        label="Raw Data",
        zorder=1,
        edgecolors="none",
    )
    ax.plot(
        df_avg["Date"],
        df_avg["Weight"],
        color="blue",
        lw=2,
        marker="o",
        markersize=8,
        label=label,
        zorder=2,
    )
    ax.scatter(
        df_avg["Date"],
        df_avg["Weight"],
        c=df_avg["Weight"],
        cmap=_SCATTER_CMAP,
        s=_SCATTER_SIZE,
        zorder=3,
    )
    ax.set_ylabel("Weight (kg)")
    ax.set_title("Body Weight")
    ax.grid(True, which="both", linestyle="--", linewidth=0.5, color="#D3D3D3")
    fig.autofmt_xdate(rotation=45)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.tick_params(axis="x", labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.legend()
    fig.tight_layout()
    return fig
