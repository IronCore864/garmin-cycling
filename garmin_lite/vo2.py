"""Cycling VO2max retrieval and plotting (precise values)."""

import logging
from datetime import date, timedelta
from typing import Optional

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from garminconnect import Garmin

logger = logging.getLogger("garmin_lite")

# How far back to look when searching for the most recent value / building the plot.
LOOKBACK_DAYS = 30

# --- Plot constants ---
BACKGROUND = "#F5F5F5"
SCATTER_CMAP = "RdYlGn"
SCATTER_SIZE = 80


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


def get_latest_cycling_vo2max(
    garmin_client: Garmin,
    lookback_days: int = LOOKBACK_DAYS,
) -> Optional[dict]:
    """Return the most recent cycling VO2max precise value.

    Tries today, then yesterday, then the nearest earlier day with data
    (within ``lookback_days``). Returns ``{"date", "vo2max_precise"}`` or None.
    """
    today = date.today()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end = today.isoformat()

    metrics = garmin_client.get_max_metrics_date_range(start, end)
    records = _cycling_records(metrics)
    if not records:
        return None

    latest = max(records, key=lambda r: r["Date"])
    return {"date": latest["Date"], "vo2max_precise": latest["VO2max"]}


def _build_figure(df: pd.DataFrame):
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
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
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
        cmap=SCATTER_CMAP,
        s=SCATTER_SIZE,
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


def plot_monthly_vo2max(
    garmin_client: Garmin,
    out_path: str,
    lookback_days: int = LOOKBACK_DAYS,
    dpi: int = 150,
) -> Optional[str]:
    """Generate a cycling VO2max image for the past month.

    Returns the output path, or None if there is no data to plot.
    """
    today = date.today()
    start = (today - timedelta(days=lookback_days)).isoformat()
    end = today.isoformat()

    metrics = garmin_client.get_max_metrics_date_range(start, end)
    records = _cycling_records(metrics)
    if not records:
        logger.warning("No cycling VO2max data available for the past month.")
        return None

    fig = _build_figure(pd.DataFrame(records))
    fig.savefig(out_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return out_path
