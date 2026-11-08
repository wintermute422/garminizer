"""S3a: EWMA load, PMC, ACWR, monotony and strain on hand-computed series."""

from __future__ import annotations

import math

import numpy as np
import pytest

from garminizer.analytics.load import acwr, ewma_load, monotony_strain, pmc

NAN = math.nan
K7 = 1 - math.exp(-1 / 7)  # 0.1331221002498184
K42 = 1 - math.exp(-1 / 42)  # 0.023528313347756735


def _close(got: object, expected: list[float]) -> None:
    np.testing.assert_allclose(
        np.asarray(got, dtype=float), np.array(expected), rtol=1e-12, atol=1e-12, equal_nan=True
    )


def test_ewma_single_impulse_tau7() -> None:
    # x0 = 100 * k, then decays by e^(-1/7) per day
    _close(ewma_load([100, 0, 0], 7), [13.312210024981841, 11.54006066748957, 10.003823554423038])
    assert pytest.approx(0.1331221002498184, rel=1e-15) == K7


def test_ewma_seed_and_steady_state() -> None:
    _close(ewma_load([0], 7, seed=50), [50 * (1 - K7)])  # 43.343894987509...
    _close(ewma_load([80, 80, 80], 42, seed=80), [80, 80, 80])
    _close(ewma_load([NAN, 100], 7), [0, 100 * K7])  # NaN day = rest day
    assert ewma_load([], 7).size == 0
    with pytest.raises(ValueError):
        ewma_load([1], 0)


def test_pmc_impulse_exact_values() -> None:
    ctl, atl, tsb = pmc([100, 0, 0])
    _close(ctl, [2.3528313347756735, 2.2974731818766507, 2.2434175129453893])
    _close(atl, [13.312210024981841, 11.54006066748957, 10.003823554423038])
    # form = yesterday's fitness - fatigue; day 0 uses the seeds
    _close(tsb, [0.0, -10.959378690206167, -9.242587485612919])
    assert ctl[0] == pytest.approx(100 * K42, rel=1e-15)


def test_pmc_seeds_and_empty() -> None:
    ctl, atl, tsb = pmc([0], ctl_seed=60, atl_seed=70)
    _close(ctl, [60 * (1 - K42)])
    _close(atl, [70 * (1 - K7)])
    _close(tsb, [-10.0])
    ctl, atl, tsb = pmc([])
    assert ctl.size == atl.size == tsb.size == 0


def test_acwr_small_windows() -> None:
    # acute 2 days / chronic 3 days
    _close(acwr([0, 0, 1, 2, 3], acute_days=2, chronic_days=3), [NAN, NAN, 1.5, 1.5, 1.25])
    # chronic mean 0 -> NaN
    _close(acwr([0, 0, 0, 1], acute_days=2, chronic_days=3), [NAN, NAN, NAN, 1.5])


def test_acwr_default_windows() -> None:
    loads = [10.0] * 28 + [20.0] * 7
    got = acwr(loads)
    assert np.isnan(got[:27]).all()
    assert got[27] == pytest.approx(1.0, rel=1e-12)
    # day 28: acute (6*10 + 20)/7, chronic (27*10 + 20)/28 -> 320/290
    assert got[28] == pytest.approx(320 / 290, rel=1e-12)
    # day 34: acute 20, chronic (21*10 + 7*20)/28 = 12.5
    assert got[34] == pytest.approx(1.6, rel=1e-12)
    assert np.isnan(acwr([5.0] * 27)).all()
    assert np.isnan(acwr([0.0] * 40)).all()
    assert acwr([]).size == 0


def test_monotony_strain_alternating_week() -> None:
    week = [100, 0, 100, 0, 100, 0, 100]
    mono, strain = monotony_strain(week)
    assert np.isnan(mono[:6]).all()
    assert np.isnan(strain[:6]).all()
    # mean = 400/7, population SD = 100 * sqrt(p(1-p)) with p = 4/7 -> mean/SD = sqrt(4/3)
    assert mono[6] == pytest.approx(1.1547005383792515, rel=1e-12)
    assert strain[6] == pytest.approx(461.8802153517006, rel=1e-12)
    # sample SD (ddof=1) -> sqrt(4/3) / sqrt(7/6) = sqrt(8/7)
    mono1, _ = monotony_strain(week, ddof=1)
    assert mono1[6] == pytest.approx(math.sqrt(8 / 7), rel=1e-12)
    # NaN counts as a rest day (0)
    mono_nan, _ = monotony_strain([100, NAN, 100, 0, 100, 0, 100])
    assert mono_nan[6] == pytest.approx(math.sqrt(4 / 3), rel=1e-12)


def test_monotony_strain_flat_and_short() -> None:
    mono, strain = monotony_strain([50.0] * 8)
    assert np.isnan(mono).all()
    assert np.isnan(strain).all()
    mono, strain = monotony_strain([1, 2, 3])
    assert mono.size == 3
    assert np.isnan(mono).all()
    with pytest.raises(ValueError):
        monotony_strain([1, 2, 3], window=1)
