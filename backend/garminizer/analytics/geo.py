"""Geo tools: great-circle distance, slippy-map tiles, explorer squares/clusters, simplification.

Coordinates are WGS84 degrees. Tiles are standard Web-Mercator slippy-map tiles ``(x, y)``
with ``y`` growing southwards.
"""

from __future__ import annotations

import math
from collections import deque
from collections.abc import Iterable

import numpy as np
from numpy.typing import ArrayLike

from garminizer.analytics import FloatArray, IndexArray

EARTH_RADIUS_M = 6_371_008.8
MAX_MERCATOR_LAT = 85.05112877980659

Tile = tuple[int, int]


def haversine_m(lat1: ArrayLike, lon1: ArrayLike, lat2: ArrayLike, lon2: ArrayLike) -> FloatArray:
    """Great-circle distance in metres (vectorised; scalar inputs give a 0-d array)."""
    p1 = np.radians(np.asarray(lat1, dtype=np.float64))
    p2 = np.radians(np.asarray(lat2, dtype=np.float64))
    dlat = p2 - p1
    dlon = np.radians(np.asarray(lon2, dtype=np.float64) - np.asarray(lon1, dtype=np.float64))
    h = np.sin(dlat / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    return np.asarray(2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0))))


def _tile_fraction(lat: FloatArray, lon: FloatArray, zoom: int) -> tuple[FloatArray, FloatArray]:
    """Fractional tile coordinates (Web Mercator, so straight segments stay straight)."""
    n = float(1 << zoom)
    lat_r = np.radians(np.clip(lat, -MAX_MERCATOR_LAT, MAX_MERCATOR_LAT))
    fx = (lon + 180.0) / 360.0 * n
    fy = (1.0 - np.arcsinh(np.tan(lat_r)) / math.pi) / 2.0 * n
    return np.asarray(fx, dtype=np.float64), np.asarray(fy, dtype=np.float64)


def tile_xy(lat: float, lon: float, zoom: int) -> Tile:
    """Slippy-map tile containing the point (clamped to the valid tile range)."""
    if zoom < 0:
        raise ValueError("zoom must be >= 0")
    fx, fy = _tile_fraction(
        np.asarray(lat, dtype=np.float64), np.asarray(lon, dtype=np.float64), zoom
    )
    last = (1 << zoom) - 1
    return (
        min(max(math.floor(float(fx)), 0), last),
        min(max(math.floor(float(fy)), 0), last),
    )


def tiles_for_track(
    lat: ArrayLike, lon: ArrayLike, zoom: int = 14, *, max_step_tiles: float = 0.25
) -> set[Tile]:
    """All tiles visited by a track, including tiles crossed between consecutive points.

    Each segment is densified in tile space so that no step exceeds ``max_step_tiles``.
    Points with NaN coordinates are skipped and never connected across: a NaN breaks the
    track. Segments jumping more than half the world in longitude (antimeridian wrap) are
    not densified.
    """
    if zoom < 0:
        raise ValueError("zoom must be >= 0")
    if not max_step_tiles > 0:
        raise ValueError("max_step_tiles must be > 0")
    la = np.asarray(lat, dtype=np.float64).ravel()
    lo = np.asarray(lon, dtype=np.float64).ravel()
    if la.shape != lo.shape:
        raise ValueError(f"lat and lon must be equally long, got {la.size} and {lo.size}")
    n = 1 << zoom
    fx, fy = _tile_fraction(la, lo, zoom)
    valid = np.isfinite(fx) & np.isfinite(fy)
    if not valid.any():
        return set()

    seg = valid[:-1] & valid[1:]
    x0, y0 = fx[:-1][seg], fy[:-1][seg]
    dx, dy = fx[1:][seg] - x0, fy[1:][seg] - y0
    keep = np.abs(dx) <= n / 2
    x0, y0, dx, dy = x0[keep], y0[keep], dx[keep], dy[keep]
    steps = np.maximum(np.ceil(np.maximum(np.abs(dx), np.abs(dy)) / max_step_tiles), 1)
    steps_i = steps.astype(np.intp)
    seg_id = np.repeat(np.arange(steps_i.size), steps_i)
    first = np.repeat(np.cumsum(steps_i) - steps_i, steps_i)
    frac = (np.arange(seg_id.size) - first) / steps[seg_id]
    px = x0[seg_id] + frac * dx[seg_id]
    py = y0[seg_id] + frac * dy[seg_id]

    all_x = np.concatenate((fx[valid], px))
    all_y = np.concatenate((fy[valid], py))
    tx = np.clip(np.floor(all_x), 0, n - 1).astype(np.int64)
    ty = np.clip(np.floor(all_y), 0, n - 1).astype(np.int64)
    pairs = np.unique(np.stack((tx, ty), axis=1), axis=0)
    return {(int(x), int(y)) for x, y in pairs.tolist()}


def max_square(tiles: Iterable[Tile]) -> tuple[int, Tile | None]:
    """Largest fully visited k x k square: ``(k, top-left (x, y))``, ``(0, None)`` if empty.

    Sparse dynamic programming over the visited tiles (bottom-right corners in (y, x)
    order). Ties go to the square with the smallest top-left (y, then x).
    """
    visited = set(tiles)
    side: dict[Tile, int] = {}
    best, best_corner = 0, None
    for x, y in sorted(visited, key=lambda tile: (tile[1], tile[0])):
        k = 1 + min(side.get((x - 1, y), 0), side.get((x, y - 1), 0), side.get((x - 1, y - 1), 0))
        side[(x, y)] = k
        if k > best:
            best, best_corner = k, (x, y)
    if best_corner is None:
        return 0, None
    return best, (best_corner[0] - best + 1, best_corner[1] - best + 1)


def _neighbours(tile: Tile) -> tuple[Tile, Tile, Tile, Tile]:
    x, y = tile
    return (x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)


def max_cluster(tiles: Iterable[Tile]) -> int:
    """Size of the largest 4-connected group of tiles whose 4 neighbours are all visited."""
    visited = set(tiles)
    inner = {t for t in visited if all(nb in visited for nb in _neighbours(t))}
    best = 0
    seen: set[Tile] = set()
    for start in inner:
        if start in seen:
            continue
        seen.add(start)
        queue = deque([start])
        size = 0
        while queue:
            tile = queue.popleft()
            size += 1
            for nb in _neighbours(tile):
                if nb in inner and nb not in seen:
                    seen.add(nb)
                    queue.append(nb)
        best = max(best, size)
    return best


def _segment_distances(
    px: FloatArray, py: FloatArray, ax: float, ay: float, bx: float, by: float
) -> FloatArray:
    """Distance of points to the segment a-b (planar)."""
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return np.asarray(np.hypot(px - ax, py - ay), dtype=np.float64)
    u = np.clip(((px - ax) * dx + (py - ay) * dy) / length2, 0.0, 1.0)
    return np.asarray(np.hypot(px - (ax + u * dx), py - (ay + u * dy)), dtype=np.float64)


def simplify_track(lat: ArrayLike, lon: ArrayLike, epsilon_m: float) -> IndexArray:
    """Douglas-Peucker simplification: sorted indices of the points to keep.

    Iterative (explicit stack), so long tracks cannot hit the recursion limit. Distances are
    measured to the segment (not the infinite line) in an equirectangular projection around
    the track's mean latitude. Points with NaN coordinates are never kept; the first and last
    valid points always are.
    """
    if epsilon_m < 0:
        raise ValueError("epsilon_m must be >= 0")
    la = np.asarray(lat, dtype=np.float64).ravel()
    lo = np.asarray(lon, dtype=np.float64).ravel()
    if la.shape != lo.shape:
        raise ValueError(f"lat and lon must be equally long, got {la.size} and {lo.size}")
    valid = np.nonzero(np.isfinite(la) & np.isfinite(lo))[0].astype(np.intp)
    if valid.size <= 2:
        return valid

    lat_v, lon_v = la[valid], lo[valid]
    scale = math.cos(math.radians(float(np.mean(lat_v))))
    px = np.radians(lon_v - lon_v[0]) * EARTH_RADIUS_M * scale
    py = np.radians(lat_v) * EARTH_RADIUS_M

    keep = np.zeros(valid.size, dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, valid.size - 1)]
    while stack:
        s, e = stack.pop()
        if e - s < 2:
            continue
        dist = _segment_distances(
            px[s + 1 : e], py[s + 1 : e], float(px[s]), float(py[s]), float(px[e]), float(py[e])
        )
        i = int(np.argmax(dist))
        if dist[i] > epsilon_m:
            mid = s + 1 + i
            keep[mid] = True
            stack.append((s, mid))
            stack.append((mid, e))
    return valid[keep]


def cluster_places(
    points: Iterable[tuple[float, float, int]], radius_m: float
) -> list[tuple[float, float, int]]:
    """Group start points ``(lat, lon, activities)`` into places ``(lat, lon, activities)``.

    Deterministic; coordinates are rounded to 4 decimals (about 11 m).

    Points are visited most used first (ties by lat, lon). A point joins the nearest place whose
    centre (its most used point) lies within ``radius_m``, otherwise it becomes a new place, so
    place centres are always more than ``radius_m`` apart. Places come most used first.
    """
    centres: list[tuple[float, float]] = []
    counts: list[int] = []
    for lat, lon, n in sorted(points, key=lambda p: (-p[2], p[0], p[1])):
        if centres:
            lats, lons = zip(*centres, strict=True)
            dist = haversine_m(lat, lon, lats, lons)
            nearest = int(np.argmin(dist))
            if float(dist[nearest]) <= radius_m:
                counts[nearest] += n
                continue
        centres.append((lat, lon))
        counts.append(n)
    places = [
        (round(lat, 4), round(lon, 4), n) for (lat, lon), n in zip(centres, counts, strict=True)
    ]
    return sorted(places, key=lambda p: (-p[2], p[0], p[1]))
