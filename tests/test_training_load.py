"""Tests for garmin.training_load (HR-based load & readiness)."""

from datetime import date, datetime, timedelta

import garmin.training_load as tl
from garmin.config import AthleteProfile
from garmin.training_load import (
    DayLoad,
    acwr,
    analyze_readiness,
    build_readiness_report,
    has_todays_activity,
    recommend,
    rolling_metrics,
)

PROFILE = AthleteProfile(resting_hr=50, max_hr=190, sex="male")


class _Rec:
    def __init__(self, **values):
        self._v = values

    def get_value(self, key):
        return self._v.get(key)


class _Fit:
    """Minimal stand-in for a fitparse.FitFile with `record` messages."""

    def __init__(self, records):
        self._records = records

    def get_messages(self, name):
        assert name == "record"
        return self._records


def _hr_fit(hr, n=300, step_s=1):
    base = datetime(2026, 1, 1, 8, 0, 0)
    return _Fit(
        [
            _Rec(timestamp=base + timedelta(seconds=i * step_s), heart_rate=hr)
            for i in range(n)
        ]
    )


# --- activity_load ---------------------------------------------------------


def test_continuous_hr_yields_positive_load():
    assert tl.activity_load(_hr_fit(150), PROFILE) > 0


def test_higher_average_hr_yields_higher_load():
    low = tl.activity_load(_hr_fit(130), PROFILE)
    high = tl.activity_load(_hr_fit(165), PROFILE)
    assert high > low


def test_sample_gaps_weighted_by_elapsed_time():
    # Same HR and sample count, but one samples every 2 s vs every 1 s: the
    # longer-elapsed activity must accrue roughly double the load.
    short = tl.activity_load(_hr_fit(150, n=300, step_s=1), PROFILE)
    long = tl.activity_load(_hr_fit(150, n=300, step_s=2), PROFILE)
    assert long > short
    assert abs(long - 2 * short) <= 2  # ~2x within rounding


def test_no_hr_returns_none():
    fit = _Fit([_Rec(timestamp=datetime(2026, 1, 1, 8, 0, i)) for i in range(10)])
    assert tl.activity_load(fit, PROFILE) is None


# --- aggregation / report assembly -----------------------------------------


def test_build_report_sums_day_and_zero_fills():
    loads = {date(2026, 1, 1): 120}  # e.g. 80 + 40 summed by the collector
    report = build_readiness_report(
        loads, scanned=3, start=date(2026, 1, 1), end=date(2026, 1, 3), source="local"
    )
    by_day = {m.day: m.load for m in report.days}
    assert by_day[date(2026, 1, 1)] == 120
    assert by_day[date(2026, 1, 2)] == 0  # zero-filled rest day
    assert by_day[date(2026, 1, 3)] == 0
    assert len(report.days) == 3
    assert report.source == "local"


def test_build_report_no_data():
    report = build_readiness_report(
        {}, scanned=0, start=date(2026, 1, 1), end=date(2026, 1, 3), source="online"
    )
    assert report.scanned == 0
    assert report.days == []
    assert report.latest is None
    assert report.recommendation is None


def test_has_todays_activity(tmp_path):
    today = date(2026, 7, 8)
    assert has_todays_activity(tmp_path, today) is False
    (tmp_path / "2026-07-08_1_ride.fit").write_text("x")
    assert has_todays_activity(tmp_path, today) is True
    assert has_todays_activity(tmp_path, date(2026, 7, 9)) is False


class _FakeClient:
    def __init__(self, activities):
        self._activities = activities

    def get_activities(self, start, end, activity_type=None):
        return self._activities

    def download_activity(self, activity_id, fmt="fit"):
        return b"ignored"


def test_analyze_readiness_online_when_local_stale(monkeypatch, tmp_path):
    # No file dated today -> goes online via the injected client factory.
    today = date(2026, 7, 8)
    activities = [
        {"activityId": 1, "startTimeLocal": "2026-07-08 08:00:00"},
        {"activityId": 2, "startTimeLocal": "2026-07-08 18:00:00"},
        {"activityId": 3, "startTimeLocal": "2026-07-06 07:00:00"},
    ]
    load_map = {1: 80, 2: 40, 3: None}
    monkeypatch.setattr(
        tl, "_download_and_load", lambda client, a, prof: load_map[a["activityId"]]
    )

    report = analyze_readiness(
        PROFILE,
        client_factory=lambda: _FakeClient(activities),
        downloads_dir=tmp_path,
        today=today,
    )
    assert report.source == "online"
    assert report.scanned == 3
    by_day = {m.day: m.load for m in report.days}
    assert by_day[date(2026, 7, 8)] == 120  # 80 + 40
    assert by_day[date(2026, 7, 6)] == 0  # activity 3 had no HR load
    assert report.recommendation is not None


def test_analyze_readiness_reuses_local_when_today_present(monkeypatch, tmp_path):
    today = date(2026, 7, 8)
    (tmp_path / "2026-07-08_1_ride.fit").write_text("x")

    def _boom():
        raise AssertionError("should not go online when local is fresh")

    monkeypatch.setattr(
        tl, "_collect_local", lambda d, s, e, p: ({date(2026, 7, 8): 100}, 1)
    )
    report = analyze_readiness(
        PROFILE, client_factory=_boom, downloads_dir=tmp_path, today=today
    )
    assert report.source == "local"
    assert report.scanned == 1


# --- rolling metrics -------------------------------------------------------


def _series(loads):
    base = date(2026, 1, 1)
    return [DayLoad(day=base + timedelta(days=i), load=v) for i, v in enumerate(loads)]


def test_sustained_load_builds_fitness_and_fatigue_atl_faster():
    metrics = rolling_metrics(_series([100] * 20))
    last = metrics[-1]
    assert last.ctl > metrics[0].ctl
    assert last.atl > metrics[0].atl
    assert last.atl > last.ctl  # fatigue rises faster than fitness


def test_rest_lowers_fatigue_and_raises_form():
    metrics = rolling_metrics(_series([100] * 20 + [0] * 10))
    end = metrics[-1]
    after_block = metrics[20]
    assert end.atl < end.ctl  # fatigue decays faster than fitness
    assert end.tsb > after_block.tsb  # Form recovers during rest


# --- ACWR ------------------------------------------------------------------


def test_acwr_balanced_is_about_one():
    val = acwr([50] * 40)
    assert val is not None
    assert abs(val - 1.0) < 0.05


def test_acwr_zero_chronic_is_undefined():
    assert acwr([0] * 40) is None


# --- recommendation --------------------------------------------------------


def test_deep_fatigue_recommends_rest():
    rec = recommend(tsb=-40.0, acwr_value=1.0)
    assert rec.recommendation == "rest"


def test_fresh_and_balanced_recommends_train():
    rec = recommend(tsb=0.0, acwr_value=1.0)
    assert rec.recommendation == "train"
    assert rec.caution is False


def test_load_spike_flags_caution():
    rec = recommend(tsb=-5.0, acwr_value=1.8)
    assert rec.caution is True
    assert rec.recommendation in ("easy", "rest")
