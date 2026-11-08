"""Training load: EWMA load, performance management chart, ACWR, monotony and strain.

Inputs are daily load series (one value per calendar day, oldest first). A NaN day counts as
a rest day (load 0).
"""

from __future__ import annotations

import math

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
from numpy.typing import ArrayLike

from garminizer.analytics import FloatArray


def _daily(daily: ArrayLike) -> FloatArray:
    x = np.asarray(daily, dtype=np.float64).ravel()
    return np.where(np.isfinite(x), x, 0.0)


def ewma_load(daily: ArrayLike, tau_days: float, seed: float = 0.0) -> FloatArray:
    """``x_t = x_{t-1} + (load_t - x_{t-1}) * (1 - e^(-1/tau))`` with ``x_{-1} = seed``."""
    if not tau_days > 0:
        raise ValueError("tau_days must be > 0")
    loads: list[float] = _daily(daily).tolist()
    k = 1.0 - math.exp(-1.0 / tau_days)
    out = np.empty(len(loads), dtype=np.float64)
    x = float(seed)
    for i, load in enumerate(loads):
        x += (load - x) * k
        out[i] = x
    return out


def pmc(
    daily_load: ArrayLike,
    ctl_tau: float = 42.0,
    atl_tau: float = 7.0,
    ctl_seed: float = 0.0,
    atl_seed: float = 0.0,
) -> tuple[FloatArray, FloatArray, FloatArray]:
    """Performance management chart: (CTL fitness, ATL fatigue, TSB form).

    ``tsb_t = ctl_{t-1} - atl_{t-1}`` (form = yesterday's fitness minus fatigue), with
    ``tsb_0 = ctl_seed - atl_seed``.
    """
    ctl = ewma_load(daily_load, ctl_tau, ctl_seed)
    atl = ewma_load(daily_load, atl_tau, atl_seed)
    tsb = np.empty_like(ctl)
    if tsb.size:
        tsb[0] = ctl_seed - atl_seed
        tsb[1:] = ctl[:-1] - atl[:-1]
    return ctl, atl, tsb


def _trailing(x: FloatArray, window: int) -> FloatArray | None:
    """Trailing windows (one row per day from ``window - 1`` on), ``None`` if too short."""
    if window < 1:
        raise ValueError("window must be >= 1")
    if x.size < window:
        return None
    return sliding_window_view(x, window)


def acwr(daily_load: ArrayLike, acute_days: int = 7, chronic_days: int = 28) -> FloatArray:
    """Acute:chronic workload ratio (coupled rolling averages).

    Day t: mean of the trailing ``acute_days`` divided by the mean of the trailing
    ``chronic_days`` (both including day t). NaN while either window is incomplete or where
    the chronic mean is 0.
    """
    x = _daily(daily_load)
    out = np.full(x.size, np.nan)
    acute = _trailing(x, acute_days)
    chronic = _trailing(x, chronic_days)
    if acute is None or chronic is None:
        return out
    first = max(acute_days, chronic_days) - 1  # first day with both windows complete
    a = acute.mean(axis=1)[first - (acute_days - 1) :]
    c = chronic.mean(axis=1)[first - (chronic_days - 1) :]
    out[first:] = np.divide(a, c, out=np.full(c.size, np.nan), where=c != 0)
    return out


def monotony_strain(
    daily_load: ArrayLike, window: int = 7, *, ddof: int = 0
) -> tuple[FloatArray, FloatArray]:
    """Foster monotony (mean / SD over the window) and strain (window sum * monotony).

    SD is the population standard deviation by default (``ddof=0``). Both are NaN while the
    window is incomplete and where all loads in the window are equal (SD = 0).
    """
    if window < 2:
        raise ValueError("window must be >= 2")
    x = _daily(daily_load)
    monotony = np.full(x.size, np.nan)
    strain = np.full(x.size, np.nan)
    windows = _trailing(x, window)
    if windows is None:
        return monotony, strain
    flat = windows.max(axis=1) == windows.min(axis=1)
    sd = np.where(flat, 1.0, windows.std(axis=1, ddof=ddof))
    mono = np.where(flat, np.nan, windows.mean(axis=1) / sd)
    monotony[window - 1 :] = mono
    strain[window - 1 :] = windows.sum(axis=1) * mono
    return monotony, strain
