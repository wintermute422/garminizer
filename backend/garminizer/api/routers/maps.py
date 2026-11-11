"""Maps: activity tracks, explorer tiles (with max square/cluster) and favourite start places."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from garminizer.analytics.geo import cluster_places, max_cluster, max_square
from garminizer.analytics.series import thin
from garminizer.api.activity_sql import ActivityFilterDep
from garminizer.api.deps import SessionDep, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/map", tags=["map"])

LOW_DETAIL_POINTS = 120
PLACE_RADIUS_M = 150.0  # start points closer than this to a place's centre belong to it


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


@router.get("/tracks", response_model=list[MapTrack])
def tracks(
    session: SessionDep,
    flt: ActivityFilterDep,
    detail: Annotated[
        Literal["low", "high"],
        Query(description=f"low: at most {LOW_DETAIL_POINTS} points per track"),
    ] = "low",
) -> list[MapTrack]:
    where, params = flt.sql()
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
def places(session: SessionDep, flt: ActivityFilterDep) -> list[MapPlace]:
    """Favourite start places: activity starts within 150 m of each other, most used first."""
    where, params = flt.sql()
    data = rows(
        session,
        f"""
        SELECT round(a.start_lat::numeric, 4)::float8 AS lat,
               round(a.start_lon::numeric, 4)::float8 AS lon, count(*) AS activities
        FROM garmin.activity a
        WHERE {where} AND a.start_lat IS NOT NULL AND a.start_lon IS NOT NULL
        GROUP BY 1, 2
        """,  # noqa: S608 - where is built from constants, values are bound
        **params,
    )
    places = cluster_places(
        ((r["lat"], r["lon"], int(r["activities"])) for r in data), PLACE_RADIUS_M
    )
    return [MapPlace(lat=lat, lon=lon, activities=n) for lat, lon, n in places]
