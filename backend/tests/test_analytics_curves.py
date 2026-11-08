"""S3a: 1 Hz resampling, mean-max curves and best distance efforts."""

from __future__ import annotations

import math
import time

import numpy as np
import pytest

from garminizer.analytics import FloatArray
from garminizer.analytics.curves import (
    STANDARD_DISTANCES_M,
    STANDARD_DURATIONS_S,
    best_distance_times,
    mean_max,
    resample_1hz,
)

NAN = math.nan


def _nan_equal(got: FloatArray, expected: list[float]) -> None:
    np.testing.assert_allclose(got, np.array(expected, dtype=float), rtol=1e-12, equal_nan=True)


def test_standard_tables() -> None:
    assert STANDARD_DURATIONS_S[0] == 1
    assert STANDARD_DURATIONS_S[-1] == 18000
    assert len(STANDARD_DURATIONS_S) == 33
    assert list(STANDARD_DURATIONS_S) == sorted(set(STANDARD_DURATIONS_S))
    assert STANDARD_DISTANCES_M == (400, 1000, 1609.344, 5000, 10000, 15000, 21097.5, 30000, 42195)


# --- resample_1hz -----------------------------------------------------------------------------


def test_resample_linear_interpolation() -> None:
    _nan_equal(resample_1hz([0, 2, 4], [0, 10, 20]), [0, 5, 10, 15, 20])


def test_resample_grid_starts_at_first_timestamp() -> None:
    # grid t = 100.5, 101.5, 102.5; 102.5 lies 2/3 of the way from (101.5, 2) to (103, 5)
    _nan_equal(resample_1hz([100.5, 101.5, 103.0], [1, 2, 5]), [1, 2, 4])


def test_resample_long_gap_becomes_nan() -> None:
    got = resample_1hz([0, 1, 20, 21], [1, 1, 3, 3], max_gap_s=10)
    assert got.size == 22
    _nan_equal(got[:2], [1, 1])
    assert np.isnan(got[2:20]).all()
    _nan_equal(got[20:], [3, 3])
    # a gap of exactly max_gap_s is still bridged
    _nan_equal(resample_1hz([0, 10], [0, 10], max_gap_s=10), list(range(11)))


def test_resample_nan_values_are_bridged_or_left_out() -> None:
    _nan_equal(resample_1hz([0, 1, 2, 3], [0, NAN, 2, 3]), [0, 1, 2, 3])
    _nan_equal(resample_1hz([0, 1, 2], [NAN, 1, 2]), [NAN, 1, 2])
    _nan_equal(resample_1hz([0, 1, 2], [NAN, NAN, NAN]), [NAN, NAN, NAN])


def test_resample_edge_cases() -> None:
    assert resample_1hz([], []).size == 0
    _nan_equal(resample_1hz([5.0], [7.0]), [7.0])
    _nan_equal(resample_1hz([0, 0, 1], [1, 2, 3]), [2, 3])  # duplicate time keeps the last
    with pytest.raises(ValueError):
        resample_1hz([2, 1], [0, 0])
    with pytest.raises(ValueError):
        resample_1hz([0, 1], [0])


# --- mean_max ---------------------------------------------------------------------------------


def test_mean_max_known_array() -> None:
    got = mean_max([1, 3, 2, 5, 4], durations=(1, 2, 3, 5, 10))
    assert got == pytest.approx({1: 5.0, 2: 4.5, 3: 11 / 3, 5: 3.0}, rel=1e-12)
    assert 10 not in got


def test_mean_max_excludes_windows_with_nan() -> None:
    got = mean_max([10, NAN, 8, 8, 1], durations=(1, 2, 3, 4))
    # d=2: [8, 8] ; d=3: [8, 8, 1] ; d=4: every window holds the NaN -> omitted
    assert got == pytest.approx({1: 10.0, 2: 8.0, 3: 17 / 3}, rel=1e-12)


def test_mean_max_constant_default_durations() -> None:
    got = mean_max(np.full(3600, 250.0))
    assert list(got) == [d for d in STANDARD_DURATIONS_S if d <= 3600]
    assert all(v == pytest.approx(250.0, rel=1e-12) for v in got.values())


def test_mean_max_matches_brute_force() -> None:
    rng = np.random.default_rng(7)
    x = rng.uniform(0, 400, 300)
    x[rng.choice(300, 15, replace=False)] = NAN
    durations = (1, 2, 5, 17, 30, 60, 299, 300)
    got = mean_max(x, durations)
    for d in durations:
        windows = [x[i : i + d] for i in range(len(x) - d + 1)]
        clean = [w.mean() for w in windows if not np.isnan(w).any()]
        if clean:
            assert got[d] == pytest.approx(max(clean), rel=1e-10)
        else:
            assert d not in got


def test_mean_max_edge_cases() -> None:
    assert mean_max([]) == {}
    assert mean_max([NAN, NAN]) == {}
    assert mean_max([123.0]) == {1: 123.0}
    with pytest.raises(ValueError):
        mean_max([1.0, 2.0], durations=(0,))


def test_mean_max_performance_18000_samples() -> None:
    x = np.random.default_rng(1).uniform(0, 500, 18000)
    start = time.perf_counter()
    got = mean_max(x)
    elapsed = time.perf_counter() - start
    assert len(got) == len(STANDARD_DURATIONS_S)
    assert elapsed < 2.0


# --- best_distance_times ----------------------------------------------------------------------


def test_best_distance_times_constant_speed() -> None:
    t = np.arange(0, 3001, dtype=float)
    d = 4.0 * t  # 4 m/s, 12 km total
    got = best_distance_times(t, d)
    assert got == pytest.approx(
        {400: 100.0, 1000: 250.0, 1609.344: 402.336, 5000: 1250.0, 10000: 2500.0}, rel=1e-9
    )
    assert 15000 not in got


def test_best_distance_times_picks_fastest_section() -> None:
    # 500 s at 2 m/s (1000 m) then 200 s at 5 m/s (1000 m)
    t = np.arange(0, 701, dtype=float)
    d = np.where(t <= 500, 2.0 * t, 1000.0 + 5.0 * (t - 500))
    got = best_distance_times(t, d, targets_m=(400, 1000, 1500, 2000, 2001))
    # 1500 m = all 1000 fast metres (200 s) + 500 slow metres (250 s)
    assert got == pytest.approx({400: 80.0, 1000: 200.0, 1500: 450.0, 2000: 700.0}, rel=1e-9)


def test_best_distance_times_with_a_stop() -> None:
    # 1 m/s for 10 s, stopped 5 s at 10 m, then 1 m/s again up to 15 m at t = 20
    t = np.arange(0, 21, dtype=float)
    d = np.concatenate((np.arange(0, 11), np.full(5, 10), np.arange(11, 16))).astype(float)
    got = best_distance_times(t, d, targets_m=(3, 10, 12, 15))
    # 3 m can start at the end of the stop (latest moment at 10 m) -> 3 s
    # 12 m must include the 5 s stop -> 17 s ; 15 m is everything -> 20 s
    assert got == pytest.approx({3: 3.0, 10: 10.0, 12: 17.0, 15: 20.0}, rel=1e-12)


def test_best_distance_times_edge_cases() -> None:
    assert best_distance_times([], []) == {}
    assert best_distance_times([0.0], [0.0]) == {}
    assert best_distance_times([0, 1, 2], [NAN, NAN, NAN]) == {}
    # odometer starting above zero and a small regression are handled
    got = best_distance_times([0, 10, 20, 30], [100, 500, 499, 900], targets_m=(400, 800))
    assert got == pytest.approx({400: 10.0, 800: 30.0}, rel=1e-12)
    with pytest.raises(ValueError):
        best_distance_times([0, 1], [0, 1], targets_m=(0,))
