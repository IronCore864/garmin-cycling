"""VO2 Max retrieval and cycling VO2max plotting."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from ._utils import to_date_str

logger = logging.getLogger("garmin")

# How far back to look for the most recent value / when building a plot.
LOOKBACK_DAYS = 30


class VO2Mixin:
    """VO2 Max Garmin Connect endpoints."""

    def get_vo2max(self, for_date: str | date | None = None) -> dict[str, Any]:
        """Get VO2 Max data for a specific date.

        Args:
            for_date: Date to query. Defaults to today.

        Returns:
            Dict with keys: generic, cycling (each containing
            vo2MaxPreciseValue, vo2MaxValue, fitnessAge, calendarDate).
        """
        d = to_date_str(for_date) if for_date else date.today().isoformat()
        result = self.connectapi(f"/metrics-service/metrics/maxmet/daily/{d}/{d}")
        if isinstance(result, list) and result:
            return result[0]
        return result if result else {}

    def get_vo2max_range(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
    ) -> list[dict[str, Any]]:
        """Get VO2 Max history for a date range.

        Args:
            start_date: Start date (YYYY-MM-DD or date object).
            end_date: End date. Defaults to today.

        Returns:
            List of daily VO2 Max entries, each with generic/cycling dicts.
        """
        start = to_date_str(start_date)
        end = to_date_str(end_date) if end_date else date.today().isoformat()
        result = self.connectapi(
            f"/metrics-service/metrics/maxmet/daily/{start}/{end}"
        )
        return result if isinstance(result, list) else [result] if result else []

    def get_vo2max_latest(self) -> dict[str, Any]:
        """Get the most recent VO2 Max reading (looks back up to 30 days)."""
        today = date.today()
        entries = self.get_vo2max_range(today - timedelta(days=LOOKBACK_DAYS), today)
        if entries:
            for entry in reversed(entries):
                generic = entry.get("generic") or {}
                cycling = entry.get("cycling") or {}
                if generic.get("vo2MaxPreciseValue") or cycling.get(
                    "vo2MaxPreciseValue"
                ):
                    return entry
        return {}

    def get_latest_cycling_vo2max(
        self,
        lookback_days: int = LOOKBACK_DAYS,
    ) -> dict[str, Any] | None:
        """Return the most recent cycling VO2max precise value.

        Searches today back to ``lookback_days`` ago for the nearest day
        with cycling data.

        Returns:
            ``{"date", "vo2max_precise"}`` or None if no data is found.
        """
        today = date.today()
        start = today - timedelta(days=lookback_days)
        metrics = self.get_vo2max_range(start, today)
        records = _cycling_records(metrics)
        if not records:
            return None
        latest = max(records, key=lambda r: r["Date"])
        return {"date": latest["Date"], "vo2max_precise": latest["VO2max"]}

    def plot_monthly_vo2max(
        self,
        out_path: str,
        lookback_days: int = LOOKBACK_DAYS,
        dpi: int = 150,
    ) -> str | None:
        """Generate a cycling VO2max image for the past month.

        Args:
            out_path: File path to write the PNG to.
            lookback_days: How many days back to include.
            dpi: Output image resolution.

        Returns:
            The output path, or None if there is no data to plot.
        """
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import pandas as pd

        today = date.today()
        start = today - timedelta(days=lookback_days)
        metrics = self.get_vo2max_range(start, today)
        records = _cycling_records(metrics)
        if not records:
            logger.warning("No cycling VO2max data available for the past month.")
            return None

        fig = _build_figure(pd.DataFrame(records))
        fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        return out_path


# ------------------------------------------------------------------
# Plotting
# ------------------------------------------------------------------

# Plot constants.
_BACKGROUND = "#F5F5F5"
_SCATTER_CMAP = "RdYlGn"
_SCATTER_SIZE = 80


def _cycling_records(metrics) -> list[dict]:
    """Extract [{"Date", "VO2max"}] cycling records from a max-metrics range."""
    records = []
    for item in metrics or []:
        cycling = item.get("cycling") if item else None
        if cycling:
            value = cycling.get("vo2MaxPreciseValue")
            cal_date = cycling.get("calendarDate")
            if value is not None and cal_date:
                records.append({"Date": cal_date, "VO2max": value})
    return records


def _build_figure(df):
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt
    import pandas as pd

    df = df.dropna(subset=["VO2max", "Date"])
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
        df["VO2max"],
        color="#A3C1DA",
        alpha=0.35,
        s=36,
        label="Raw Data",
        zorder=1,
        edgecolors="none",
    )
    ax.plot(
        df_avg["Date"],
        df_avg["VO2max"],
        color="blue",
        lw=2,
        marker="o",
        markersize=8,
        label=label,
        zorder=2,
    )
    ax.scatter(
        df_avg["Date"],
        df_avg["VO2max"],
        c=df_avg["VO2max"],
        cmap=_SCATTER_CMAP,
        s=_SCATTER_SIZE,
        zorder=3,
    )
    ax.set_ylabel("VO2max")
    ax.grid(True, which="both", linestyle="--", linewidth=0.5, color="#D3D3D3")
    fig.autofmt_xdate(rotation=45)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.tick_params(axis="x", labelsize=10)
    ax.tick_params(axis="y", labelsize=10)
    ax.legend()
    fig.tight_layout()
    return fig
