"""Single-activity ride analysis derived from one FIT file's record stream.

Everything here works on a single activity, offline, using only the libraries
already required by the project (numpy/pandas). Three analyses are provided
that Garmin Connect does not surface per ride:

* **Aerobic decoupling (Pw:Hr) + efficiency factor** -- :func:`compute_decoupling`.
  How much power-to-heart-rate drifts from the first to the second half of a
  ride; a durability/endurance marker.
* **Critical power / W' + rider phenotype** -- :func:`compute_critical_power`.
  Fits the 2-parameter critical-power model to the ride's mean-maximal power
  curve to estimate sustainable power (CP) and anaerobic work capacity (W').
* **Coasting / pedaling breakdown** -- :func:`compute_coasting`.
  How much of the moving time was spent freewheeling versus pedaling.

The building blocks (:func:`normalized_power`, :func:`mean_max_power`,
``compute_*``) are pure: they accept already-parsed pandas objects / mappings
so they can be unit-tested without a real FIT file. :func:`analyze_ride` is the
orchestrator that turns a parsed ``fitparse.FitFile`` into a
:class:`RideAnalysis`.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING

from ._fit import extract_fit_bytes

if TYPE_CHECKING:  # imported lazily at runtime inside functions
    import pandas as pd

logger = logging.getLogger("garmin")

# Durations (seconds) at which the mean-maximal power curve is sampled for the
# critical-power fit: 2, 3, 4, 5, 7, 10, 12, 15 and 20 minutes.
CP_DURATIONS_S: tuple[int, ...] = (120, 180, 240, 300, 420, 600, 720, 900, 1200)

# Critical-power fit is only trusted over this duration window (seconds), where
# the linear work-time model holds reasonably well.
_CP_MIN_S = 120
_CP_MAX_S = 1200
_MIN_CP_POINTS = 3

# Decoupling needs a long-enough continuous effort to be meaningful.
_MIN_DECOUPLING_S = 600  # 10 minutes
# Normalized power uses a 30-second rolling average (Coggan).
_NP_WINDOW_S = 30
# Below this speed (m/s) the rider is considered stopped, not coasting.
_MOVING_SPEED_MS = 0.5
# Decoupling at or below this percentage is conventionally "coupled" (good).
_COUPLED_THRESHOLD_PCT = 5.0


@dataclass(frozen=True)
class Decoupling:
    """Aerobic decoupling (Pw:Hr) and efficiency factor for one ride."""

    efficiency_factor: float  # normalized power / average heart rate
    np_watts: float
    avg_hr: float
    first_half_ratio: float  # NP / HR over the first half
    second_half_ratio: float  # NP / HR over the second half
    decoupling_pct: float  # (first - second) / first * 100

    @property
    def is_coupled(self) -> bool:
        """True when decoupling is within the conventional 5% threshold."""
        return self.decoupling_pct <= _COUPLED_THRESHOLD_PCT


@dataclass(frozen=True)
class CriticalPower:
    """Critical-power model fit and the derived rider phenotype."""

    cp_watts: float
    w_prime_j: float
    r_squared: float
    n_points: int
    phenotype: str
    cp_per_kg: float | None = None

    @property
    def w_prime_kj(self) -> float:
        """Anaerobic work capacity W' expressed in kilojoules."""
        return self.w_prime_j / 1000.0


@dataclass(frozen=True)
class Coasting:
    """Coasting / pedaling time breakdown for one ride (all values seconds)."""

    elapsed_s: float
    moving_s: float
    stopped_s: float
    pedaling_s: float
    coasting_s: float
    longest_coast_s: float

    @property
    def coasting_pct(self) -> float:
        """Coasting time as a percentage of moving time."""
        return 100.0 * self.coasting_s / self.moving_s if self.moving_s else 0.0

    @property
    def pedaling_pct(self) -> float:
        """Pedaling time as a percentage of moving time."""
        return 100.0 * self.pedaling_s / self.moving_s if self.moving_s else 0.0


@dataclass(frozen=True)
class RideAnalysis:
    """Bundle of the single-ride analyses (any section may be ``None``)."""

    duration_min: float
    has_power: bool
    has_hr: bool
    decoupling: Decoupling | None
    critical_power: CriticalPower | None
    coasting: Coasting | None


def normalized_power(power: pd.Series) -> float | None:
    """Normalized Power: the 4th-power mean of 30s-rolling-average power.

    Args:
        power: Power samples at 1 Hz. Missing samples are treated as 0 W
            (coasting), matching the usual convention.

    Returns:
        Normalized power in watts, or ``None`` when there are fewer than
        :data:`_NP_WINDOW_S` samples.
    """
    import numpy as np

    filled = power.fillna(0.0)
    if len(filled) < _NP_WINDOW_S:
        return None
    rolling = (
        filled.rolling(window=_NP_WINDOW_S, min_periods=_NP_WINDOW_S).mean().dropna()
    )
    if rolling.empty:
        return None
    arr = rolling.to_numpy(dtype=float)
    return float(np.mean(arr**4) ** 0.25)


def mean_max_power(
    power: pd.Series,
    durations_s: Sequence[int] = CP_DURATIONS_S,
) -> dict[int, float]:
    """Best (maximal) rolling-average power for each requested duration.

    Uses a prefix-sum so every duration is evaluated in O(N).

    Args:
        power: Power samples at 1 Hz. Missing samples are treated as 0 W.
        durations_s: Window lengths in seconds.

    Returns:
        ``{duration_s: best_avg_power}`` for every duration the ride is long
        enough to support.
    """
    import numpy as np

    samples = power.fillna(0.0).to_numpy(dtype=float)
    n = len(samples)
    out: dict[int, float] = {}
    if n == 0:
        return out
    prefix = np.concatenate(([0.0], np.cumsum(samples)))
    for raw in durations_s:
        d = int(raw)
        if d < 1 or d > n:
            continue
        window_sums = prefix[d:] - prefix[:-d]
        out[d] = float(window_sums.max() / d)
    return out


def _phenotype(
    cp_watts: float,
    w_prime_j: float,
    cp_per_kg: float | None,
) -> str:
    """Classify a rider from CP and W' (rough, clearly-heuristic labels)."""
    w_kj = w_prime_j / 1000.0
    if w_kj <= 0:
        return "Indeterminate (ride lacks short near-maximal efforts)"
    if cp_per_kg is not None:
        if cp_per_kg >= 4.0 and w_kj < 20.0:
            return "Time-trial / climber (strong sustained power-to-weight)"
        if w_kj >= 25.0 and cp_per_kg < 3.7:
            return "Sprinter / pursuiter (large anaerobic reserve)"
        return "All-rounder"
    if w_kj >= 25.0:
        return "Sprinter-leaning (large anaerobic reserve)"
    if w_kj <= 15.0:
        return "Time-trial-leaning (small anaerobic reserve)"
    return "All-rounder"


def compute_critical_power(
    mmp: Mapping[int, float],
    weight_kg: float | None = None,
) -> CriticalPower | None:
    """Fit the 2-parameter critical-power model to a power-duration curve.

    The model is ``work = CP * t + W'`` (equivalently ``P = CP + W'/t``), so a
    linear regression of work against time yields CP (slope) and W' (intercept).

    Args:
        mmp: Mean-maximal power ``{duration_s: watts}`` (see
            :func:`mean_max_power`).
        weight_kg: Optional rider weight, enabling a CP-per-kg figure and a
            weight-aware phenotype.

    Returns:
        A :class:`CriticalPower`, or ``None`` when fewer than
        :data:`_MIN_CP_POINTS` usable durations are present or the fit is
        non-physical (CP <= 0).
    """
    import numpy as np

    points = sorted(
        (int(d), float(p)) for d, p in mmp.items() if _CP_MIN_S <= d <= _CP_MAX_S
    )
    if len(points) < _MIN_CP_POINTS:
        return None

    t = np.array([d for d, _ in points], dtype=float)
    work = np.array([p * d for d, p in points], dtype=float)
    slope, intercept = np.polyfit(t, work, 1)
    cp_watts = float(slope)
    w_prime_j = float(intercept)
    if cp_watts <= 0:
        return None

    predicted = slope * t + intercept
    ss_res = float(((work - predicted) ** 2).sum())
    ss_tot = float(((work - work.mean()) ** 2).sum())
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

    cp_per_kg = cp_watts / weight_kg if weight_kg else None
    phenotype = _phenotype(cp_watts, w_prime_j, cp_per_kg)
    return CriticalPower(
        cp_watts=cp_watts,
        w_prime_j=w_prime_j,
        r_squared=r_squared,
        n_points=len(points),
        phenotype=phenotype,
        cp_per_kg=cp_per_kg,
    )


def compute_decoupling(frame: pd.DataFrame) -> Decoupling | None:
    """Aerobic decoupling (Pw:Hr) and efficiency factor for a 1 Hz ride frame.

    The ride is split into two equal halves by time; for each half the ratio of
    normalized power to average heart rate is computed. Positive decoupling
    means the second half needed more heart rate for the same power (aerobic
    fade); values at or below 5% are conventionally "coupled".

    Args:
        frame: 1 Hz frame with ``power`` and ``heart_rate`` columns.

    Returns:
        A :class:`Decoupling`, or ``None`` when power+HR are missing or the
        usable record is shorter than :data:`_MIN_DECOUPLING_S`.
    """
    if "power" not in frame.columns or "heart_rate" not in frame.columns:
        return None

    valid = frame[["power", "heart_rate"]].copy()
    valid["power"] = valid["power"].fillna(0.0)
    valid = valid.dropna(subset=["heart_rate"])
    if len(valid) < _MIN_DECOUPLING_S:
        return None

    half = len(valid) // 2
    first, second = valid.iloc[:half], valid.iloc[half:]
    np_first = normalized_power(first["power"])
    np_second = normalized_power(second["power"])
    hr_first = float(first["heart_rate"].mean())
    hr_second = float(second["heart_rate"].mean())
    if not np_first or not np_second or hr_first <= 0 or hr_second <= 0:
        return None

    ratio_first = np_first / hr_first
    ratio_second = np_second / hr_second
    if ratio_first == 0:
        return None
    decoupling_pct = (ratio_first - ratio_second) / ratio_first * 100.0

    np_all = normalized_power(valid["power"])
    hr_all = float(valid["heart_rate"].mean())
    if not np_all or hr_all <= 0:
        return None

    return Decoupling(
        efficiency_factor=np_all / hr_all,
        np_watts=np_all,
        avg_hr=hr_all,
        first_half_ratio=ratio_first,
        second_half_ratio=ratio_second,
        decoupling_pct=decoupling_pct,
    )


def _longest_true_run(mask) -> int:
    """Length of the longest run of consecutive ``True`` values in ``mask``."""
    import numpy as np

    arr = np.concatenate(([0], np.asarray(mask, dtype=np.int8), [0]))
    deltas = np.diff(arr)
    starts = np.flatnonzero(deltas == 1)
    ends = np.flatnonzero(deltas == -1)
    if len(starts) == 0:
        return 0
    return int((ends - starts).max())


def compute_coasting(
    frame: pd.DataFrame,
    moving_speed_ms: float = _MOVING_SPEED_MS,
) -> Coasting | None:
    """Coasting versus pedaling breakdown for a 1 Hz ride frame.

    A second counts as *moving* when speed exceeds ``moving_speed_ms`` (or, when
    speed is unavailable, when power or cadence is positive). Within moving
    time, a second is *pedaling* when cadence is positive (or, lacking cadence,
    when power is positive) and *coasting* otherwise.

    Args:
        frame: 1 Hz frame; uses ``speed`` (m/s), ``cadence`` and/or ``power``.
        moving_speed_ms: Speed threshold separating moving from stopped.

    Returns:
        A :class:`Coasting`, or ``None`` when neither cadence nor power is
        present (pedaling cannot be distinguished from coasting).
    """
    has_speed = "speed" in frame.columns and frame["speed"].notna().any()
    has_cadence = "cadence" in frame.columns and frame["cadence"].notna().any()
    has_power = "power" in frame.columns and frame["power"].notna().any()
    if not has_cadence and not has_power:
        return None

    present = [c for c in ("power", "cadence", "speed") if c in frame.columns]
    valid_row = frame[present].notna().any(axis=1).to_numpy()
    elapsed = int(valid_row.sum())
    if elapsed == 0:
        return None

    if has_speed:
        speed = frame["speed"].fillna(-1.0).to_numpy()
        moving = (speed > moving_speed_ms) & valid_row
    else:
        proxy = frame["power"] if has_power else frame["cadence"]
        moving = (proxy.fillna(0.0).to_numpy() > 0) & valid_row

    if has_cadence:
        pedaling = (frame["cadence"].fillna(0.0).to_numpy() > 0) & moving
    else:
        pedaling = (frame["power"].fillna(0.0).to_numpy() > 0) & moving
    coasting = moving & ~pedaling

    moving_s = int(moving.sum())
    return Coasting(
        elapsed_s=float(elapsed),
        moving_s=float(moving_s),
        stopped_s=float(elapsed - moving_s),
        pedaling_s=float(int(pedaling.sum())),
        coasting_s=float(int(coasting.sum())),
        longest_coast_s=float(_longest_true_run(coasting)),
    )


def _first_value(record, names: Sequence[str]):
    """First non-``None`` value among ``names`` from a FIT record."""
    for name in names:
        value = record.get_value(name)
        if value is not None:
            return value
    return None


def ride_frame(fit_file) -> pd.DataFrame | None:
    """Build a 1 Hz pandas frame of the record stream from a parsed FIT file.

    Collects timestamp, power, heart rate, cadence and speed, coerces them to
    numeric, then resamples onto a uniform 1-second grid (averaging any
    sub-second duplicates and leaving gaps as NaN).

    Args:
        fit_file: A ``fitparse.FitFile`` with ``record`` messages.

    Returns:
        A 1 Hz :class:`pandas.DataFrame` indexed by timestamp, or ``None`` when
        the activity has no timestamped records.
    """
    import pandas as pd

    fields = ("power", "heart_rate", "cadence")
    timestamps: list = []
    columns: dict[str, list] = {name: [] for name in fields}
    columns["speed"] = []
    for record in fit_file.get_messages("record"):
        ts = record.get_value("timestamp")
        if ts is None:
            continue
        timestamps.append(ts)
        for name in fields:
            columns[name].append(record.get_value(name))
        columns["speed"].append(_first_value(record, ("enhanced_speed", "speed")))

    if not timestamps:
        return None

    df = pd.DataFrame(columns, index=pd.to_datetime(timestamps))
    df = df.apply(pd.to_numeric, errors="coerce").sort_index()
    return df.resample("1s").mean()


def analyze_ride(fit_file, weight_kg: float | None = None) -> RideAnalysis:
    """Run all single-ride analyses on a parsed FIT file.

    Args:
        fit_file: A ``fitparse.FitFile`` instance.
        weight_kg: Optional rider weight for CP-per-kg and phenotype.

    Returns:
        A :class:`RideAnalysis`; sections without enough data are ``None``.
    """
    frame = ride_frame(fit_file)
    if frame is None or frame.empty:
        return RideAnalysis(0.0, False, False, None, None, None)

    has_power = "power" in frame.columns and frame["power"].notna().any()
    has_hr = "heart_rate" in frame.columns and frame["heart_rate"].notna().any()
    duration_min = len(frame) / 60.0

    decoupling = compute_decoupling(frame) if has_power and has_hr else None
    critical_power = None
    if has_power:
        mmp = mean_max_power(frame["power"], CP_DURATIONS_S)
        critical_power = compute_critical_power(mmp, weight_kg)
    coasting = compute_coasting(frame)

    return RideAnalysis(
        duration_min=duration_min,
        has_power=bool(has_power),
        has_hr=bool(has_hr),
        decoupling=decoupling,
        critical_power=critical_power,
        coasting=coasting,
    )


class PowerMixin:
    """Single-ride analysis for the latest downloaded activity."""

    def analyze_latest_ride(
        self,
        weight_kg: float | None = None,
    ) -> RideAnalysis | None:
        """Download the latest activity and run :func:`analyze_ride` on it.

        Args:
            weight_kg: Optional rider weight for CP-per-kg and phenotype.

        Returns:
            A :class:`RideAnalysis`, or ``None`` when there is no activity or
            the downloaded archive has no ``.fit`` member.
        """
        import io

        import fitparse

        activities = self.get_latest_activities(0, 1)
        if not activities:
            logger.warning("No activities found to analyze.")
            return None

        activity_id = activities[0].get("activityId")
        activity_bytes = self.download_activity(activity_id, fmt="fit")
        fit_bytes = extract_fit_bytes(activity_bytes)
        if not fit_bytes:
            logger.warning("No .fit file in latest activity archive.")
            return None

        fitfile = fitparse.FitFile(io.BytesIO(fit_bytes))
        return analyze_ride(fitfile, weight_kg=weight_kg)
