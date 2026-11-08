"""Physiology metrics: TRIMP, HR zone times, normalized power, IF/TSS, efficiency, decoupling.

Heart rate in bpm, power in W, time in seconds. NaN marks a missing sample.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.typing import ArrayLike

from garminizer.analytics import FloatArray
from garminizer.analytics.series import rolling_mean

# Banister TRIMP weighting y = a * e^(b * HRr).
TRIMP_COEFFICIENTS: dict[str, tuple[float, float]] = {
    "male": (0.64, 1.92),
    "female": (0.86, 1.67),
}
NP_WINDOW_S = 30


def _durations(dt_s: ArrayLike, shape: tuple[int, ...]) -> FloatArray:
    """``dt_s`` as an array of ``shape`` (a scalar is broadcast)."""
    dt = np.asarray(dt_s, dtype=np.float64)
    if dt.ndim == 0:
        return np.full(shape, float(dt), dtype=np.float64)
    if dt.shape != shape:
        raise ValueError(f"dt_s must be a scalar or have shape {shape}, got {dt.shape}")
    return dt


def trimp_banister(
    hr: ArrayLike,
    dt_s: ArrayLike,
    hr_rest: float,
    hr_max: float,
    sex: str = "male",
) -> float:
    """Banister TRIMP: sum of ``dt_min * HRr * a * e^(b * HRr)``.

    ``HRr = clip((hr - hr_rest) / (hr_max - hr_rest), 0, 1)``; (a, b) = (0.64, 1.92) for
    ``sex="male"`` and (0.86, 1.67) for ``"female"``. ``dt_s`` is the duration of each sample
    (scalar or per sample). Samples with NaN heart rate or duration contribute 0.
    """
    try:
        a, b = TRIMP_COEFFICIENTS[sex.lower()]
    except KeyError:
        raise ValueError(f"sex must be 'male' or 'female', got {sex!r}") from None
    if not hr_max > hr_rest:
        raise ValueError("hr_max must be greater than hr_rest")
    h = np.asarray(hr, dtype=np.float64)
    dt = _durations(dt_s, h.shape)
    ok = np.isfinite(h) & np.isfinite(dt)
    hrr = np.clip((h[ok] - hr_rest) / (hr_max - hr_rest), 0.0, 1.0)
    return float(np.sum(dt[ok] / 60.0 * hrr * a * np.exp(b * hrr)))


def hr_zone_seconds(hr: ArrayLike, dt_s: ArrayLike, floors: ArrayLike) -> list[float]:
    """Seconds per heart-rate zone.

    ``floors`` are the strictly ascending lower bounds (bpm) of zones 1..n. The result has
    n + 1 entries: index 0 is the time below the zone-1 floor, index k the time in zone k
    (``floors[k-1] <= hr < floors[k]``); zone n is open-ended. NaN samples are ignored.
    """
    f = np.asarray(floors, dtype=np.float64)
    if f.ndim != 1 or not np.all(np.isfinite(f)) or np.any(np.diff(f) <= 0):
        raise ValueError("floors must be a finite, strictly ascending 1-D sequence")
    h = np.asarray(hr, dtype=np.float64)
    dt = _durations(dt_s, h.shape)
    ok = np.isfinite(h) & np.isfinite(dt)
    zones = np.searchsorted(f, h[ok], side="right")
    seconds = np.bincount(zones, weights=dt[ok], minlength=f.size + 1)
    return [float(s) for s in seconds]


def normalized_power(power_1hz: ArrayLike, window_s: int = NP_WINDOW_S) -> float | None:
    """Normalized power: 30 s rolling mean, then the fourth root of the mean fourth power.

    Rolling windows that contain a NaN sample are dropped (NaN is never treated as 0). Returns
    ``None`` with fewer than ``window_s`` valid samples or when no NaN-free window exists.
    """
    p = np.asarray(power_1hz, dtype=np.float64).ravel()
    if np.count_nonzero(np.isfinite(p)) < window_s:
        return None
    means = rolling_mean(p, window_s)[window_s - 1 :]
    means = means[np.isfinite(means)]
    if means.size == 0:
        return None
    return float(np.mean(means**4) ** 0.25)


def _positive(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0


def intensity_factor(np_w: float | None, ftp_w: float | None) -> float | None:
    """IF = NP / FTP; ``None`` when either is missing, not finite, or FTP <= 0."""
    if np_w is None or ftp_w is None or not math.isfinite(np_w) or not _positive(ftp_w):
        return None
    return float(np_w) / float(ftp_w)


def training_stress_score(
    duration_s: float | None, np_w: float | None, ftp_w: float | None
) -> float | None:
    """TSS = duration_s * NP * IF / (FTP * 3600) * 100 (one hour at FTP = 100)."""
    if duration_s is None or not math.isfinite(duration_s) or duration_s < 0:
        return None
    if np_w is None or ftp_w is None:
        return None
    intensity = intensity_factor(np_w, ftp_w)
    if intensity is None:
        return None
    return float(duration_s) * float(np_w) * intensity / (float(ftp_w) * 3600.0) * 100.0


def _valid_pairs(output: ArrayLike, hr: ArrayLike) -> tuple[FloatArray, FloatArray]:
    o = np.asarray(output, dtype=np.float64).ravel()
    h = np.asarray(hr, dtype=np.float64).ravel()
    if o.shape != h.shape:
        raise ValueError(f"output and hr must be equally long, got {o.size} and {h.size}")
    ok = np.isfinite(o) & np.isfinite(h) & (o > 0) & (h > 0)
    return o[ok], h[ok]


def efficiency_factor(output: ArrayLike, hr: ArrayLike) -> float | None:
    """EF = mean(output) / mean(hr) over samples where both are finite and > 0."""
    o, h = _valid_pairs(output, hr)
    if o.size == 0:
        return None
    return float(np.mean(o) / np.mean(h))


def aerobic_decoupling(output: ArrayLike, hr: ArrayLike, min_samples: int = 1200) -> float | None:
    """Pa:HR decoupling in percent: ``(EF1 - EF2) / EF1 * 100``.

    The valid samples (both finite and > 0) of a 1 Hz series are split by count: the first
    half is the first ``n // 2`` valid samples, the second half the rest (gets the extra
    sample when n is odd). Positive values mean HR drifted up relative to output. ``None``
    with fewer than ``min_samples`` (and at least 2) valid samples.
    """
    o, h = _valid_pairs(output, hr)
    n = o.size
    if n < max(min_samples, 2):
        return None
    half = n // 2
    ef1 = float(np.mean(o[:half]) / np.mean(h[:half]))
    ef2 = float(np.mean(o[half:]) / np.mean(h[half:]))
    return (ef1 - ef2) / ef1 * 100.0
