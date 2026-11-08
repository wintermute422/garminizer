"""Power/pace curves: 1 Hz resampling, mean-max values and best efforts over distances."""

from __future__ import annotations

import math
from collections.abc import Iterable

import numpy as np
from numpy.typing import ArrayLike

from garminizer.analytics import FloatArray

STANDARD_DURATIONS_S: tuple[int, ...] = (
    1, 2, 3, 5, 10, 15, 20, 30, 45, 60, 90, 120, 180, 240, 300, 360, 420, 480, 600, 720, 900,
    1200, 1500, 1800, 2400, 2700, 3600, 4500, 5400, 7200, 10800, 14400, 18000,
)  # fmt: skip
STANDARD_DISTANCES_M: tuple[float, ...] = (
    400, 1000, 1609.344, 5000, 10000, 15000, 21097.5, 30000, 42195,
)  # fmt: skip


def resample_1hz(t_s: ArrayLike, values: ArrayLike, max_gap_s: float = 10.0) -> FloatArray:
    """Linearly interpolate ``values`` onto a 1 s grid.

    Output index ``i`` corresponds to ``t = t_s[0] + i`` for ``i = 0..floor(t_s[-1] - t_s[0])``
    (``t_s[0]`` = first finite time). ``t_s`` must be ascending; samples with non-finite time
    are dropped, samples with NaN value are skipped (interpolation bridges them). A grid
    second that falls strictly between two valid samples more than ``max_gap_s`` apart is
    NaN; seconds exactly on a valid sample keep its value. Seconds before the first or after
    the last valid sample are NaN. Duplicate timestamps keep the last sample.
    """
    t = np.asarray(t_s, dtype=np.float64).ravel()
    v = np.asarray(values, dtype=np.float64).ravel()
    if t.shape != v.shape:
        raise ValueError(f"t_s and values must be equally long, got {t.size} and {v.size}")
    has_t = np.isfinite(t)
    t, v = t[has_t], v[has_t]
    if t.size == 0:
        return np.empty(0, dtype=np.float64)
    if np.any(np.diff(t) < 0):
        raise ValueError("t_s must be ascending")

    grid = t[0] + np.arange(math.floor(t[-1] - t[0]) + 1, dtype=np.float64)
    out = np.full(grid.size, np.nan)
    has_v = np.isfinite(v)
    tv, vv = t[has_v], v[has_v]
    if tv.size == 0:
        return out
    last_of_run = np.append(np.diff(tv) > 0, True)  # drop duplicate timestamps (keep last)
    tv, vv = tv[last_of_run], vv[last_of_run]

    j = np.searchsorted(tv, grid, side="right") - 1  # last valid sample at or before grid
    inside = (j >= 0) & (grid <= tv[-1])
    jj = np.clip(j, 0, tv.size - 1)
    nxt = np.minimum(jj + 1, tv.size - 1)
    exact = inside & (tv[jj] == grid)
    bridged = inside & (tv[nxt] - tv[jj] <= max_gap_s)
    use = exact | bridged
    out[use] = np.interp(grid[use], tv, vv)
    return out


def mean_max(
    values_1hz: ArrayLike, durations: Iterable[int] = STANDARD_DURATIONS_S
) -> dict[int, float]:
    """Best mean value over every window of each duration (seconds = samples at 1 Hz).

    Uses cumulative sums, O(n) per duration. Windows containing a NaN sample are excluded;
    durations longer than the series or without any NaN-free window are omitted.
    """
    x = np.asarray(values_1hz, dtype=np.float64).ravel()
    n = x.size
    finite = np.isfinite(x)
    csum = np.concatenate(([0.0], np.cumsum(np.where(finite, x, 0.0))))
    cbad = np.concatenate(([0], np.cumsum(~finite)))
    out: dict[int, float] = {}
    for duration in durations:
        d = int(duration)
        if d < 1:
            raise ValueError(f"durations must be >= 1 s, got {duration}")
        if d > n:
            continue
        clean = (cbad[d:] - cbad[:-d]) == 0
        if not clean.any():
            continue
        sums = (csum[d:] - csum[:-d])[clean]
        out[d] = float(np.max(sums)) / d
    return out


def best_distance_times(
    t_s: ArrayLike,
    distance_m: ArrayLike,
    targets_m: Iterable[float] = STANDARD_DISTANCES_M,
) -> dict[float, float]:
    """Fastest elapsed time (s) to cover each target distance.

    For every sample taken as the end point, the start is the point exactly ``target`` metres
    earlier: its time is linearly interpolated between the two samples around that distance
    (when the athlete stood still there, the latest moment at that distance is used). The
    best effort is the minimum over all end samples (vectorised binary search instead of an
    explicit two-pointer loop). Samples with non-finite time or distance are dropped and the
    distance is made non-decreasing (running maximum). Targets longer than the covered
    distance are omitted; keys are the targets as given (as float).
    """
    t = np.asarray(t_s, dtype=np.float64).ravel()
    d = np.asarray(distance_m, dtype=np.float64).ravel()
    if t.shape != d.shape:
        raise ValueError(f"t_s and distance_m must be equally long, got {t.size} and {d.size}")
    ok = np.isfinite(t) & np.isfinite(d)
    t, d = t[ok], d[ok]
    if t.size < 2:
        return {}
    rel = np.maximum.accumulate(d) - d[0]  # covered distance, starts at exactly 0
    total = float(rel[-1])

    out: dict[float, float] = {}
    for target in targets_m:
        goal = float(target)
        if not goal > 0:
            raise ValueError(f"targets must be > 0 m, got {target}")
        if goal > total:
            continue
        start_pos = rel - goal
        ends = np.nonzero(start_pos >= 0)[0]
        s = start_pos[ends]
        i = np.searchsorted(rel, s, side="right") - 1  # last sample at or before the start
        i1 = np.minimum(i + 1, rel.size - 1)
        span = rel[i1] - rel[i]
        frac = np.divide(s - rel[i], span, out=np.zeros_like(span), where=span > 0)
        t_start = t[i] + frac * (t[i1] - t[i])
        out[goal] = float(np.min(t[ends] - t_start))
    return out
