"""/api/map: tracks, explorer tiles and start places, cross-checked against the base tables."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.analytics.geo import cluster_places, haversine_m, max_cluster, max_square
from garminizer.analytics.series import thin
from garminizer.api.routers.maps import LOW_DETAIL_POINTS, PLACE_RADIUS_M
from tests.api.conftest import API_END

RANGE_START = API_END - timedelta(days=364)  # RangeDep default: one year ending at the last day


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in s.execute(text(query), params)]


def test_thin_keeps_ends_and_limit() -> None:
    pts = list(range(1000))
    out = thin(pts, 120)
    assert len(out) <= 120
    assert out[0] == 0
    assert out[-1] == 999
    assert out == sorted(set(out))
    assert thin(pts[:50], 120) == pts[:50]
    assert thin(pts[:121], 120)[-1] == 120


def test_tracks_low_detail(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/map/tracks")
    assert resp.status_code == 200
    tracks = resp.json()
    db = {
        r["activity_id"]: r
        for r in _rows(
            sql,
            "SELECT t.activity_id, t.points FROM garmin.activity_track t "
            "JOIN garmin.activity a USING (activity_id) "
            "WHERE a.start_time_local >= :a AND a.start_time_local < :b",
            a=RANGE_START,
            b=API_END + timedelta(days=1),
        )
    }
    assert len(tracks) == len(db) > 0
    assert set(tracks[0]) == {"activity_id", "sport_group", "name", "day", "distance_m", "points"}
    assert any(len(db[t["activity_id"]]["points"]) > LOW_DETAIL_POINTS for t in tracks)
    for t in tracks:
        full = db[t["activity_id"]]["points"]
        assert 2 <= len(t["points"]) <= LOW_DETAIL_POINTS
        assert t["points"][0] == full[0]
        assert t["points"][-1] == full[-1]


def test_tracks_high_detail_and_sport_filter(client: TestClient, sql: Session) -> None:
    tracks = client.get("/api/map/tracks", params={"detail": "high", "sport": "run"}).json()
    lengths = {
        r["activity_id"]: r["n"]
        for r in _rows(
            sql,
            "SELECT t.activity_id, jsonb_array_length(t.points) AS n "
            "FROM garmin.activity_track t JOIN garmin.activity a USING (activity_id) "
            "WHERE a.sport_group = 'run'",
        )
    }
    assert tracks
    assert {t["sport_group"] for t in tracks} == {"run"}
    assert {t["activity_id"] for t in tracks} == set(lengths)
    assert all(len(t["points"]) == lengths[t["activity_id"]] for t in tracks)
    assert client.get("/api/map/tracks", params={"detail": "medium"}).status_code == 422


def test_tiles_match_activity_tiles(client: TestClient, sql: Session) -> None:
    body = client.get("/api/map/tiles").json()
    assert body["zoom"] == 14
    db = _rows(
        sql,
        "SELECT x, y, count(*) AS visits FROM garmin.activity_tile WHERE zoom = 14 GROUP BY x, y",
    )
    assert body["total"] == len(body["tiles"]) == len(db) > 0
    assert {(t["x"], t["y"]): t["visits"] for t in body["tiles"]} == {
        (r["x"], r["y"]): r["visits"] for r in db
    }
    visited = {(r["x"], r["y"]) for r in db}
    size, corner = max_square(visited)
    assert corner is not None
    assert body["max_square"] == {"size": size, "x": corner[0], "y": corner[1]}
    sq = body["max_square"]
    assert all(
        (sq["x"] + dx, sq["y"] + dy) in visited
        for dx in range(sq["size"])
        for dy in range(sq["size"])
    )
    assert body["max_cluster"] == max_cluster(visited)


def test_tiles_other_zoom_is_empty(client: TestClient) -> None:
    body = client.get("/api/map/tiles", params={"zoom": 10}).json()
    assert body == {"zoom": 10, "tiles": [], "total": 0, "max_square": None, "max_cluster": 0}
    assert client.get("/api/map/tiles", params={"zoom": 99}).status_code == 422


def test_cluster_places_groups_nearby_starts() -> None:
    # ~0.00045 deg latitude is 50 m; at 48 deg N ~0.0054 deg longitude is 400 m.
    a = (48.0, 11.0, 5)
    b = (48.00045, 11.0, 3)  # 50 m from a -> joins a
    c = (48.0, 11.0054, 4)  # 400 m from a -> own place
    d = (48.00153, 11.0, 1)  # 170 m from a, 120 m from b (not a centre) -> own place
    e = (48.0, 11.0054, 4)  # same spot as c, equal count: tie broken by position
    places = cluster_places([d, c, b, a], PLACE_RADIUS_M)
    assert places == [
        (48.0, 11.0, 8),
        (48.0, 11.0054, 4),
        (48.0015, 11.0, 1),
    ]
    # Input order does not matter.
    assert cluster_places([a, b, c, d], PLACE_RADIUS_M) == places
    assert cluster_places([c, e], PLACE_RADIUS_M)[0][2] == 8
    assert cluster_places([], PLACE_RADIUS_M) == []


def test_places_cluster_start_points(client: TestClient, sql: Session) -> None:
    places = client.get("/api/map/places").json()
    n = _rows(
        sql,
        "SELECT count(*) AS n FROM garmin.activity WHERE start_lat IS NOT NULL "
        "AND start_time_local >= :a AND start_time_local < :b",
        a=RANGE_START,
        b=API_END + timedelta(days=1),
    )[0]["n"]
    assert places
    assert sum(p["activities"] for p in places) == n
    counts = [p["activities"] for p in places]
    assert counts == sorted(counts, reverse=True)
    for p in places:
        assert round(p["lat"], 4) == p["lat"]
        assert round(p["lon"], 4) == p["lon"]
    # Place centres are further apart than the clustering radius (no duplicates of one spot).
    for i, p in enumerate(places):
        for q in places[i + 1 :]:
            assert float(haversine_m(p["lat"], p["lon"], q["lat"], q["lon"])) > PLACE_RADIUS_M
    assert client.get("/api/map/places").json() == places  # deterministic
    walks = client.get("/api/map/places", params={"sport": "walk"}).json()
    assert 0 < sum(p["activities"] for p in walks) < n
