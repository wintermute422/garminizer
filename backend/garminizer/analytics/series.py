"""Series tools: LTTB downsampling, even splits, elevation, rolling mean, trend, correlation.

Conventions: inputs are 1-D array-likes; NaN marks a missing sample. Time is in seconds,
distance in metres.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike

from garminizer.analytics import FloatArray, IndexArray


def _pair(x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
    xa = np.asarray(x, dtype=np.float64)
    ya = np.asarray(y, dtype=np.float64)
    if xa.ndim != 1 or xa.shape != ya.shape:
        raise ValueError(f"x and y must be 1-D and equally long, got {xa.shape} and {ya.shape}")
    return xa, ya


def _finite_pairs(x: ArrayLike, y: ArrayLike) -> tuple[FloatArray, FloatArray]:
    xa, ya = _pair(x, y)
    ok = np.isfinite(xa) & np.isfinite(ya)
    return xa[ok], ya[ok]


# --------------------------------------------------------------------------------------------
# Downsampling
# --------------------------------------------------------------------------------------------


def lttb(x: ArrayLike, y: ArrayLike, threshold: int) -> IndexArray:
    """Largest-Triangle-Three-Buckets: indices of ``threshold`` representative points.

    ``x`` must be finite and ascending. The result is sorted and always contains the first and
    last index; with ``threshold >= len`` or ``threshold < 3`` every index is returned.

    NaN ``y``: bucket averages ignore NaN, and a NaN point is never selected unless its whole
    bucket is NaN (then the bucket's first index is used). If both reference values of a
    triangle are undefined (NaN previous pick and an all-NaN next bucket), 0 stands in for them.
    """
    xa, ya = _pair(x, y)
    n = xa.size
    if threshold >= n or threshold < 3:
        return np.arange(n, dtype=np.intp)

    finite = np.isfinite(ya)
    buckets = threshold - 2
    # Integer bucket edges: bucket i covers [edges[i], edges[i + 1]); the last "bucket" is the
    # final point alone, so the next-bucket average of the last real bucket is that point.
    edges = [1 + (k * (n - 2)) // buckets for k in range(buckets + 1)] + [n]

    selected = np.empty(threshold, dtype=np.intp)
    selected[0] = 0
    a = 0
    for i in range(buckets):
        lo, hi = edges[i], edges[i + 1]
        next_lo, next_hi = edges[i + 1], edges[i + 2]

        next_x = float(np.mean(xa[next_lo:next_hi]))
        next_y_vals = ya[next_lo:next_hi][finite[next_lo:next_hi]]
        next_y = float(np.mean(next_y_vals)) if next_y_vals.size else math.nan

        candidates = np.arange(lo, hi)[finite[lo:hi]]
        if candidates.size == 0:
            a = lo
        else:
            ax = float(xa[a])
            ay = float(ya[a]) if finite[a] else next_y
            if not math.isfinite(next_y):
                next_y = ay
            if not math.isfinite(ay):
                ay = next_y = 0.0
            area = np.abs(
                (ax - next_x) * (ya[candidates] - ay) - (ax - xa[candidates]) * (next_y - ay)
            )
            a = int(candidates[int(np.argmax(area))])
        selected[i + 1] = a
    selected[-1] = n - 1
    return selected


# --------------------------------------------------------------------------------------------
# Elevation and splits
# --------------------------------------------------------------------------------------------


def elevation_gain_loss(altitude: ArrayLike, threshold_m: float = 2.0) -> tuple[float, float]:
    """Total (gain, loss) in metres with hysteresis.

    A climb (descent) is only counted once the altitude has moved more than ``threshold_m``
    away from the last turning point; it is then counted in full, from that turning point to
    the next one. Wiggles within the threshold are ignored. NaN samples are skipped.
    """
    if threshold_m < 0:
        raise ValueError("threshold_m must be >= 0")
    alt = np.asarray(altitude, dtype=np.float64).ravel()
    values: list[float] = alt[np.isfinite(alt)].tolist()
    direction, anchor, extreme, start = _first_move(values, threshold_m)
    if direction == 0:
        return 0.0, 0.0

    totals = {1: 0.0, -1: 0.0}  # +1 = climbing (gain), -1 = descending (loss)
    for v in values[start:]:
        if (v - extreme) * direction > 0:
            extreme = v  # still moving the same way: extend the current leg
        elif (extreme - v) * direction > threshold_m:
            totals[direction] += (extreme - anchor) * direction  # turning point confirmed
            direction, anchor, extreme = -direction, extreme, v
    totals[direction] += (extreme - anchor) * direction
    return float(totals[1]), float(totals[-1])


def _first_move(values: list[float], threshold_m: float) -> tuple[int, float, float, int]:
    """First leg that exceeds the threshold: (direction, turning point, extreme, next index)."""
    if not values:
        return 0, 0.0, 0.0, 0
    hi = lo = values[0]
    for i, v in enumerate(values[1:], start=1):
        hi = max(hi, v)
        lo = min(lo, v)
        if v - lo > threshold_m:
            return 1, lo, v, i + 1
        if hi - v > threshold_m:
            return -1, hi, v, i + 1
    return 0, values[0], values[0], len(values)


@dataclass(frozen=True)
class Split:
    """One even split. ``index`` is the 1-based split number (1 = first split)."""

    index: int
    distance_m: float
    duration_s: float
    averages: dict[str, float | None]
    elevation_gain_m: float | None
    elevation_loss_m: float | None


def _aligned(values: ArrayLike, n: int, name: str) -> FloatArray:
    arr = np.asarray(values, dtype=np.float64)
    if arr.shape != (n,):
        raise ValueError(f"{name} must have {n} samples, got shape {arr.shape}")
    return arr


def even_splits(
    t_s: ArrayLike,
    distance_m: ArrayLike,
    split_m: float = 1000.0,
    extras: Mapping[str, ArrayLike] | None = None,
    altitude: ArrayLike | None = None,
    *,
    elevation_threshold_m: float = 2.0,
    min_partial_fraction: float = 0.1,
) -> list[Split]:
    """Cut an activity into splits at every multiple of ``split_m`` of cumulative distance.

    - Boundaries are the absolute multiples ``k * split_m`` that lie after the first sample's
      distance; the crossing time is linearly interpolated between the two samples around it.
      The first split runs from the first sample to the first boundary.
    - Samples with non-finite time or distance are dropped; distance is made non-decreasing
      (running maximum) to absorb small GPS/odometer regressions.
    - ``averages[name]`` is the time-weighted mean of ``extras[name]`` within the split. Each
      sample's value holds until the next sample (sample-and-hold); NaN samples carry no
      weight; ``None`` when no valid value overlaps the split.
    - Elevation uses :func:`elevation_gain_loss` on the samples inside the split plus the
      altitude interpolated at both split edges (``None`` without any finite altitude).
    - The final partial split is included when it covers at least ``min_partial_fraction``
      of ``split_m``.
    """
    if not split_m > 0:
        raise ValueError("split_m must be > 0")
    t_all, d_all = _pair(t_s, distance_m)
    n_all = t_all.size
    keep = np.isfinite(t_all) & np.isfinite(d_all)
    series = {name: _aligned(values, n_all, name)[keep] for name, values in (extras or {}).items()}
    alt = None if altitude is None else _aligned(altitude, n_all, "altitude")[keep]
    t = t_all[keep]
    d = np.maximum.accumulate(d_all[keep])
    if t.size < 2:
        return []
    alt_ok = np.isfinite(alt) if alt is not None else np.zeros(t.size, dtype=bool)
    t_alt = t[alt_ok]
    a_alt = alt[alt_ok] if alt is not None else t_alt

    first_k = math.floor(d[0] / split_m) + 1
    last_k = math.floor(d[-1] / split_m)
    boundaries = split_m * np.arange(first_k, last_k + 1, dtype=np.float64)
    boundaries = boundaries[boundaries > d[0]]
    j = np.maximum(np.searchsorted(d, boundaries, side="left"), 1)
    span = d[j] - d[j - 1]
    frac = np.divide(boundaries - d[j - 1], span, out=np.zeros_like(span), where=span > 0)
    t_cross = t[j - 1] + frac * (t[j] - t[j - 1])

    edge_t = [float(t[0]), *t_cross.tolist()]
    edge_d = [float(d[0]), *boundaries.tolist()]
    if float(d[-1]) - edge_d[-1] >= min_partial_fraction * split_m:
        edge_t.append(float(t[-1]))
        edge_d.append(float(d[-1]))

    hold_start, hold_end = t[:-1], t[1:]
    splits: list[Split] = []
    for k in range(len(edge_t) - 1):
        ta, tb = edge_t[k], edge_t[k + 1]
        overlap = np.clip(np.minimum(hold_end, tb) - np.maximum(hold_start, ta), 0.0, None)
        averages: dict[str, float | None] = {}
        for name, values in series.items():
            held = values[:-1]
            ok = np.isfinite(held) & (overlap > 0)
            weight = float(np.sum(overlap[ok]))
            averages[name] = float(np.sum(overlap[ok] * held[ok]) / weight) if weight > 0 else None

        gain: float | None = None
        loss: float | None = None
        if t_alt.size:
            inner = (t_alt > ta) & (t_alt < tb)
            seq = np.concatenate(
                ([np.interp(ta, t_alt, a_alt)], a_alt[inner], [np.interp(tb, t_alt, a_alt)])
            )
            gain, loss = elevation_gain_loss(seq, elevation_threshold_m)

        splits.append(
            Split(
                index=k + 1,
                distance_m=edge_d[k + 1] - edge_d[k],
                duration_s=tb - ta,
                averages=averages,
                elevation_gain_m=gain,
                elevation_loss_m=loss,
            )
        )
    return splits


# --------------------------------------------------------------------------------------------
# Rolling, trend and correlation
# --------------------------------------------------------------------------------------------


def rolling_mean(values: ArrayLike, window: int, min_periods: int | None = None) -> FloatArray:
    """Trailing mean over the last ``window`` samples (inclusive), ignoring NaN.

    Position ``t`` averages the finite values among ``values[t - window + 1 : t + 1]`` (fewer
    at the start). It is NaN when fewer than ``min_periods`` finite values are in the window;
    ``min_periods`` defaults to ``window``.
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    need = window if min_periods is None else min_periods
    if not 1 <= need <= window:
        raise ValueError("min_periods must be between 1 and window")
    x = np.asarray(values, dtype=np.float64).ravel()
    finite = np.isfinite(x)
    csum = np.concatenate(([0.0], np.cumsum(np.where(finite, x, 0.0))))
    count = np.concatenate(([0], np.cumsum(finite)))
    end = np.arange(1, x.size + 1)
    start = np.maximum(end - window, 0)
    sums = csum[end] - csum[start]
    counts = count[end] - count[start]
    out = np.full(x.size, np.nan)
    ok = counts >= need
    out[ok] = sums[ok] / counts[ok]
    return out


def linear_trend(x: ArrayLike, y: ArrayLike) -> tuple[float, float, float]:
    """Least-squares line ``y = slope * x + intercept`` and its r².

    NaN pairs are dropped. Raises ``ValueError`` with fewer than 2 points or constant ``x``.
    r² is NaN when ``y`` is constant (the fit is exact but r² is undefined).
    """
    xa, ya = _finite_pairs(x, y)
    if xa.size < 2:
        raise ValueError("linear_trend needs at least 2 finite (x, y) pairs")
    dx = xa - xa.mean()
    dy = ya - ya.mean()
    sxx = float(np.dot(dx, dx))
    if sxx == 0:
        raise ValueError("linear_trend needs at least 2 distinct x values")
    sxy = float(np.dot(dx, dy))
    syy = float(np.dot(dy, dy))
    slope = sxy / sxx
    intercept = float(ya.mean()) - slope * float(xa.mean())
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else math.nan
    return slope, intercept, min(r2, 1.0) if math.isfinite(r2) else r2


def pearson(x: ArrayLike, y: ArrayLike) -> tuple[float, int]:
    """Pearson r and the number of pairs used (NaN pairs dropped).

    r is NaN with fewer than 3 pairs or when either side has zero variance.
    """
    xa, ya = _finite_pairs(x, y)
    n = int(xa.size)
    if n < 3:
        return math.nan, n
    dx = xa - xa.mean()
    dy = ya - ya.mean()
    sxx = float(np.dot(dx, dx))
    syy = float(np.dot(dy, dy))
    if sxx == 0 or syy == 0:
        return math.nan, n
    r = float(np.dot(dx, dy)) / math.sqrt(sxx * syy)
    return max(-1.0, min(1.0, r)), n


def lagged_correlation(x: ArrayLike, y: ArrayLike, max_lag: int) -> list[tuple[int, float, int]]:
    """``(lag, r, n)`` for lag k = 0..max_lag, correlating ``x[t]`` with ``y[t + k]``."""
    if max_lag < 0:
        raise ValueError("max_lag must be >= 0")
    xa, ya = _pair(x, y)
    n = xa.size
    out: list[tuple[int, float, int]] = []
    for k in range(max_lag + 1):
        if k >= n:
            out.append((k, math.nan, 0))
            continue
        r, used = pearson(xa[: n - k], ya[k:])
        out.append((k, r, used))
    return out
