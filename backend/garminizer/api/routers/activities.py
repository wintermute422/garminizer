"""Activities: filterable list, totals, detail, downsampled streams and per-activity curves."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from pydantic import Field

from garminizer.analytics.series import lttb
from garminizer.api.deps import RangeDep, SessionDep, SportDep, one, rows
from garminizer.api.schemas import ActivitySummary, Model

router = APIRouter(prefix="/api/activities", tags=["activities"])

SUMMARY_COLUMNS = """
    a.activity_id, a.name, a.sport_type, a.sport_group, a.start_time_utc, a.start_time_local,
    a.duration_s, a.moving_s, a.distance_m, a.elevation_gain_m, a.avg_speed_mps, a.avg_hr,
    a.max_hr, a.avg_power_w, a.normalized_power_w, a.calories, a.training_load, a.aerobic_te,
    a.anaerobic_te, a.training_effect_label, a.vo2max, a.location_name,
    EXISTS (SELECT 1 FROM garmin.activity_track t WHERE t.activity_id = a.activity_id) AS has_track
"""
SORTS = {
    "start_time": "a.start_time_utc",
    "distance": "a.distance_m",
    "duration": "a.duration_s",
    "load": "a.training_load",
    "elevation": "a.elevation_gain_m",
    "avg_hr": "a.avg_hr",
    "pace": "a.avg_speed_mps",
}


class ActivityList(Model):
    total: int
    items: list[ActivitySummary]


class SportTotals(Model):
    sport_group: str
    activities: int
    distance_m: float | None
    duration_s: float | None = Field(description="Elapsed time")
    moving_s: float | None = Field(description="Moving time (elapsed when an activity has none)")
    elevation_gain_m: float | None
    training_load: float | None
    calories: float | None


class Lap(Model):
    lap_index: int
    start_time_utc: datetime | None
    duration_s: float | None
    moving_s: float | None
    distance_m: float | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_cadence: float | None
    avg_power_w: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None
    intensity: str | None


class Split(Model):
    split_index: int
    distance_m: float
    duration_s: float
    avg_hr: float | None
    avg_cadence: float | None
    avg_power_w: float | None
    elevation_gain_m: float | None
    elevation_loss_m: float | None


class Zone(Model):
    kind: str
    zone: int
    seconds: float
    low_value: float | None


class Weather(Model):
    temperature_c: float | None
    apparent_temperature_c: float | None
    humidity_pct: float | None
    wind_speed_mps: float | None
    wind_direction_deg: float | None
    condition: str | None


class GearRef(Model):
    uuid: str
    gear_type: str
    display_name: str | None


class Track(Model):
    points: list[list[float]]
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class ActivityDetail(ActivitySummary):
    description: str | None
    elapsed_s: float | None
    elevation_loss_m: float | None
    min_elevation_m: float | None
    max_elevation_m: float | None
    max_speed_mps: float | None
    avg_cadence: float | None
    max_cadence: float | None
    max_power_w: float | None
    training_stress_score: float | None
    intensity_factor: float | None
    trimp: float | None
    avg_temperature_c: float | None
    avg_respiration: float | None
    avg_stride_length_m: float | None
    avg_vertical_oscillation_cm: float | None
    avg_ground_contact_ms: float | None
    avg_vertical_ratio: float | None
    steps: int | None
    pool_length_m: float | None
    active_lengths: int | None
    avg_swolf: float | None
    total_sets: int | None
    total_reps: int | None
    moderate_intensity_min: int | None
    vigorous_intensity_min: int | None
    body_battery_delta: int | None
    water_estimated_ml: float | None
    aerobic_decoupling_pct: float | None
    efficiency_factor: float | None
    has_samples: bool
    laps: list[Lap]
    splits_km: list[Split]
    splits_mi: list[Split]
    zones: list[Zone]
    weather: Weather | None
    gear: list[GearRef]
    track: Track | None
    previous_id: int | None
    next_id: int | None


class Streams(Model):
    """Aligned, downsampled series; every list has the same length (null = not recorded)."""

    points: int
    source_points: int
    t_s: list[float]
    distance_m: list[float | None]
    hr: list[float | None]
    speed_mps: list[float | None]
    altitude_m: list[float | None]
    cadence: list[float | None]
    power_w: list[float | None]
    temperature_c: list[float | None]
    lat: list[float | None]
    lon: list[float | None]


class CurvePoint(Model):
    duration_s: int
    value: float
    best: float | None


class ActivityCurve(Model):
    metric: str
    points: list[CurvePoint]


@router.get("", response_model=ActivityList)
def list_activities(
    session: SessionDep,
    rng: RangeDep,
    sport: SportDep,
    q: Annotated[str | None, Query(max_length=100, description="Name contains")] = None,
    sort: Annotated[Literal[tuple(SORTS)], Query()] = "start_time",  # type: ignore[valid-type]
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
    limit: Annotated[int, Query(ge=1, le=1000)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ActivityList:
    where = "a.start_time_local >= :start AND a.start_time_local < :end_excl"
    params: dict[str, Any] = rng.params()
    if sport:
        where += " AND a.sport_group = :sport"
        params["sport"] = sport
    if q:
        where += " AND a.name ILIKE :q"
        params["q"] = f"%{q}%"
    total = one(session, f"SELECT count(*) AS n FROM garmin.activity a WHERE {where}", **params)  # noqa: S608
    items = rows(
        session,
        f"SELECT {SUMMARY_COLUMNS} FROM garmin.activity a WHERE {where} "  # noqa: S608 - whitelisted
        f"ORDER BY {SORTS[sort]} {order.upper()} NULLS LAST, a.activity_id DESC "
        "LIMIT :limit OFFSET :offset",
        limit=limit,
        offset=offset,
        **params,
    )
    return ActivityList(
        total=total["n"] if total else 0, items=[ActivitySummary(**r) for r in items]
    )


@router.get("/totals", response_model=list[SportTotals])
def totals(session: SessionDep, rng: RangeDep) -> list[SportTotals]:
    data = rows(
        session,
        """
        SELECT sport_group, count(*) AS activities, sum(distance_m) AS distance_m,
               sum(duration_s) AS duration_s, sum(coalesce(moving_s, duration_s)) AS moving_s,
               sum(elevation_gain_m) AS elevation_gain_m, sum(training_load) AS training_load,
               sum(calories) AS calories
        FROM garmin.activity
        WHERE start_time_local >= :start AND start_time_local < :end_excl
        GROUP BY sport_group ORDER BY count(*) DESC
        """,
        **rng.params(),
    )
    return [SportTotals(**r) for r in data]


@router.get("/{activity_id}", response_model=ActivityDetail)
def activity_detail(activity_id: int, session: SessionDep) -> ActivityDetail:
    a = one(
        session,
        f"SELECT {SUMMARY_COLUMNS}, a.* FROM garmin.activity a WHERE a.activity_id = :id",  # noqa: S608
        id=activity_id,
    )
    if a is None:
        raise HTTPException(status_code=404, detail="activity not found")
    p = {"id": activity_id}
    laps = rows(
        session, "SELECT * FROM garmin.activity_lap WHERE activity_id = :id ORDER BY lap_index", **p
    )
    splits = rows(
        session,
        "SELECT * FROM garmin.activity_split WHERE activity_id = :id ORDER BY unit, split_index",
        **p,
    )
    zones = rows(
        session,
        "SELECT * FROM garmin.activity_zone WHERE activity_id = :id ORDER BY kind, zone",
        **p,
    )
    weather = one(session, "SELECT * FROM garmin.activity_weather WHERE activity_id = :id", **p)
    gear = rows(
        session,
        "SELECT g.uuid, g.gear_type, g.display_name FROM garmin.activity_gear ag "
        "JOIN garmin.gear g ON g.uuid = ag.gear_uuid WHERE ag.activity_id = :id",
        **p,
    )
    track = one(session, "SELECT * FROM garmin.activity_track WHERE activity_id = :id", **p)
    nav = one(
        session,
        """
        SELECT (SELECT activity_id FROM garmin.activity WHERE start_time_utc < :t
                ORDER BY start_time_utc DESC LIMIT 1) AS previous_id,
               (SELECT activity_id FROM garmin.activity WHERE start_time_utc > :t
                ORDER BY start_time_utc LIMIT 1) AS next_id
        """,
        t=a["start_time_utc"],
    )
    return ActivityDetail(
        **a,
        laps=[Lap(**r) for r in laps],
        splits_km=[Split(**r) for r in splits if r["unit"] == "km"],
        splits_mi=[Split(**r) for r in splits if r["unit"] == "mi"],
        zones=[Zone(**r) for r in zones],
        weather=Weather(**weather) if weather else None,
        gear=[GearRef(**g) for g in gear],
        track=Track(**track) if track else None,
        previous_id=nav["previous_id"] if nav else None,
        next_id=nav["next_id"] if nav else None,
    )


def _col(values: list[Any]) -> np.ndarray[Any, np.dtype[np.float64]]:
    return np.array([np.nan if v is None else float(v) for v in values], dtype=np.float64)


def _out(a: np.ndarray[Any, Any], idx: np.ndarray[Any, Any], nd: int) -> list[float | None]:
    return [None if not np.isfinite(v) else round(float(v), nd) for v in a[idx]]


@router.get("/{activity_id}/streams", response_model=Streams)
def activity_streams(
    activity_id: int,
    session: SessionDep,
    points: Annotated[int, Query(ge=50, le=10_000)] = 1500,
) -> Streams:
    data = rows(
        session,
        "SELECT t_s, distance_m, hr, speed_mps, altitude_m, cadence, power_w, temperature_c, "
        "lat, lon FROM garmin.activity_sample WHERE activity_id = :id ORDER BY t_s",
        id=activity_id,
    )
    if not data:
        if one(
            session, "SELECT 1 AS x FROM garmin.activity WHERE activity_id = :id", id=activity_id
        ):
            return Streams(
                points=0,
                source_points=0,
                t_s=[],
                distance_m=[],
                hr=[],
                speed_mps=[],
                altitude_m=[],
                cadence=[],
                power_w=[],
                temperature_c=[],
                lat=[],
                lon=[],
            )
        raise HTTPException(status_code=404, detail="activity not found")
    cols = {k: _col([r[k] for r in data]) for k in data[0]}
    t = cols["t_s"]
    key = next(
        (
            cols[k]
            for k in ("hr", "speed_mps", "altitude_m", "power_w")
            if np.isfinite(cols[k]).any()
        ),
        np.zeros_like(t),
    )
    idx = lttb(t, key, points)
    return Streams(
        points=len(idx),
        source_points=len(t),
        t_s=[float(v) for v in t[idx]],
        distance_m=_out(cols["distance_m"], idx, 1),
        hr=_out(cols["hr"], idx, 0),
        speed_mps=_out(cols["speed_mps"], idx, 3),
        altitude_m=_out(cols["altitude_m"], idx, 1),
        cadence=_out(cols["cadence"], idx, 0),
        power_w=_out(cols["power_w"], idx, 0),
        temperature_c=_out(cols["temperature_c"], idx, 1),
        lat=_out(cols["lat"], idx, 6),
        lon=_out(cols["lon"], idx, 6),
    )


@router.get("/{activity_id}/curve", response_model=ActivityCurve)
def activity_curve(
    activity_id: int,
    session: SessionDep,
    metric: Annotated[Literal["power", "speed", "hr"], Query()] = "speed",
) -> ActivityCurve:
    data = rows(
        session,
        """
        SELECT e.duration_s, e.value,
               (SELECT max(b.value) FROM garmin.activity_best_effort b
                JOIN garmin.activity x ON x.activity_id = b.activity_id
                WHERE b.metric = e.metric AND b.duration_s = e.duration_s
                  AND x.sport_group = a.sport_group) AS best
        FROM garmin.activity_best_effort e JOIN garmin.activity a USING (activity_id)
        WHERE e.activity_id = :id AND e.metric = :metric
        ORDER BY e.duration_s
        """,
        id=activity_id,
        metric=metric,
    )
    return ActivityCurve(metric=metric, points=[CurvePoint(**r) for r in data])
