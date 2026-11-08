"""Per-second activity streams for demo workouts (1 Hz, like a watch's FIT records).

Models: target effort per workout segment; running pace adjusted for grade; cycling speed from
power via a simple physics model; heart rate follows effort with lag, drift, heat and fatigue.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import numpy.typing as npt

from garminizer.demo.calendar import Workout
from garminizer.demo.routes import Route, loop_route, out_and_back_route, track_route

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True)
class AthleteState:
    vo2max: float
    hr_rest: float
    hr_max: float
    weight_kg: float
    ftp_w: float
    fatigue: float  # acute - chronic load (positive = tired)
    temperature_c: float
    age: float


@dataclass(frozen=True)
class Places:
    home: tuple[float, float]
    track: tuple[float, float]
    trailhead: tuple[float, float]
    mountains: tuple[float, float]
    race_venue: tuple[float, float]


@dataclass
class Synth:
    """A synthesized activity: 1 Hz streams (NaN = not recorded) plus laps."""

    workout: Workout
    start_utc: datetime
    speed: FloatArray
    dist: FloatArray
    hr: FloatArray
    lat: FloatArray
    lon: FloatArray
    alt: FloatArray
    cadence: FloatArray
    power: FloatArray
    temp: FloatArray
    resp: FloatArray
    vo: FloatArray
    gct: FloatArray
    stride: FloatArray
    effort: FloatArray  # target intensity (fraction of threshold), used for summaries
    lap_marks: list[tuple[int, str]] = field(default_factory=list)  # (start second, intensity)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def n(self) -> int:
        return len(self.hr)


def threshold_speed(vo2max: float) -> float:
    """Running speed (m/s) at ~88 % VO2max, from Daniels' oxygen-cost equation."""
    target = 0.88 * vo2max
    a, b, c = 0.000104, 0.182258, -4.60 - target
    v_m_min = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
    return v_m_min / 60.0


def _nan(n: int) -> FloatArray:
    return np.full(n, np.nan, dtype=np.float64)


def _cumdist(speed: FloatArray) -> FloatArray:
    """Odometer per sample: 0 at the first record, like a FIT file."""
    out = np.zeros(len(speed), dtype=np.float64)
    out[1:] = np.cumsum(speed[:-1])
    return out


def _schedule(segments: list[tuple[float, float]], smooth_s: int = 12) -> FloatArray:
    """Expand (seconds, intensity) segments into a 1 Hz effort series with soft transitions."""
    parts = [np.full(max(int(s), 1), r, dtype=np.float64) for s, r in segments]
    effort = np.concatenate(parts)
    if smooth_s > 1 and len(effort) > smooth_s:
        kernel = np.ones(smooth_s) / smooth_s
        effort = np.convolve(np.pad(effort, (smooth_s, smooth_s), mode="edge"), kernel, "same")[
            smooth_s:-smooth_s
        ]
    return effort


def _ar_noise(n: int, sigma: float, rho: float, rng: np.random.Generator) -> FloatArray:
    """AR(1) noise via a recursive filter written as cumulative sums of decayed shocks."""
    shocks = rng.normal(0.0, sigma * math.sqrt(1 - rho * rho), n)
    out = np.empty(n, dtype=np.float64)
    acc = 0.0
    for i in range(n):
        acc = rho * acc + shocks[i]
        out[i] = acc
    return out


def _heart_rate(
    effort_frac: FloatArray, st: AthleteState, rng: np.random.Generator, hr_start: float
) -> FloatArray:
    """HR follows a target (fraction of HR reserve) with first-order lag, drift and noise."""
    n = len(effort_frac)
    hours = np.arange(n, dtype=np.float64) / 3600.0
    heat = max(st.temperature_c - 15.0, 0.0) * 0.004
    drift = 0.022 * np.sqrt(hours) * (1.0 + 4 * heat)
    frac = np.clip(effort_frac + st.fatigue / 250.0 + heat + drift, 0.25, 1.0)
    target = st.hr_rest + (st.hr_max - st.hr_rest) * frac
    hr = np.empty(n, dtype=np.float64)
    cur = hr_start
    up, down = 1 - math.exp(-1 / 22.0), 1 - math.exp(-1 / 40.0)
    tgt = target.tolist()
    for i in range(n):
        cur += (tgt[i] - cur) * (up if tgt[i] > cur else down)
        hr[i] = cur
    hr += _ar_noise(n, 1.4, 0.8, rng)
    return np.round(np.clip(hr, 40, st.hr_max + 2))


def _grade_at(route: Route, d: FloatArray) -> FloatArray:
    g = route.grade()
    dd = np.mod(d, route.length_m) if route.length_m > 0 else d
    return np.interp(dd, route.dist, g)


def _run_speed_factor(g: FloatArray) -> FloatArray:
    down = np.clip(-g, 0, None)
    f = np.where(
        g > 0, 1 - 3.3 * g, 1 + 1.5 * np.minimum(down, 0.08) - 2.5 * np.maximum(down - 0.08, 0)
    )
    return np.clip(f, 0.3, 1.25)


def _laps_by_distance(dist: FloatArray, every_m: float) -> list[tuple[int, str]]:
    marks = [(0, "active")]
    k = 1
    for i in range(1, len(dist)):
        if dist[i] >= k * every_m:
            marks.append((i, "active"))
            k += 1
    return marks


def _laps_by_segments(
    segments: list[tuple[float, float]], rest_below: float
) -> list[tuple[int, str]]:
    marks, t = [], 0
    for i, (s, r) in enumerate(segments):
        kind = "warmup" if i == 0 else ("cooldown" if i == len(segments) - 1 else "active")
        if 0 < i < len(segments) - 1 and r < rest_below:
            kind = "rest"
        marks.append((t, kind))
        t += max(int(s), 1)
    return marks


def _add_stops(speed: FloatArray, effort: FloatArray, count: int, rng: np.random.Generator) -> None:
    n = len(speed)
    for _ in range(count):
        if n < 900:
            return
        s = int(rng.integers(300, n - 300))
        length = int(rng.integers(8, 40))
        speed[s : s + length] = 0.0
        effort[s : s + length] = np.minimum(effort[s : s + length], 0.35)


def _positions(route: Route, dist: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    return route.at(dist)


# --------------------------------------------------------------------------- running-type


Segments = list[tuple[float, float]]


def _repeats(work: tuple[float, float], rest: tuple[float, float], reps: int) -> Segments:
    out: Segments = []
    for _ in range(reps):
        out += [work, rest]
    return out[:-1]


def _seg_intervals(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    reps = int(rng.integers(5, 9))
    rep_s = 800 / (1.08 * v_thr)
    cool = max(total - 900 - reps * (rep_s + 120), 300)
    return [(900.0, 0.74), *_repeats((rep_s, 1.08), (120.0, 0.55), reps), (cool, 0.70)]


def _seg_hills(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    reps = int(rng.integers(6, 10))
    cool = max(total - 900 - reps * 240, 300)
    return [(900.0, 0.74), *_repeats((90.0, 1.12), (150.0, 0.55), reps), (cool, 0.70)]


def _seg_tempo(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    return [(900.0, 0.75), (max(total - 1500, 900), 0.97), (600.0, 0.72)]


def _seg_long(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    return [(total / 3, 0.72), (total / 3, 0.75), (total / 3, 0.79)]


def _seg_recovery(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    return [(total, 0.68)]


def _seg_steady(total: float, v_thr: float, rng: np.random.Generator) -> Segments:
    return [(total, 0.75 + float(rng.normal(0, 0.015)))]


_RUN_SEGMENTS = {
    "intervals": _seg_intervals,
    "hills": _seg_hills,
    "tempo": _seg_tempo,
    "long": _seg_long,
    "recovery": _seg_recovery,
}


def _run_segments(w: Workout, v_thr: float, rng: np.random.Generator) -> Segments:
    if w.kind == "race":
        dist = w.race_distance_m or 10_000.0
        r = 1.03 if dist <= 10_000 else (0.955 if dist <= 21_100 else 0.89)
        duration = dist / (r * v_thr) * 1.06
        return [(duration * 0.75, r), (duration * 0.25, r * (0.96 if dist > 30_000 else 1.0))]
    return _RUN_SEGMENTS.get(w.kind, _seg_steady)(w.duration_min * 60, v_thr, rng)


def run_like(
    w: Workout, start: datetime, st: AthleteState, places: Places, rng: np.random.Generator
) -> Synth:
    v_thr = threshold_speed(st.vo2max)
    if w.kind == "xc_ski":
        v_thr *= 1.12
    segments = _run_segments(w, v_thr, rng)
    effort = _schedule(segments)
    n = len(effort)
    trail = w.kind in {"trail", "hills"}

    est_len = float(np.sum(effort) * v_thr)
    if w.kind == "intervals":
        route = track_route(*places.track, rng)
    elif w.kind == "race":
        route = loop_route(*places.race_venue, w.race_distance_m or est_len, rng, amplitude_m=8.0)
    elif trail:
        route = out_and_back_route(
            *places.trailhead, est_len, rng, climb_m=float(rng.uniform(120, 260)), amplitude_m=35
        )
    elif w.kind == "xc_ski":
        route = loop_route(*places.mountains, est_len, rng, amplitude_m=25.0, base_alt_m=900.0)
    else:
        route = loop_route(*places.home, est_len, rng, amplitude_m=float(rng.uniform(6, 22)))

    v_flat = effort * v_thr * (1 + _ar_noise(n, 0.025, 0.97, rng))
    speed = v_flat.copy()
    for _ in range(2):  # pace depends on grade, grade depends on position
        dist = _cumdist(speed)
        g = _grade_at(route, dist)
        speed = v_flat * _run_speed_factor(g) * (0.92 if trail else 1.0)
    if w.kind in {"easy", "long", "recovery", "tempo"}:
        _add_stops(speed, effort, int(rng.integers(0, 4)), rng)
    dist = _cumdist(speed)
    if w.kind == "race" and w.race_distance_m:
        end = int(np.searchsorted(dist, w.race_distance_m)) + 1
        effort, speed, dist = effort[:end], speed[:end], dist[:end]
        n = len(effort)
    g = _grade_at(route, dist)
    lat, lon, alt = _positions(route, dist)
    hr_frac = 0.09 + 0.75 * effort + 0.6 * np.clip(g, 0, None) * (effort > 0.4)
    hr = _heart_rate(hr_frac, st, rng, st.hr_rest + 25)

    moving = speed > 0.3
    cadence = np.where(moving, 150 + 7.5 * speed + rng.normal(0, 1.5, n), 0.0)
    if w.kind == "xc_ski":
        cadence = _nan(n)
    power = np.where(moving, st.weight_kg * speed * (1.2 + 4.0 * np.clip(g, -0.1, 0.3)), 0.0)
    power = np.clip(power + rng.normal(0, 6, n), 0, None)
    temp = st.temperature_c + 6 + 2 * (1 - np.exp(-np.arange(n) / 600)) + rng.normal(0, 0.3, n)
    resp = 16 + 30 * np.clip(hr_frac, 0, 1) ** 2 + rng.normal(0, 1.2, n)
    vo = np.where(moving, 9.6 - 0.45 * (speed - 3) + rng.normal(0, 0.25, n), np.nan)
    gct = np.where(moving, 270 - 28 * (speed - 3) + rng.normal(0, 6, n), np.nan)
    stride = np.where(cadence > 0, speed * 60 / np.where(cadence > 0, cadence, 1), np.nan)
    if w.kind == "xc_ski":
        vo, gct, stride, power = _nan(n), _nan(n), _nan(n), _nan(n)

    laps = (
        _laps_by_segments(segments, rest_below=0.6)
        if w.kind in {"intervals", "hills"}
        else _laps_by_distance(dist, 1000.0)
    )
    return Synth(
        w,
        start,
        speed,
        dist,
        hr,
        lat,
        lon,
        alt,
        cadence,
        power,
        temp,
        resp,
        vo,
        gct,
        stride,
        effort,
        laps,
    )


# --------------------------------------------------------------------------- cycling


def _bike_speed(
    power: FloatArray, grade: FloatArray, mass: float, crr: float, cda: float
) -> FloatArray:
    """Solve P = 0.5·rho·CdA·v³ + (Crr + grade)·m·g·v for v (vectorized bisection)."""
    a = 0.5 * 1.2 * cda
    b = (crr + grade) * mass * 9.81
    lo = np.full_like(power, 0.3)
    hi = np.full_like(power, 25.0)
    for _ in range(32):
        mid = (lo + hi) / 2
        f = a * mid**3 + b * mid - power
        hi = np.where(f > 0, mid, hi)
        lo = np.where(f > 0, lo, mid)
    v = (lo + hi) / 2
    kernel = np.ones(6) / 6  # inertia
    return np.asarray(
        np.convolve(np.pad(v, (3, 2), mode="edge"), kernel, "valid"), dtype=np.float64
    )


def ride_like(
    w: Workout, start: datetime, st: AthleteState, places: Places, rng: np.random.Generator
) -> Synth:
    total = w.duration_min * 60
    indoor = w.kind == "indoor_ride"
    if indoor:
        reps = 5
        main = []
        for _ in range(reps):
            main += [(300.0, 1.05), (180.0, 0.55)]
        segments = [(600.0, 0.6), *main[:-1], (max(total - 600 - reps * 480, 300), 0.55)]
    elif w.kind == "gravel":
        segments = [(total, 0.66)]
    else:
        segments = [(total * 0.5, 0.66), (total * 0.5, 0.70)]
    effort = _schedule(segments, smooth_s=20)
    n = len(effort)
    p_target = effort * st.ftp_w * (1 + _ar_noise(n, 0.07, 0.9, rng))
    mass = st.weight_kg + (10.5 if w.kind == "gravel" else 8.5)
    crr = 0.012 if w.kind == "gravel" else 0.0055
    cda = 0.42 if w.kind == "gravel" else 0.36

    if indoor:
        g = np.zeros(n)
        power = np.clip(p_target, 0, None)
        speed = _bike_speed(power, g, mass, crr, cda)
        dist = _cumdist(speed)
        lat = lon = alt = _nan(n)
    else:
        est_len = float(np.mean(_bike_speed(p_target, np.zeros(n), mass, crr, cda)) * n)
        route = loop_route(
            *places.home, est_len, rng, amplitude_m=float(rng.uniform(40, 140)), wiggle=0.006
        )
        speed = _bike_speed(np.clip(p_target, 1, None), np.zeros(n), mass, crr, cda)
        power = p_target
        for _ in range(2):
            dist = _cumdist(speed)
            g = _grade_at(route, dist)
            coast = g < -0.03
            power = np.where(coast, p_target * 0.12, p_target * (1 + 1.5 * np.clip(g, 0, 0.1)))
            power = np.clip(power, 0, None)
            speed = _bike_speed(np.maximum(power, 1.0), g, mass, crr, cda)
        dist = _cumdist(speed)
        lat, lon, alt = _positions(route, dist)
    hr_frac = 0.14 + 0.72 * effort
    hr = _heart_rate(hr_frac, st, rng, st.hr_rest + 20)
    cadence = np.where(power > 25, 88 + rng.normal(0, 4, n), 0.0)
    temp = (
        np.full(n, 21.0) + rng.normal(0, 0.2, n)
        if indoor
        else st.temperature_c + 3 + rng.normal(0, 0.4, n)
    )
    resp = 15 + 28 * np.clip(hr_frac, 0, 1) ** 2 + rng.normal(0, 1.2, n)
    laps = _laps_by_segments(segments, 0.6) if indoor else _laps_by_distance(dist, 5000.0)
    nan = _nan(n)
    return Synth(
        w,
        start,
        speed,
        dist,
        hr,
        lat,
        lon,
        alt,
        cadence,
        power,
        temp,
        resp,
        nan,
        nan,
        nan,
        effort,
        laps,
    )


# --------------------------------------------------------------------------- walking / hiking


def _tobler(g: FloatArray) -> FloatArray:
    return 6.0 * np.exp(-3.5 * np.abs(g + 0.05)) / 3.6


def foot_like(
    w: Workout, start: datetime, st: AthleteState, places: Places, rng: np.random.Generator
) -> Synth:
    total = int(w.duration_min * 60)
    hike = w.kind == "hike"
    pace = float(rng.uniform(0.82, 0.92)) if hike else float(rng.uniform(0.95, 1.12))
    est_len = total * 1.25 * pace
    if hike:
        route = out_and_back_route(
            *places.mountains,
            est_len,
            rng,
            climb_m=float(rng.uniform(450, 1050)),
            amplitude_m=40.0,
            base_alt_m=850.0,
        )
    else:
        route = loop_route(*places.home, est_len, rng, amplitude_m=5.0)
    speed = np.full(total, 1.2 * pace)
    for _ in range(2):
        dist = _cumdist(speed)
        g = _grade_at(route, dist)
        speed = _tobler(g) * pace * (1 + _ar_noise(total, 0.03, 0.95, rng))
    if hike:  # summit break around the turnaround
        mid = int(np.searchsorted(np.cumsum(speed), route.length_m / 2))
        brk = int(rng.uniform(300, 900))
        speed[mid : mid + brk] = 0.0
    dist = _cumdist(speed)
    dist = np.minimum(dist, route.length_m)
    g = _grade_at(route, dist)
    lat, lon, alt = _positions(route, dist)
    moving = speed > 0.2
    effort = np.where(moving, 0.42 + 2.2 * np.clip(g, 0, 0.4), 0.3)
    hr_frac = np.clip(0.12 + 0.55 * effort, 0.15, 0.85)
    hr = _heart_rate(hr_frac, st, rng, st.hr_rest + 15)
    cadence = np.where(moving, 102 + 9 * speed + rng.normal(0, 2, total), 0.0)
    temp = st.temperature_c + 5 + rng.normal(0, 0.4, total)
    resp = 15 + 18 * hr_frac**2 + rng.normal(0, 1.0, total)
    nan = _nan(total)
    power = nan
    return Synth(
        w,
        start,
        speed,
        dist,
        hr,
        lat,
        lon,
        alt,
        cadence,
        power,
        temp,
        resp,
        nan,
        nan,
        nan,
        effort,
        _laps_by_distance(dist, 1000.0),
    )


# --------------------------------------------------------------------------- pool / gym


def swim(w: Workout, start: datetime, st: AthleteState, rng: np.random.Generator) -> Synth:
    v_css = 1.05 + 0.012 * (st.vo2max - 50)
    work = w.duration_min * 60 - 400 / (0.85 * v_css)
    reps = max(int(work // (100 / v_css + 20)), 4)
    segments: list[tuple[float, float]] = [(200 / (0.85 * v_css), 0.85)]
    for _ in range(reps):
        segments += [(100 / v_css, 1.0), (20.0, 0.0)]
    segments += [(200 / (0.85 * v_css), 0.85)]
    effort = _schedule(segments, smooth_s=1)
    n = len(effort)
    speed = effort * v_css * (1 + rng.normal(0, 0.02, n))
    dist = _cumdist(speed)
    hr = _heart_rate(np.where(effort > 0, 0.42 + 0.26 * effort, 0.38), st, rng, st.hr_rest + 20)
    hr[rng.random(n) < 0.04] = np.nan  # optical HR drops out in water
    lengths = int(dist[-1] // 25)
    nan = _nan(n)
    synth = Synth(
        w,
        start,
        speed,
        dist,
        hr,
        nan,
        nan,
        nan,
        nan,
        nan,
        np.full(n, 27.0),
        nan,
        nan,
        nan,
        nan,
        effort,
        _laps_by_segments(segments, 0.5),
    )
    strokes_per_length = float(rng.uniform(15, 19))
    synth.extra = {
        "pool_length_m": 25.0,
        "active_lengths": lengths,
        "strokes": round(strokes_per_length * lengths),
        "avg_swolf": round(strokes_per_length + 25 / v_css, 1),
    }
    return synth


def strength(w: Workout, start: datetime, st: AthleteState, rng: np.random.Generator) -> Synth:
    sets = int(rng.integers(12, 19))
    segments: list[tuple[float, float]] = [(300.0, 0.3)]
    reps_total = 0
    for _ in range(sets):
        segments += [(float(rng.uniform(35, 55)), 0.75), (float(rng.uniform(60, 120)), 0.3)]
        reps_total += int(rng.integers(8, 13))
    effort = _schedule(segments, smooth_s=5)
    n = len(effort)
    hr = _heart_rate(0.28 + 0.42 * effort, st, rng, st.hr_rest + 15)
    nan = _nan(n)
    zeros = np.zeros(n)
    synth = Synth(
        w,
        start,
        zeros,
        zeros,
        hr,
        nan,
        nan,
        nan,
        nan,
        nan,
        np.full(n, 23.0),
        nan,
        nan,
        nan,
        nan,
        effort,
        [(0, "active")],
    )
    synth.extra = {"total_sets": sets, "total_reps": reps_total}
    return synth


def synthesize(
    w: Workout, start: datetime, st: AthleteState, places: Places, rng: np.random.Generator
) -> Synth:
    if w.kind in {"endurance_ride", "gravel", "indoor_ride"}:
        return ride_like(w, start, st, places, rng)
    if w.kind in {"hike", "walk"}:
        return foot_like(w, start, st, places, rng)
    if w.kind == "swim":
        return swim(w, start, st, rng)
    if w.kind == "strength":
        return strength(w, start, st, rng)
    return run_like(w, start, st, places, rng)


def sample_times(synth: Synth) -> list[datetime]:
    return [synth.start_utc + timedelta(seconds=i) for i in range(synth.n)]
