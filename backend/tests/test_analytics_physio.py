"""S3a: physiology metrics (TRIMP, zones, NP/IF/TSS, EF, decoupling) on hand-computed data."""

from __future__ import annotations

import math

import numpy as np
import pytest

from garminizer.analytics.physio import (
    aerobic_decoupling,
    efficiency_factor,
    hr_zone_seconds,
    intensity_factor,
    normalized_power,
    training_stress_score,
    trimp_banister,
)

NAN = math.nan


# --- TRIMP ------------------------------------------------------------------------------------


def test_trimp_male_one_minute_at_half_reserve() -> None:
    # HRr = (120 - 50) / (190 - 50) = 0.5 for 60 s: 1 min * 0.5 * 0.64 * e^0.96
    hr = [120.0] * 60
    assert trimp_banister(hr, 1.0, 50, 190) == pytest.approx(0.8357428714953977, rel=1e-12)
    assert trimp_banister(hr, 1.0, 50, 190) == pytest.approx(0.32 * math.exp(0.96), rel=1e-12)


def test_trimp_female_coefficients() -> None:
    # 1 min * 0.5 * 0.86 * e^(1.67 * 0.5)
    got = trimp_banister([120.0] * 60, 1, 50, 190, sex="female")
    assert got == pytest.approx(0.9910700407634154, rel=1e-12)


def test_trimp_clips_reserve_and_ignores_nan() -> None:
    # 30 s below rest (HRr clipped to 0), 60 s above max (clipped to 1), NaN samples add 0.
    hr = [40.0] * 30 + [200.0] * 60 + [NAN] * 10
    assert trimp_banister(hr, 1, 50, 190) == pytest.approx(0.64 * math.exp(1.92), rel=1e-12)


def test_trimp_per_sample_durations() -> None:
    # two samples at HRr 0.5 lasting 30 s and 90 s = 2 minutes
    got = trimp_banister([120.0, 120.0], [30.0, 90.0], 50, 190)
    assert got == pytest.approx(2 * 0.32 * math.exp(0.96), rel=1e-12)


def test_trimp_edge_cases() -> None:
    assert trimp_banister([], 1, 50, 190) == 0.0
    assert trimp_banister([NAN, NAN], 1, 50, 190) == 0.0
    with pytest.raises(ValueError):
        trimp_banister([120.0], 1, 50, 190, sex="other")
    with pytest.raises(ValueError):
        trimp_banister([120.0], 1, 190, 190)
    with pytest.raises(ValueError):
        trimp_banister([120.0, 130.0], [1.0, 1.0, 1.0], 50, 190)


# --- HR zones ---------------------------------------------------------------------------------


def test_hr_zone_seconds_boundaries_and_open_top_zone() -> None:
    floors = [100, 120, 140, 160, 180]
    hr = [90, 100, 119, 120, 150, 185, NAN]
    # below=90 | z1=100,119 | z2=120 | z3=150 | z4=- | z5=185 ; 2 s per sample
    assert hr_zone_seconds(hr, 2.0, floors) == [2.0, 4.0, 2.0, 2.0, 0.0, 2.0]


def test_hr_zone_seconds_per_sample_dt_and_empty() -> None:
    assert hr_zone_seconds([110, 130], [5.0, 7.5], [100, 120]) == [0.0, 5.0, 7.5]
    assert hr_zone_seconds([], 1.0, [100, 120]) == [0.0, 0.0, 0.0]
    assert hr_zone_seconds([NAN], 1.0, [100]) == [0.0, 0.0]


def test_hr_zone_seconds_rejects_unsorted_floors() -> None:
    with pytest.raises(ValueError):
        hr_zone_seconds([120], 1, [140, 120])
    with pytest.raises(ValueError):
        hr_zone_seconds([120], 1, [120, 120])


# --- Normalized power, IF, TSS ----------------------------------------------------------------


def test_normalized_power_constant_is_the_constant() -> None:
    assert normalized_power([200.0] * 60) == pytest.approx(200.0, rel=1e-12)


def test_normalized_power_step_matches_brute_force() -> None:
    # 30 s at 100 W then 30 s at 300 W: 31 windows with means 100 + 200 * i / 30.
    power = [100.0] * 30 + [300.0] * 30
    expected = (sum((100 + 200 * i / 30) ** 4 for i in range(31)) / 31) ** 0.25
    assert normalized_power(power) == pytest.approx(expected, rel=1e-12)


def test_normalized_power_drops_windows_with_nan() -> None:
    # Only two NaN-free windows: [0, 30) at 100 W and [60, 90) at 300 W.
    power = [100.0] * 30 + [NAN] * 30 + [300.0] * 30
    expected = ((100**4 + 300**4) / 2) ** 0.25  # 253.0439534435243
    assert normalized_power(power) == pytest.approx(expected, rel=1e-12)
    assert expected == pytest.approx(253.0439534435243, rel=1e-12)
    # A NaN must not act as 0 W: the clean windows are all 200 W.
    with_gap = [200.0] * 40
    with_gap[35] = NAN
    assert normalized_power(with_gap) == pytest.approx(200.0, rel=1e-12)


def test_normalized_power_none_cases() -> None:
    assert normalized_power([]) is None
    assert normalized_power([250.0] * 29) is None
    assert normalized_power([NAN] * 100) is None
    alternating = [200.0 if i % 2 else NAN for i in range(120)]  # 60 valid, no clean window
    assert normalized_power(alternating) is None


def test_intensity_factor_and_tss() -> None:
    assert intensity_factor(250, 250) == pytest.approx(1.0)
    assert intensity_factor(200, 250) == pytest.approx(0.8)
    assert training_stress_score(3600, 250, 250) == pytest.approx(100.0, rel=1e-12)
    # 1800 * 200 * 0.8 / (250 * 3600) * 100 = 32
    assert training_stress_score(1800, 200, 250) == pytest.approx(32.0, rel=1e-12)


@pytest.mark.parametrize(
    ("np_w", "ftp_w"), [(None, 250.0), (200.0, None), (200.0, 0.0), (200.0, -5.0), (NAN, 250.0)]
)
def test_intensity_factor_and_tss_none(np_w: float | None, ftp_w: float | None) -> None:
    assert intensity_factor(np_w, ftp_w) is None
    assert training_stress_score(3600, np_w, ftp_w) is None


def test_tss_none_for_missing_duration() -> None:
    assert training_stress_score(None, 200, 250) is None
    assert training_stress_score(NAN, 200, 250) is None


# --- Efficiency factor and decoupling ---------------------------------------------------------


def test_efficiency_factor_uses_positive_finite_pairs() -> None:
    output = [200, 210, 0, NAN, 220, 190]
    hr = [100, 140, 120, 130, 0, 120]
    # valid pairs: (200, 100), (210, 140), (190, 120) -> 200 / 120
    assert efficiency_factor(output, hr) == pytest.approx(200 / 120, rel=1e-12)
    assert efficiency_factor([0, NAN], [100, 120]) is None
    assert efficiency_factor([], []) is None
    with pytest.raises(ValueError):
        efficiency_factor([1, 2], [1])


def test_aerobic_decoupling_synthetic_halves() -> None:
    output = np.full(1200, 200.0)
    hr = np.concatenate((np.full(600, 100.0), np.full(600, 110.0)))
    # EF1 = 2.0, EF2 = 200/110 -> (1 - 100/110) * 100 = 9.0909...%
    assert aerobic_decoupling(output, hr) == pytest.approx(100 / 11, rel=1e-12)
    # HR falling in the second half gives a negative value: EF2 = 2.5 -> -25 %
    falling = np.concatenate((np.full(600, 100.0), np.full(600, 80.0)))
    assert aerobic_decoupling(output, falling) == pytest.approx(-25.0, rel=1e-12)


def test_aerobic_decoupling_min_samples_and_odd_split() -> None:
    assert aerobic_decoupling(np.full(1199, 200.0), np.full(1199, 100.0)) is None
    with_invalid = np.full(1300, 200.0)
    with_invalid[:101] = 0.0  # only 1199 valid samples remain
    assert aerobic_decoupling(with_invalid, np.full(1300, 100.0)) is None
    # Odd count: first half = first 2 samples (EF 2), second = last 3 (EF 1) -> 50 %
    got = aerobic_decoupling([100] * 5, [50, 50, 100, 100, 100], min_samples=2)
    assert got == pytest.approx(50.0, rel=1e-12)
    assert aerobic_decoupling([100], [50], min_samples=1) is None
