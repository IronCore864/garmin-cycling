"""HR-based training load and readiness.

Answers "should I train or rest today?" from heart-rate data, mirroring
Strava/Garmin's paid Relative-Effort / Fitness-&-Freshness views. Readiness is a
*current-state* question, so the public entry point takes no date/range flags: it
assesses a fixed recent window (:data:`LOOKBACK_DAYS`) ending today and picks its
data source automatically (reuse local FIT files when they are up to date, else
fetch recent activities online in memory).

Building blocks:

* :func:`activity_load` -- Banister HR-reserve TRIMP for one activity ("相对负荷度").
* :func:`rolling_metrics` -- EWMA Fitness (CTL), Fatigue (ATL), Form (TSB).
* :func:`acwr` -- acute:chronic workload ratio guardrail.
* :func:`recommend` -- map (Form, ACWR) to a train/easy/rest recommendation.
* :func:`analyze_readiness` -- orchestrator with automatic source selection.
"""

from __future__ import annotations

import io
import logging
import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from ._fit import extract_fit_bytes
from .config import AthleteProfile

logger = logging.getLogger("garmin")

# Fixed lookback for the readiness assessment (days). Covers the 42-day fitness
# constant and the 28-day chronic ACWR window.
LOOKBACK_DAYS = 42

# EWMA time constants (days) for Fitness (CTL) and Fatigue (ATL).
CTL_TAU_DAYS = 42
ATL_TAU_DAYS = 7
# Acute:chronic workload ratio windows (days).
ACUTE_DAYS = 7
CHRONIC_DAYS = 28

# Banister TRIMP constant multiplier.
_TRIMP_B = 0.64
# Cap the elapsed weighting of a single sample gap (seconds) so device pauses
# do not inflate load; normal FIT recording is ~1 s/sample.
_MAX_SAMPLE_GAP_S = 60.0

# Recommendation thresholds (tunable).
TSB_REST = -30.0  # Form at/below this => deep fatigue.
TSB_FRESH = -10.0  # Form at/above this => adequately recovered.
ACWR_HIGH = 1.5  # ACWR above this => overload / injury-risk zone.

# Default directory the download command writes to; reused when up to date.
DEFAULT_DOWNLOADS_DIR = "downloads"


@dataclass(frozen=True)
class DayLoad:
    """Aggregated training load for a single calendar day."""

    day: date
    load: int


@dataclass(frozen=True)
class Recommendation:
    """A train/easy/rest recommendation with a short rationale."""

    recommendation: str  # "rest" | "easy" | "train"
    caution: bool  # True when load is spiking (ACWR above the high threshold).
    rationale: str


@dataclass(frozen=True)
class ReadinessMetrics:
    """Per-day rolling readiness metrics."""

    day: date
    load: int
    ctl: float  # Fitness.
    atl: float  # Fatigue.
    tsb: float  # Form = previous day's CTL - ATL.
    acwr: float | None  # Acute:chronic ratio (None when undefined).


@dataclass(frozen=True)
class ReadinessReport:
    """End-to-end readiness result for the assessed window."""

    start: date
    end: date
    scanned: int
    source: str  # "local" | "online"
    days: list[ReadinessMetrics]
    latest: ReadinessMetrics | None
    recommendation: Recommendation | None


# --- per-activity load -----------------------------------------------------


def activity_load(fit_file, profile: AthleteProfile) -> int | None:
    """Compute HR-reserve–weighted Banister TRIMP for one activity.

    Args:
        fit_file: A parsed ``fitparse.FitFile``.
        profile: Athlete HR parameters (resting HR, max HR, sex).

    Returns:
        An integer training-load score, or ``None`` when the activity has no
        usable heart-rate data.

    Raises:
        RuntimeError: If the profile lacks the parameters TRIMP requires.
    """
    resting, max_hr, k = profile.trimp_params()
    denom = max_hr - resting

    samples: list[tuple[object, float]] = []
    for record in fit_file.get_messages("record"):
        ts = record.get_value("timestamp")
        hr = record.get_value("heart_rate")
        if ts is not None and hr is not None:
            samples.append((ts, float(hr)))

    if len(samples) < 2:
        return None

    samples.sort(key=lambda s: s[0])
    trimp = 0.0
    for (t0, _), (t1, hr1) in zip(samples[:-1], samples[1:], strict=False):
        elapsed_s = (t1 - t0).total_seconds()
        if elapsed_s <= 0:
            continue
        dt_min = min(elapsed_s, _MAX_SAMPLE_GAP_S) / 60.0
        hrr = (hr1 - resting) / denom
        hrr = max(0.0, min(1.0, hrr))
        trimp += dt_min * hrr * _TRIMP_B * math.exp(k * hrr)
    return int(round(trimp))


# --- rolling metrics (pure) ------------------------------------------------


def _series_from_loads(
    loads_by_day: dict[date, int], start: date, end: date
) -> list[DayLoad]:
    """Build a continuous, zero-filled daily series over ``[start, end]``."""
    out: list[DayLoad] = []
    day = start
    while day <= end:
        out.append(DayLoad(day=day, load=loads_by_day.get(day, 0)))
        day += timedelta(days=1)
    return out


def _window_average(loads: list[int], index: int, window: int) -> float:
    """Mean load over the ``window`` days ending at ``index`` (inclusive)."""
    lo = max(0, index - window + 1)
    span = loads[lo : index + 1]
    return sum(span) / len(span) if span else 0.0


def _acwr_at(loads: list[int], index: int) -> float | None:
    """ACWR for the day at ``index``; ``None`` when chronic load is zero."""
    chronic = _window_average(loads, index, CHRONIC_DAYS)
    if chronic == 0:
        return None
    acute = _window_average(loads, index, ACUTE_DAYS)
    return acute / chronic


def acwr(loads: list[int]) -> float | None:
    """Acute:chronic workload ratio for the most recent day of ``loads``.

    Returns ``None`` (undefined) when chronic load is zero or the series is
    empty, avoiding division by zero.
    """
    if not loads:
        return None
    return _acwr_at(loads, len(loads) - 1)


def rolling_metrics(series: list[DayLoad]) -> list[ReadinessMetrics]:
    """Compute EWMA Fitness/Fatigue/Form and ACWR for each day in ``series``.

    CTL uses a 42-day time constant, ATL a 7-day one; Form (TSB) for a day is
    the *previous* day's CTL minus ATL, so adding load raises fatigue faster
    than fitness and rest raises form.
    """
    loads = [d.load for d in series]
    ctl = 0.0
    atl = 0.0
    out: list[ReadinessMetrics] = []
    for i, d in enumerate(series):
        tsb = ctl - atl  # Based on the prior day's fitness/fatigue.
        ctl += (d.load - ctl) / CTL_TAU_DAYS
        atl += (d.load - atl) / ATL_TAU_DAYS
        out.append(
            ReadinessMetrics(
                day=d.day,
                load=d.load,
                ctl=ctl,
                atl=atl,
                tsb=tsb,
                acwr=_acwr_at(loads, i),
            )
        )
    return out


def recommend(tsb: float, acwr_value: float | None) -> Recommendation:
    """Map Form (TSB) and ACWR to a train/easy/rest recommendation.

    Deep fatigue (very negative Form) recommends rest; a load spike (ACWR above
    the high threshold) recommends easy and raises a caution flag; lingering
    fatigue recommends easy; otherwise train.
    """
    caution = acwr_value is not None and acwr_value > ACWR_HIGH

    if tsb <= TSB_REST:
        rec = "rest"
        why = f"deep fatigue (Form {tsb:.0f}); prioritize recovery"
    elif caution:
        rec = "easy"
        why = (
            f"load spiking (ACWR {acwr_value:.2f} > {ACWR_HIGH:.1f}); "
            "ease off to limit injury risk"
        )
    elif tsb < TSB_FRESH:
        rec = "easy"
        why = f"still carrying fatigue (Form {tsb:.0f}); keep it light"
    else:
        rec = "train"
        why = f"recovered (Form {tsb:.0f}); good to train"
    return Recommendation(recommendation=rec, caution=caution, rationale=why)


def build_readiness_report(
    loads_by_day: dict[date, int],
    scanned: int,
    start: date,
    end: date,
    source: str,
) -> ReadinessReport:
    """Assemble a :class:`ReadinessReport` from per-day loads (pure)."""
    if scanned == 0:
        return ReadinessReport(
            start=start,
            end=end,
            scanned=scanned,
            source=source,
            days=[],
            latest=None,
            recommendation=None,
        )
    series = _series_from_loads(loads_by_day, start, end)
    metrics = rolling_metrics(series)
    latest = metrics[-1]
    rec = recommend(latest.tsb, latest.acwr)
    return ReadinessReport(
        start=start,
        end=end,
        scanned=scanned,
        source=source,
        days=metrics,
        latest=latest,
        recommendation=rec,
    )


# --- data collectors -------------------------------------------------------


def has_todays_activity(
    directory: str | Path = DEFAULT_DOWNLOADS_DIR, today: date | None = None
) -> bool:
    """Whether ``directory`` holds a FIT file dated ``today`` (freshness check)."""
    today = today or date.today()
    directory = Path(directory)
    if not directory.is_dir():
        return False
    today_iso = today.isoformat()
    return any(f.name[:10] == today_iso for f in directory.glob("*.fit"))


def _collect_local(
    directory: str | Path, start: date, end: date, profile: AthleteProfile
) -> tuple[dict[date, int], int]:
    """Sum per-day load from local FIT files in ``[start, end]``."""
    import fitparse

    directory = Path(directory)
    start_iso, end_iso = start.isoformat(), end.isoformat()
    files = sorted(
        f
        for f in directory.glob("*.fit")
        if len(f.name) >= 10 and start_iso <= f.name[:10] <= end_iso
    )
    loads_by_day: dict[date, int] = {}
    scanned = 0
    for fp in files:
        scanned += 1
        try:
            load = activity_load(fitparse.FitFile(str(fp)), profile)
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 -- skip unreadable/corrupt files
            logger.debug("Skipping unreadable FIT file: %s", fp.name)
            continue
        if load is None:
            continue
        try:
            day = date.fromisoformat(fp.name[:10])
        except ValueError:
            continue
        loads_by_day[day] = loads_by_day.get(day, 0) + load
    return loads_by_day, scanned


def _download_and_load(client, activity: dict, profile: AthleteProfile) -> int | None:
    """Download one activity in memory and compute its load (no disk I/O)."""
    import fitparse

    raw = client.download_activity(activity.get("activityId"), fmt="fit")
    fit_bytes = extract_fit_bytes(raw)
    if not fit_bytes:
        return None
    return activity_load(fitparse.FitFile(io.BytesIO(fit_bytes)), profile)


def _collect_online(
    client, start: date, end: date, profile: AthleteProfile
) -> tuple[dict[date, int], int]:
    """Sum per-day load from activities fetched online (downloaded in memory)."""
    activities = client.get_activities(start.isoformat(), end.isoformat())
    loads_by_day: dict[date, int] = {}
    scanned = 0
    for activity in activities:
        day_str = (activity.get("startTimeLocal") or "")[:10]
        try:
            day = date.fromisoformat(day_str)
        except ValueError:
            continue
        try:
            load = _download_and_load(client, activity, profile)
        except RuntimeError:
            raise
        except Exception:  # noqa: BLE001 -- skip any activity that fails to load
            logger.debug("Skipping activity %s", activity.get("activityId"))
            continue
        scanned += 1
        if load:
            loads_by_day[day] = loads_by_day.get(day, 0) + load
    return loads_by_day, scanned


# --- orchestrator ----------------------------------------------------------


def analyze_readiness(
    profile: AthleteProfile,
    client_factory: Callable[[], object] | None = None,
    downloads_dir: str | Path = DEFAULT_DOWNLOADS_DIR,
    today: date | None = None,
) -> ReadinessReport:
    """Assess current readiness over the fixed :data:`LOOKBACK_DAYS` window.

    Source selection: if ``downloads_dir`` already contains an activity dated
    today, local FIT files are reused (offline); otherwise the window is fetched
    online via ``client_factory`` (downloaded in memory) so the result is
    current.

    Args:
        profile: Athlete HR parameters.
        client_factory: Zero-arg callable returning a Garmin client; required
            only when local data is not up to date.
        downloads_dir: Directory the download command writes to.
        today: Override for "today" (testing).

    Raises:
        RuntimeError: If the profile is incomplete, or online data is needed but
            no ``client_factory`` was supplied.
    """
    today = today or date.today()
    start = today - timedelta(days=LOOKBACK_DAYS)
    # Validate HR params once up front so config errors fail fast.
    profile.trimp_params()

    if has_todays_activity(downloads_dir, today):
        loads_by_day, scanned = _collect_local(downloads_dir, start, today, profile)
        return build_readiness_report(loads_by_day, scanned, start, today, "local")

    if client_factory is None:
        raise RuntimeError(
            "Local data is not up to date and no online client is available."
        )
    client = client_factory()
    loads_by_day, scanned = _collect_online(client, start, today, profile)
    return build_readiness_report(loads_by_day, scanned, start, today, "online")
