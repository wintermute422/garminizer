"""Synthetic GPS routes and elevation profiles for demo activities.

Routes are smooth closed curves (random Fourier harmonics) or out-and-back paths in a local
east/north frame around a start point, sampled every few metres. Nothing here is real.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

STEP_M = 5.0  # path resolution
_EARTH_R = 6_371_008.8


@dataclass(frozen=True)
class Route:
    """A path sampled every STEP_M metres: positions, altitude and cumulative distance."""

    lat: FloatArray
    lon: FloatArray
    alt: FloatArray
    dist: FloatArray  # cumulative metres, starts at 0

    @property
    def length_m(self) -> float:
        return float(self.dist[-1])

    def at(self, d: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
        """Interpolate lat/lon/alt at cumulative distances d (wrapping for repeated laps)."""
        dd = np.mod(d, self.length_m) if self.length_m > 0 else d
        return (
            np.interp(dd, self.dist, self.lat),
            np.interp(dd, self.dist, self.lon),
            np.interp(dd, self.dist, self.alt),
        )

    def grade(self) -> FloatArray:
        """Grade (rise/run) per path segment, same length as dist."""
        g = np.gradient(self.alt, self.dist, edge_order=1) if len(self.dist) > 2 else self.alt * 0
        return np.clip(g, -0.35, 0.35)


def _to_latlon(
    east: FloatArray, north: FloatArray, lat0: float, lon0: float
) -> tuple[FloatArray, FloatArray]:
    lat = lat0 + np.degrees(north / _EARTH_R)
    lon = lon0 + np.degrees(east / (_EARTH_R * math.cos(math.radians(lat0))))
    return lat, lon


def _resample(east: FloatArray, north: FloatArray) -> tuple[FloatArray, FloatArray, FloatArray]:
    seg = np.hypot(np.diff(east), np.diff(north))
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    grid = np.arange(0.0, cum[-1], STEP_M)
    grid = np.append(grid, cum[-1])
    return np.interp(grid, cum, east), np.interp(grid, cum, north), grid


def _profile(
    dist: FloatArray, base_alt: float, amplitude: float, rng: np.random.Generator, periodic: bool
) -> FloatArray:
    length = max(float(dist[-1]), 1.0)
    alt = np.full_like(dist, base_alt)
    for k, share in ((1, 0.55), (2, 0.25), (3, 0.12), (7, 0.08)):
        wavelength = length / k if periodic else length / (k * rng.uniform(0.7, 1.3))
        alt += (
            amplitude
            * share
            * np.sin(2 * math.pi * dist / wavelength + rng.uniform(0, 2 * math.pi))
        )
    return alt


def loop_route(
    lat0: float,
    lon0: float,
    length_m: float,
    rng: np.random.Generator,
    *,
    amplitude_m: float = 15.0,
    base_alt_m: float = 520.0,
    wiggle: float = 0.012,
) -> Route:
    """A closed loop of roughly `length_m` that starts and ends at (lat0, lon0)."""
    theta = np.linspace(0.0, 2 * math.pi, 2000)
    r = np.ones_like(theta)
    for k in range(2, 6):
        r += rng.uniform(0.04, 0.22) / k * np.cos(k * theta + rng.uniform(0, 2 * math.pi))
    for k in range(14, 30, 3):
        r += wiggle * np.cos(k * theta + rng.uniform(0, 2 * math.pi))
    east, north = r * np.cos(theta), r * np.sin(theta)
    perimeter = float(np.sum(np.hypot(np.diff(east), np.diff(north))))
    scale = length_m / perimeter
    rot = rng.uniform(0, 2 * math.pi)
    e = (east - east[0]) * scale
    n = (north - north[0]) * scale
    e, n = e * math.cos(rot) - n * math.sin(rot), e * math.sin(rot) + n * math.cos(rot)
    e, n, dist = _resample(e, n)
    e += rng.normal(0, 1.2, len(e))  # GPS jitter
    n += rng.normal(0, 1.2, len(n))
    lat, lon = _to_latlon(e, n, lat0, lon0)
    alt = _profile(dist, base_alt_m, amplitude_m, rng, periodic=True)
    return Route(lat, lon, alt, dist)


def out_and_back_route(
    lat0: float,
    lon0: float,
    length_m: float,
    rng: np.random.Generator,
    *,
    climb_m: float = 0.0,
    amplitude_m: float = 20.0,
    base_alt_m: float = 520.0,
) -> Route:
    """Out along a meandering path and back the same way; optional steady climb to the turn."""
    half = length_m / 2
    n_pts = max(int(half / STEP_M), 10)
    heading = rng.uniform(0, 2 * math.pi) + np.cumsum(rng.normal(0, 0.035, n_pts))
    e = np.concatenate([[0.0], np.cumsum(STEP_M * np.cos(heading))])
    n = np.concatenate([[0.0], np.cumsum(STEP_M * np.sin(heading))])
    out_dist = np.arange(len(e), dtype=np.float64) * STEP_M
    x = out_dist / out_dist[-1]
    out_alt = base_alt_m + climb_m * (3 * x**2 - 2 * x**3)
    out_alt += _profile(out_dist, 0.0, amplitude_m, rng, periodic=False)
    e_all = np.concatenate([e, e[-2::-1]])
    n_all = np.concatenate([n, n[-2::-1]])
    alt_all = np.concatenate([out_alt, out_alt[-2::-1]])
    dist = np.concatenate([out_dist, out_dist[-1] + out_dist[1:]])
    e_all += rng.normal(0, 1.2, len(e_all))
    n_all += rng.normal(0, 1.2, len(n_all))
    lat, lon = _to_latlon(e_all, n_all, lat0, lon0)
    return Route(lat, lon, alt_all, dist)


def track_route(lat0: float, lon0: float, rng: np.random.Generator) -> Route:
    """A 400 m athletics-track oval (for interval sessions)."""
    straight, radius = 84.39, 36.5
    s = np.arange(0.0, 400.0, STEP_M)
    e = np.empty_like(s)
    n = np.empty_like(s)
    half_curve = math.pi * radius
    for i, d in enumerate(s):
        if d < straight:
            e[i], n[i] = d, 0.0
        elif d < straight + half_curve:
            a = (d - straight) / radius
            e[i], n[i] = straight + radius * math.sin(a), radius - radius * math.cos(a)
        elif d < 2 * straight + half_curve:
            e[i], n[i] = straight - (d - straight - half_curve), 2 * radius
        else:
            a = (d - 2 * straight - half_curve) / radius
            e[i], n[i] = -radius * math.sin(a), radius + radius * math.cos(a)
    rot = rng.uniform(0, math.pi)
    e, n = e * math.cos(rot) - n * math.sin(rot), e * math.sin(rot) + n * math.cos(rot)
    lat, lon = _to_latlon(
        e + rng.normal(0, 0.8, len(e)), n + rng.normal(0, 0.8, len(n)), lat0, lon0
    )
    return Route(lat, lon, np.full_like(s, 515.0), s)
