"""Maps: activity tracks, explorer tiles (with max square/cluster) and favourite start places."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, Query

from garminizer.analytics.geo import max_cluster, max_square
from garminizer.api.deps import RangeDep, SessionDep, SportDep, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/map", tags=["map"])

LOW_DETAIL_POINTS = 120


class MapTrack(Model):
    activity_id: int
    sport_group: str
    name: str | None
    day: date
    distance_m: float | None
    points: list[list[float]]


class MapTile(Model):
    x: int
    y: int
    visits: int
    first_visit: datetime


class MapSquare(Model):
    """Largest fully visited size x size block of tiles; (x, y) is its top-left tile."""

    size: int
    x: int
    y: int


class MapTiles(Model):
    zoom: int
    tiles: list[MapTile]
    total: int
    max_square: MapSquare | None
    max_cluster: int


class MapPlace(Model):
    lat: float
    lon: float
    activities: int


def thin(points: list[Any], limit: int) -> list[Any]:
    """Evenly spaced subset of at most ``limit`` points, always keeping the first and last."""
    n = len(points)
    if n <= limit:
        return points
    idx = np.unique(np.rint(np.linspace(0, n - 1, limit)).astype(np.intp))
    return [points[int(i)] for i in idx]


def _filter(rng: RangeDep, sport: str | None) -> tuple[str, dict[str, Any]]:
    where = "a.start_time_local >= :start AND a.start_time_local < :end_excl"
    params: dict[str, Any] = rng.params()
    if sport:
        where += " AND a.sport_group = :sport"
        params["sport"] = sport
    return where, params


@router.get("/tracks", response_model=list[MapTrack])
def tracks(
    session: SessionDep,
    rng: RangeDep,
    sport: SportDep,
    detail: Annotated[
        Literal["low", "high"],
        Query(description=f"low: at most {LOW_DETAIL_POINTS} points per track"),
    ] = "low",
) -> list[MapTrack]:
    where, params = _filter(rng, sport)
    data = rows(
        session,
        f"""
        SELECT a.activity_id, a.sport_group, a.name, a.start_time_local::date AS day,
               a.distance_m, t.points
        FROM garmin.activity a JOIN garmin.activity_track t USING (activity_id)
        WHERE {where} ORDER BY a.start_time_utc
        """,  # noqa: S608 - where is built from constants, values are bound
        **params,
    )
    if detail == "low":
        for r in data:
            r["points"] = thin(r["points"], LOW_DETAIL_POINTS)
    return [MapTrack(**r) for r in data]


@router.get("/tiles", response_model=MapTiles)
def tiles(
    session: SessionDep,
    zoom: Annotated[int, Query(ge=0, le=22, description="Slippy-map zoom level")] = 14,
) -> MapTiles:
    data = rows(
        session,
        "SELECT x, y, visits, first_visit FROM garmin.explorer_tile WHERE zoom = :zoom "
        "ORDER BY y, x",
        zoom=zoom,
    )
    visited = [(r["x"], r["y"]) for r in data]
    size, corner = max_square(visited)
    return MapTiles(
        zoom=zoom,
        tiles=[MapTile(**r) for r in data],
        total=len(data),
        max_square=MapSquare(size=size, x=corner[0], y=corner[1]) if corner else None,
        max_cluster=max_cluster(visited),
    )


@router.get("/places", response_model=list[MapPlace])
def places(session: SessionDep, rng: RangeDep, sport: SportDep) -> list[MapPlace]:
    """Activity start points rounded to 3 decimals (about 100 m), most used first."""
    where, params = _filter(rng, sport)
    data = rows(
        session,
        f"""
        SELECT round(a.start_lat::numeric, 3)::float8 AS lat,
               round(a.start_lon::numeric, 3)::float8 AS lon, count(*) AS activities
        FROM garmin.activity a
        WHERE {where} AND a.start_lat IS NOT NULL AND a.start_lon IS NOT NULL
        GROUP BY 1, 2 ORDER BY 3 DESC, 1, 2
        """,  # noqa: S608 - where is built from constants, values are bound
        **params,
    )
    return [MapPlace(**r) for r in data]
