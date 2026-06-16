"""Tests for garmin.power: NP, critical power, decoupling and coasting.

All tests feed synthetic pandas objects / mappings to the pure functions, so
they need no real FIT file or network access. ``analyze_ride`` is exercised
end-to-end with a tiny fake FIT file that mimics ``fitparse``'s
``get_messages`` / ``get_value`` API.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from garmin.power import (
    CP_DURATIONS_S,
    _longest_true_run,
    _phenotype,
    analyze_ride,
    compute_coasting,
    compute_critical_power,
    compute_decoupling,
    mean_max_power,
    normalized_power,
)

# --- helpers ---------------------------------------------------------------


class _Record:
    def __init__(self, **values):
        self._values = values

    def get_value(self, name):
        return self._values.get(name)


class _FakeFitFile:
    def __init__(self, records):
        self._records = records

    def get_messages(self, _kind):
        return self._records


def _ride_records(n=1200):
    """1 Hz records: constant 200 W, HR 100 then 125, pedaling, 5 m/s."""
    start = datetime(2026, 1, 1, 7, 0, 0)
    records = []
    for i in range(n):
        records.append(
            _Record(
                timestamp=start + timedelta(seconds=i),
                power=200.0,
                heart_rate=100.0 if i < n // 2 else 125.0,
                cadence=85.0,
                enhanced_speed=5.0,
            )
        )
    return records


# --- normalized_power ------------------------------------------------------


def test_normalized_power_constant_series():
    assert abs(normalized_power(pd.Series([200.0] * 600)) - 200.0) < 1e-9


def test_normalized_power_too_short():
    assert normalized_power(pd.Series([150.0] * 10)) is None


def test_normalized_power_penalises_variability():
    # Same average (200 W) but variable -> NP must exceed the mean.
    variable = pd.Series(([100.0] * 30 + [300.0] * 30) * 20)
    assert normalized_power(variable) > 200.0


# --- mean_max_power --------------------------------------------------------


def test_mean_max_power_constant():
    mmp = mean_max_power(pd.Series([100.0] * 1000), [60, 300, 1000, 2000])
    assert mmp[60] == 100.0
    assert mmp[300] == 100.0
    assert mmp[1000] == 100.0
    assert 2000 not in mmp  # longer than the series


def test_mean_max_power_finds_peak_window():
    series = pd.Series([100.0] * 1000)
    series.iloc[100:160] = 300.0  # a 60-second block at 300 W
    mmp = mean_max_power(series, [60])
    assert abs(mmp[60] - 300.0) < 1e-9


# --- critical power --------------------------------------------------------


def test_compute_critical_power_recovers_model():
    cp_true, w_true = 250.0, 20000.0
    mmp = {d: cp_true + w_true / d for d in CP_DURATIONS_S}
    cp = compute_critical_power(mmp)
    assert cp is not None
    assert abs(cp.cp_watts - cp_true) < 1e-6
    assert abs(cp.w_prime_j - w_true) < 1e-3
    assert cp.r_squared > 0.9999
    assert cp.n_points == len(CP_DURATIONS_S)
    assert cp.cp_per_kg is None
    assert cp.phenotype == "All-rounder"  # 20 kJ, no weight


def test_compute_critical_power_per_kg():
    mmp = {d: 250.0 + 20000.0 / d for d in CP_DURATIONS_S}
    cp = compute_critical_power(mmp, weight_kg=62.5)
    assert cp is not None
    assert abs(cp.cp_per_kg - 4.0) < 1e-9
    assert abs(cp.w_prime_kj - 20.0) < 1e-6


def test_compute_critical_power_too_few_points():
    assert compute_critical_power({120: 300.0, 600: 260.0}) is None


def test_compute_critical_power_rejects_non_physical():
    # Work decreasing with time -> negative slope (CP <= 0) -> rejected.
    mmp = {120: 400.0, 600: 50.0, 1200: 20.0}
    assert compute_critical_power(mmp) is None


# --- phenotype -------------------------------------------------------------


def test_phenotype_indeterminate_when_no_anaerobic_reserve():
    assert "Indeterminate" in _phenotype(250.0, 0.0, None)
    assert "Indeterminate" in _phenotype(250.0, -5000.0, 4.0)


def test_phenotype_with_weight():
    assert "climber" in _phenotype(250.0, 15000.0, 4.5).lower()
    assert "Sprinter" in _phenotype(250.0, 26000.0, 3.5)
    assert _phenotype(250.0, 21000.0, 4.0) == "All-rounder"


def test_phenotype_without_weight():
    assert "Sprinter-leaning" in _phenotype(250.0, 26000.0, None)
    assert "Time-trial-leaning" in _phenotype(250.0, 14000.0, None)
    assert _phenotype(250.0, 20000.0, None) == "All-rounder"


# --- decoupling ------------------------------------------------------------


def test_compute_decoupling_known_drift():
    frame = pd.DataFrame(
        {
            "power": [200.0] * 1200,
            "heart_rate": [100.0] * 600 + [125.0] * 600,
        }
    )
    dec = compute_decoupling(frame)
    assert dec is not None
    assert abs(dec.first_half_ratio - 2.0) < 1e-6
    assert abs(dec.second_half_ratio - 1.6) < 1e-6
    assert abs(dec.decoupling_pct - 20.0) < 1e-6
    assert abs(dec.np_watts - 200.0) < 1e-6
    assert abs(dec.avg_hr - 112.5) < 1e-6
    assert abs(dec.efficiency_factor - 200.0 / 112.5) < 1e-6
    assert dec.is_coupled is False


def test_compute_decoupling_coupled_when_steady():
    frame = pd.DataFrame(
        {"power": [200.0] * 1200, "heart_rate": [120.0] * 1200}
    )
    dec = compute_decoupling(frame)
    assert dec is not None
    assert abs(dec.decoupling_pct) < 1e-6
    assert dec.is_coupled is True


def test_compute_decoupling_too_short():
    frame = pd.DataFrame({"power": [200.0] * 100, "heart_rate": [120.0] * 100})
    assert compute_decoupling(frame) is None


def test_compute_decoupling_requires_hr():
    assert compute_decoupling(pd.DataFrame({"power": [200.0] * 1200})) is None


# --- coasting --------------------------------------------------------------


def _coasting_frame(n=600):
    speed = np.zeros(n)
    speed[60:] = 5.0  # stopped for 60 s, then moving
    cadence = np.zeros(n)
    cadence[60:500] = 85.0  # pedaling 440 s, then coasting 100 s
    return pd.DataFrame({"speed": speed, "cadence": cadence})


def test_compute_coasting_breakdown():
    co = compute_coasting(_coasting_frame())
    assert co is not None
    assert co.elapsed_s == 600.0
    assert co.moving_s == 540.0
    assert co.stopped_s == 60.0
    assert co.pedaling_s == 440.0
    assert co.coasting_s == 100.0
    assert co.longest_coast_s == 100.0
    assert abs(co.coasting_pct - 100.0 / 540.0 * 100.0) < 1e-9
    assert abs(co.pedaling_pct - 440.0 / 540.0 * 100.0) < 1e-9


def test_compute_coasting_power_proxy_without_speed():
    n = 600
    power = np.zeros(n)
    power[60:] = 150.0
    cadence = np.zeros(n)
    cadence[60:500] = 85.0
    co = compute_coasting(pd.DataFrame({"power": power, "cadence": cadence}))
    assert co is not None
    assert co.moving_s == 540.0
    assert co.coasting_s == 100.0


def test_compute_coasting_needs_cadence_or_power():
    speed = np.full(600, 5.0)
    assert compute_coasting(pd.DataFrame({"speed": speed})) is None


# --- _longest_true_run -----------------------------------------------------


def test_longest_true_run():
    assert _longest_true_run([False, True, True, False, True, True, True, False]) == 3
    assert _longest_true_run([True, True, True]) == 3
    assert _longest_true_run([False, False]) == 0
    assert _longest_true_run([]) == 0


# --- analyze_ride (integration with a fake FIT file) -----------------------


def test_analyze_ride_end_to_end():
    analysis = analyze_ride(_FakeFitFile(_ride_records(1200)), weight_kg=70.0)
    assert analysis.has_power is True
    assert analysis.has_hr is True
    assert abs(analysis.duration_min - 20.0) < 0.05

    assert analysis.decoupling is not None
    assert abs(analysis.decoupling.decoupling_pct - 20.0) < 0.5

    # Constant 200 W -> CP ~ 200 W, W' ~ 0 (no anaerobic signal).
    assert analysis.critical_power is not None
    assert abs(analysis.critical_power.cp_watts - 200.0) < 1e-3
    assert abs(analysis.critical_power.w_prime_j) < 1.0

    # Always moving (5 m/s) and always pedaling (85 rpm) -> no coasting.
    assert analysis.coasting is not None
    assert analysis.coasting.moving_s == 1200.0
    assert analysis.coasting.coasting_s == 0.0


def test_analyze_ride_no_records():
    analysis = analyze_ride(_FakeFitFile([]))
    assert analysis.has_power is False
    assert analysis.decoupling is None
    assert analysis.critical_power is None
    assert analysis.coasting is None
