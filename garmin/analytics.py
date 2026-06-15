"""Power/heart-rate analytics for Garmin activities.

Computes, for a set of durations, the maximum rolling average power and the
heart rate that occurred over that same best window.
"""

from __future__ import annotations

import io
import logging

from ._fit import extract_fit_bytes

logger = logging.getLogger("garmin")

# Durations (minutes) to compute rolling max average power for.
DEFAULT_DURATIONS = [1, 2, 3, 4, 5, 20, 60, 120, 180, 240, 300, 360]


def max_avg_pwr_and_hr(fit_file, durations: list[int] | None = None) -> dict:
    """Compute max rolling average power and corresponding HR per duration.

    For each duration (in minutes), find the window with the highest average
    power and report that average power together with the average heart rate
    over the same window.

    Args:
        fit_file: A ``fitparse.FitFile`` instance with activity records.
        durations: Durations in minutes. Defaults to
            ``[1, 2, 3, 4, 5, 20, 60, 120, 180, 240, 300, 360]``.

    Returns:
        Dict ``{duration: (max_avg_power, corresponding_avg_hr)}`` containing
        only the durations the activity is long enough to support.
    """
    import pandas as pd

    if durations is None:
        durations = DEFAULT_DURATIONS

    timestamps, heart_rates, powers = [], [], []
    for record in fit_file.get_messages("record"):
        timestamp = record.get_value("timestamp")
        heart_rate = record.get_value("heart_rate")
        power = record.get_value("power")
        if timestamp and heart_rate is not None and power is not None:
            timestamps.append(timestamp)
            heart_rates.append(heart_rate)
            powers.append(power)

    if not heart_rates or not powers:
        logger.warning("No heart rate or power data found in the FIT file.")
        return {}

    df = pd.DataFrame(
        {"timestamp": timestamps, "heart_rate": heart_rates, "power": powers}
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")

    total_duration_minutes = (df.index.max() - df.index.min()).total_seconds() / 60
    if total_duration_minutes == 0:
        logger.warning("Activity duration is too short to compute rolling averages.")
        return {}

    samples_per_minute = len(df) / total_duration_minutes
    results = {}
    for duration in durations:
        if duration > total_duration_minutes:
            continue
        window_samples = int(duration * samples_per_minute)
        min_periods = int(window_samples * 0.9)
        if window_samples < 1 or len(df) < window_samples:
            continue
        rolling_power = (
            df["power"]
            .rolling(window=window_samples, center=False, min_periods=min_periods)
            .mean()
        )
        rolling_hr = (
            df["heart_rate"]
            .rolling(window=window_samples, center=False, min_periods=min_periods)
            .mean()
        )
        max_avg_power = rolling_power.max()
        max_power_timestamp = rolling_power.idxmax()
        corresponding_avg_hr = rolling_hr.loc[max_power_timestamp]
        results[duration] = (max_avg_power, corresponding_avg_hr)
    return results


class AnalyticsMixin:
    """Power/heart-rate analytics derived from activity FIT files."""

    def analyze_latest_activity(self, durations: list[int] | None = None) -> dict:
        """Download the latest activity and compute power/HR analytics.

        Args:
            durations: Optional list of durations in minutes.

        Returns:
            Dict ``{duration: (max_avg_power, corresponding_avg_hr)}``, or an
            empty dict if the latest activity has no power/HR data.
        """
        import fitparse

        activities = self.get_latest_activities(0, 1)
        if not activities:
            logger.warning("No activities found to analyze.")
            return {}

        activity_id = activities[0].get("activityId")
        activity_bytes = self.download_activity(activity_id, fmt="fit")
        fit_bytes = extract_fit_bytes(activity_bytes)
        if not fit_bytes:
            logger.warning("No .fit file in latest activity archive.")
            return {}

        fitfile = fitparse.FitFile(io.BytesIO(fit_bytes))
        return max_avg_pwr_and_hr(fitfile, durations)
