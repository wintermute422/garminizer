"""S3a: haversine, slippy tiles, squares/clusters and Douglas-Peucker on synthetic coordinates."""

from __future__ import annotations

import math
import time
from itertools import pairwise

import numpy as np
import pytest

from garminizer.analytics.geo import (
    EARTH_RADIUS_M,
    haversine_m,
    max_cluster,
    max_square,
    simplify_track,
    tile_xy,
    tiles_for_track,
)

NAN = math.nan


def _block(x0: int, y0: int, w: int, h: int) -> set[tuple[int, int]]:
    return {(x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h)}


# --- haversine --------------------------------------------------------------------------------


def test_haversine_known_distances() -> None:
    one_degree = EARTH_RADIUS_M * math.pi / 180  # 111195.08023353292 m
    assert float(haversine_m(0, 0, 0, 1)) == pytest.approx(111195.08023353292, rel=1e-12)
    assert float(haversine_m(0, 0, 1, 0)) == pytest.approx(one_degree, rel=1e-12)
    assert float(haversine_m(0, 0, 0, 180)) == pytest.approx(20015114.442035925, rel=1e-12)
    assert float(haversine_m(45, 7, 45, 7)) == 0.0


def test_haversine_is_vectorised() -> None:
    got = haversine_m([0, 0, 45], [0, 0, 7], [0, 1, 45], [1, 0, 7])
    assert got.shape == (3,)
    np.testing.assert_allclose(got, [111195.08023353292, 111195.08023353292, 0.0], rtol=1e-12)


# --- tiles ------------------------------------------------------------------------------------


def test_tile_xy_standard_values() -> None:
    assert tile_xy(0, 0, 0) == (0, 0)
    assert tile_xy(0.1, 0.1, 1) == (1, 0)
    assert tile_xy(-0.1, -0.1, 1) == (0, 1)
    # x = floor(187/360 * 2^14) = floor(8510.58), y = floor(5893.74)
    assert tile_xy(45, 7, 14) == (8510, 5893)
    # clamped to the tile range
    assert tile_xy(89, 180, 2) == (3, 0)
    assert tile_xy(-89, -180, 2) == (0, 3)
    with pytest.raises(ValueError):
        tile_xy(0, 0, -1)


def test_tiles_for_track_fills_crossed_tiles() -> None:
    # zoom 4: lon 1 -> x 8.04, lon 80 -> x 11.56; lat 10 -> y 7.55
    assert tiles_for_track([10, 10], [1, 80], zoom=4) == {(8, 7), (9, 7), (10, 7), (11, 7)}
    # north-south: lat 10 -> y 7.55, lat -30 -> y 9.40
    assert tiles_for_track([10, -30], [1, 1], zoom=4) == {(8, 7), (8, 8), (8, 9)}


def test_tiles_for_track_nan_breaks_the_track() -> None:
    assert tiles_for_track([10, NAN, 10], [1, 50, 80], zoom=4) == {(8, 7), (11, 7)}
    assert tiles_for_track([10, 10, 10], [1, NAN, 80], zoom=4) == {(8, 7), (11, 7)}


def test_tiles_for_track_edge_cases() -> None:
    assert tiles_for_track([], [], zoom=14) == set()
    assert tiles_for_track([NAN], [NAN]) == set()
    assert tiles_for_track([45.0], [7.0], zoom=14) == {(8510, 5893)}
    # antimeridian wrap is not densified across the whole world
    assert tiles_for_track([10, 10], [179.99, -179.99], zoom=4) == {(15, 7), (0, 7)}


def test_tiles_for_track_has_no_gaps_on_a_long_segment() -> None:
    tiles = tiles_for_track([45.0, 45.0], [7.0, 7.1], zoom=14)
    xs = sorted(x for x, _ in tiles)
    assert {y for _, y in tiles} == {5893}
    assert xs == list(range(xs[0], xs[-1] + 1))
    assert xs[0] == tile_xy(45.0, 7.0, 14)[0]
    assert xs[-1] == tile_xy(45.0, 7.1, 14)[0]
    assert len(xs) >= 4


# --- squares and clusters ---------------------------------------------------------------------


def test_max_square() -> None:
    assert max_square([]) == (0, None)
    assert max_square([(5, 6)]) == (1, (5, 6))
    tiles = _block(10, 20, 3, 3) | {(13, 20), (40, 40)}
    assert max_square(tiles) == (3, (10, 20))
    # 3x3 ring without its centre contains no 2x2 square
    assert max_square(_block(0, 0, 3, 3) - {(1, 1)}) == (1, (0, 0))
    # ties: smallest top-left by (y, x)
    assert max_square(_block(10, 5, 2, 2) | _block(0, 9, 2, 2)) == (2, (10, 5))
    assert max_square(_block(3, 0, 4, 6)) == (4, (3, 0))


def test_max_cluster() -> None:
    assert max_cluster([]) == 0
    assert max_cluster(_block(0, 0, 2, 2)) == 0
    assert max_cluster(_block(0, 0, 3, 3)) == 1
    assert max_cluster(_block(0, 0, 4, 4)) == 4
    assert max_cluster(_block(0, 0, 5, 3)) == 3  # inner row of 3
    assert max_cluster(_block(0, 0, 3, 3) | _block(10, 0, 3, 3)) == 1
    plus = {(1, 0), (0, 1), (1, 1), (2, 1), (1, 2)}
    assert max_cluster(plus) == 1
    # overlapping blocks: inner tiles (1,1), (2,1), (1,2), (2,2)
    assert max_cluster(_block(0, 0, 3, 3) | _block(1, 1, 3, 3)) == 4
    # blocks touching at one corner tile: inner tiles (1,1), (2,2), (3,3) touch only
    # diagonally, so with 4-connectivity each is its own cluster
    assert max_cluster(_block(0, 0, 3, 3) | _block(2, 2, 3, 3)) == 1


# --- Douglas-Peucker --------------------------------------------------------------------------


def test_simplify_keeps_corner_of_l_shape() -> None:
    lat = [0.0] * 11 + [0.001 * k for k in range(1, 11)]
    lon = [0.001 * k for k in range(11)] + [0.01] * 10
    assert simplify_track(lat, lon, 1.0).tolist() == [0, 10, 20]
    assert simplify_track(lat, lon, 1e7).tolist() == [0, 20]


def test_simplify_out_and_back_uses_segment_distance() -> None:
    # first == last point: the turnaround must survive
    lat = [0.0] * 5
    lon = [0.0, 0.005, 0.01, 0.005, 0.0]
    assert simplify_track(lat, lon, 10.0).tolist() == [0, 2, 4]


def test_simplify_edge_cases_and_nan() -> None:
    assert simplify_track([], [], 5.0).tolist() == []
    assert simplify_track([45.0], [7.0], 5.0).tolist() == [0]
    assert simplify_track([45.0, 45.1], [7.0, 7.1], 5.0).tolist() == [0, 1]
    lat = [NAN, 0.0, NAN, 0.0, NAN]
    lon = [NAN, 0.0, 1.0, 0.01, NAN]
    assert simplify_track(lat, lon, 1.0).tolist() == [1, 3]
    with pytest.raises(ValueError):
        simplify_track([0, 1], [0, 1], -1.0)


def test_simplify_performance_and_tolerance_20000_points() -> None:
    rng = np.random.default_rng(3)
    lat = 45.0 + np.cumsum(rng.normal(0, 1e-4, 20000))
    lon = 7.0 + np.cumsum(rng.normal(0, 1e-4, 20000))
    eps = 5.0
    start = time.perf_counter()
    keep = simplify_track(lat, lon, eps)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0
    assert keep[0] == 0
    assert keep[-1] == 19999
    assert np.all(np.diff(keep) > 0)
    assert 2 < keep.size < 20000

    # every dropped point lies within eps of the kept segment that replaces it
    scale = math.cos(math.radians(float(lat.mean())))
    px = np.radians(lon - lon[0]) * EARTH_RADIUS_M * scale
    py = np.radians(lat) * EARTH_RADIUS_M
    for a, b in pairwise(keep.tolist()):
        if b - a < 2:
            continue
        qx, qy = px[a + 1 : b], py[a + 1 : b]
        dx, dy = px[b] - px[a], py[b] - py[a]
        u = np.clip(((qx - px[a]) * dx + (qy - py[a]) * dy) / (dx * dx + dy * dy), 0, 1)
        dist = np.hypot(qx - (px[a] + u * dx), qy - (py[a] + u * dy))
        assert dist.max() <= eps + 1e-6
