"""S3a: LTTB, even splits, elevation hysteresis, rolling mean, trend and correlation."""

from __future__ import annotations

import math

import numpy as np
import pytest

from garminizer.analytics.series import (
    Split,
    elevation_gain_loss,
    even_splits,
    lagged_pairs,
    linear_trend,
    lttb,
    pearson,
    rolling_mean,
)

NAN = math.nan


def _close(got: object, expected: list[float]) -> None:
    np.testing.assert_allclose(
        np.asarray(got, dtype=float), np.array(expected), rtol=1e-12, atol=1e-12, equal_nan=True
    )


# --- LTTB -------------------------------------------------------------------------------------


def test_lttb_hand_computed_three_points() -> None:
    # one bucket {1, 2, 3}; triangle with (0, 0) and the last point (4, 0): area ~ 4*|y|
    assert lttb([0, 1, 2, 3, 4], [0, 5, 0, -5, 0], 3).tolist() == [0, 1, 4]


def test_lttb_hand_computed_four_points() -> None:
    # buckets {1, 2} and {3, 4}: picks 2 (area 41 vs 6.5), then 4 (area 34 vs 14)
    x = [0, 1, 2, 3, 4, 5]
    assert lttb(x, [0, 1, 10, 2, -8, 0], 4).tolist() == [0, 2, 4, 5]


def test_lttb_nan_points_are_never_selected() -> None:
    x = [0, 1, 2, 3, 4, 5]
    assert lttb(x, [0, 1, NAN, 2, -8, 0], 4).tolist() == [0, 1, 4, 5]
    # an all-NaN bucket yields its first index
    assert lttb(x, [0, NAN, NAN, 2, -8, 0], 4).tolist() == [0, 1, 4, 5]


def test_lttb_keeps_endpoints_and_peaks() -> None:
    x = np.arange(1000, dtype=float)
    y = np.sin(x / 50.0)
    y[400] = 50.0
    y[777] = -50.0
    idx = lttb(x, y, 100)
    assert idx.size == 100
    assert idx.dtype == np.intp
    assert idx[0] == 0
    assert idx[-1] == 999
    assert {400, 777} <= set(idx.tolist())
    assert np.all(np.diff(idx) > 0)


def test_lttb_returns_everything_when_not_reducing() -> None:
    assert lttb([0, 1, 2], [1, 2, 3], 3).tolist() == [0, 1, 2]
    assert lttb([0, 1, 2, 3], [1, 2, 3, 4], 10).tolist() == [0, 1, 2, 3]
    assert lttb([0, 1, 2, 3], [1, 2, 3, 4], 2).tolist() == [0, 1, 2, 3]
    assert lttb([], [], 5).tolist() == []
    with pytest.raises(ValueError):
        lttb([0, 1], [0], 3)


# --- elevation --------------------------------------------------------------------------------


def test_elevation_hysteresis_counts_full_legs() -> None:
    alt = [100, 101, 103, 102, 104, 100, 99, 99.5, 105]
    # climb 100 -> 104 (4), descent 104 -> 99 (5), climb 99 -> 105 (6)
    assert elevation_gain_loss(alt, 2.0) == pytest.approx((10.0, 5.0))


def test_elevation_ignores_noise_and_nan() -> None:
    assert elevation_gain_loss([100, 101, 100, 101.5, 100], 2.0) == (0.0, 0.0)
    assert elevation_gain_loss([100, NAN, 105, NAN, 95], 2.0) == pytest.approx((5.0, 10.0))
    assert elevation_gain_loss([110, 109, 105, 106, 104], 2.0) == pytest.approx((0.0, 6.0))
    assert elevation_gain_loss([0, 1, 0, 2], 0.0) == pytest.approx((3.0, 1.0))


def test_elevation_edge_cases() -> None:
    assert elevation_gain_loss([]) == (0.0, 0.0)
    assert elevation_gain_loss([123.0]) == (0.0, 0.0)
    assert elevation_gain_loss([NAN, NAN]) == (0.0, 0.0)
    with pytest.raises(ValueError):
        elevation_gain_loss([1, 2], -1)


# --- even splits ------------------------------------------------------------------------------


def _constant_run() -> tuple[np.ndarray, np.ndarray]:
    t = np.arange(0, 1101, dtype=float)
    return t, 4.0 * t  # 4 m/s, 4400 m


def test_even_splits_constant_speed_with_extras_and_altitude() -> None:
    t, d = _constant_run()
    hr = np.where(t < 600, 100.0, 150.0)
    cadence = np.full(t.size, NAN)
    alt = np.where(d <= 2000, 0.01 * d, 20.0 - 0.01 * (d - 2000))
    splits = even_splits(t, d, extras={"hr": hr, "cadence": cadence}, altitude=alt)

    assert [s.index for s in splits] == [1, 2, 3, 4, 5]
    _close([s.distance_m for s in splits], [1000, 1000, 1000, 1000, 400])
    _close([s.duration_s for s in splits], [250, 250, 250, 250, 100])
    # split 3 = 100 s at 100 bpm + 150 s at 150 bpm -> 130
    _close([s.averages["hr"] for s in splits], [100, 100, 130, 150, 150])
    assert all(s.averages["cadence"] is None for s in splits)
    _close([s.elevation_gain_m for s in splits], [10, 10, 0, 0, 0])
    _close([s.elevation_loss_m for s in splits], [0, 0, 10, 10, 4])
    assert isinstance(splits[0], Split)
    assert list(splits[0].averages) == ["hr", "cadence"]


def test_even_splits_interpolates_crossing_time() -> None:
    t = np.arange(0, 401, dtype=float)
    splits = even_splits(t, 3.0 * t)  # 1200 m; 1000 m is crossed at t = 333.33...
    _close([s.duration_s for s in splits], [1000 / 3, 200 / 3])
    _close([s.distance_m for s in splits], [1000, 200])
    assert splits[0].averages == {}
    assert splits[0].elevation_gain_m is None
    assert splits[0].elevation_loss_m is None


def test_even_splits_partial_threshold_and_offset_start() -> None:
    t = np.arange(0, 1013, dtype=float)
    assert len(even_splits(t, t)) == 1  # 12 m remainder < 10 % of 1000 m
    tail = even_splits(t, t, min_partial_fraction=0.0)
    _close([s.distance_m for s in tail], [1000, 12])
    # odometer already at 3.2 m on the first sample: first split ends at the 1000 m mark
    t2 = np.arange(0, 1001, dtype=float)
    only = even_splits(t2, 3.2 + t2)
    assert len(only) == 1
    assert only[0].distance_m == pytest.approx(996.8, rel=1e-12)
    assert only[0].duration_s == pytest.approx(996.8, rel=1e-12)


def test_even_splits_short_and_invalid_input() -> None:
    assert even_splits([], []) == []
    assert even_splits([0.0], [0.0]) == []
    assert even_splits([0, 10], [0, 50]) == []  # 50 m < 10 % of a 1000 m split
    one = even_splits([0, NAN, 100], [0, 50, 500], split_m=400)
    _close([s.distance_m for s in one], [400, 100])
    no_alt = even_splits([0, 100], [0, 500], split_m=400, altitude=[NAN, NAN])
    assert [(s.elevation_gain_m, s.elevation_loss_m) for s in no_alt] == [(None, None)] * 2
    with pytest.raises(ValueError):
        even_splits([0, 1], [0, 1], split_m=0)
    with pytest.raises(ValueError):
        even_splits([0, 1], [0, 1], extras={"hr": [1, 2, 3]})


# --- rolling mean -----------------------------------------------------------------------------


def test_rolling_mean_trailing_window() -> None:
    _close(rolling_mean([1, 2, 3, 4], 2), [NAN, 1.5, 2.5, 3.5])
    _close(rolling_mean([1, 2, 3, 4], 2, min_periods=1), [1, 1.5, 2.5, 3.5])
    _close(rolling_mean([1, 2, 3, 4], 3), [NAN, NAN, 2, 3])


def test_rolling_mean_nan_aware() -> None:
    _close(rolling_mean([1, NAN, 3, 5], 2, min_periods=1), [1, 1, 3, 4])
    _close(rolling_mean([1, NAN, 3, 5], 2), [NAN, NAN, NAN, 4])
    assert rolling_mean([], 3).size == 0
    with pytest.raises(ValueError):
        rolling_mean([1, 2], 0)
    with pytest.raises(ValueError):
        rolling_mean([1, 2], 2, min_periods=3)


# --- trend and correlation --------------------------------------------------------------------


def test_linear_trend_exact_and_noisy() -> None:
    assert linear_trend([0, 1, 2, 3], [1, 3, 5, 7]) == pytest.approx((2.0, 1.0, 1.0))
    # sxx = 5, sxy = 4.5, syy = 4.75 -> slope 0.9, intercept -0.1, r2 = 20.25 / 23.75
    got = linear_trend([0, 1, 2, 3, NAN], [0, 1, 1, 3, 9])
    assert got == pytest.approx((0.9, -0.1, 20.25 / 23.75), rel=1e-12)


def test_linear_trend_degenerate() -> None:
    slope, intercept, r2 = linear_trend([0, 1, 2], [4, 4, 4])
    assert (slope, intercept) == pytest.approx((0.0, 4.0))
    assert math.isnan(r2)
    with pytest.raises(ValueError):
        linear_trend([1], [1])
    with pytest.raises(ValueError):
        linear_trend([1, NAN], [1, 2])
    with pytest.raises(ValueError):
        linear_trend([2, 2], [1, 3])


def test_pearson_known_values() -> None:
    r, n = pearson([1, 2, 3, 4, 5], [2, 4, 5, 4, 5])
    assert n == 5
    assert r == pytest.approx(6 / math.sqrt(60), rel=1e-12)  # 0.7745966692414834
    r, n = pearson([1, 2, 3, NAN], [3, 2, 1, 0])
    assert r == pytest.approx(-1.0)
    assert n == 3


def test_pearson_degenerate() -> None:
    r, n = pearson([1, 2], [1, 2])
    assert math.isnan(r)
    assert n == 2
    r, n = pearson([1, 1, 1], [1, 2, 3])
    assert math.isnan(r)
    assert n == 3


def test_lagged_pairs() -> None:
    x = [1, 3, 2, 5, 4, 6]
    y = [0, 1, 3, 2, 5, 4]  # y[t + 1] == x[t]
    rs = [pearson(*lagged_pairs(x, y, k)) for k in range(3)]
    assert [n for _, n in rs] == [6, 5, 4]
    _close([r for r, _ in rs], [0.6, 1.0, 0.5 / math.sqrt(43.75)])
    xs, ys = lagged_pairs([1, 2, 3], [4, 5, 6], 1)
    assert xs.tolist() == [1, 2] and ys.tolist() == [5, 6]
    assert [a.size for a in lagged_pairs([1, 2, 3], [1, 2, 3], 3)] == [0, 0]
    with pytest.raises(ValueError):
        lagged_pairs([1], [1], -1)
    with pytest.raises(ValueError):
        lagged_pairs([1, 2], [1], 0)
