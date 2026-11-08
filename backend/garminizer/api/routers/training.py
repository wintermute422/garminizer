"""Training: daily load (CTL/ATL/TSB), Garmin training status, volume, intensity, effects."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from garminizer.api.deps import RangeDep, SessionDep, SportDep, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/training", tags=["training"])

Period = Literal["week", "month"]
PeriodQuery = Annotated[Period, Query(description="Bucket size (ISO week or calendar month)")]
VOLUME_VIEWS: dict[str, tuple[str, str]] = {
    "week": ("garmin.weekly_volume", "week"),
    "month": ("garmin.monthly_volume", "month"),
}


class TrainingLoadPoint(Model):
    day: date
    load: float
    trimp: float
    activities: int
    ctl: float
    atl: float
    tsb: float
    acwr: float | None
    monotony: float | None
    strain: float | None


class TrainingStatusPoint(Model):
    day: date
    status: str | None
    acute_load: float | None
    chronic_load: float | None
    acwr: float | None
    acwr_status: str | None
    load_low_aerobic: float | None
    load_high_aerobic: float | None
    load_anaerobic: float | None
    target_low_aerobic_min: float | None
    target_low_aerobic_max: float | None
    target_high_aerobic_min: float | None
    target_high_aerobic_max: float | None
    target_anaerobic_min: float | None
    target_anaerobic_max: float | None
    load_balance_feedback: str | None
    heat_acclimation_pct: float | None
    altitude_acclimation_m: float | None


class TrainingVolumePoint(Model):
    period_start: date
    sport_group: str
    activities: int
    distance_m: float | None
    duration_s: float | None
    moving_s: float | None
    elevation_gain_m: float | None
    training_load: float | None
    calories: float | None


class TrainingIntensityPoint(Model):
    period_start: date
    zone_1_s: float
    zone_2_s: float
    zone_3_s: float
    zone_4_s: float
    zone_5_s: float
    total_s: float


class TrainingEffectActivity(Model):
    activity_id: int
    day: date
    name: str | None
    sport_group: str
    aerobic_te: float | None
    anaerobic_te: float | None
    training_effect_label: str | None
    training_load: float | None


class TrainingEffectLabel(Model):
    label: str
    activities: int


class TrainingEffects(Model):
    activities: list[TrainingEffectActivity]
    labels: list[TrainingEffectLabel]


@router.get("/load", response_model=list[TrainingLoadPoint])
def training_load(session: SessionDep, rng: RangeDep) -> list[TrainingLoadPoint]:
    """Daily load with fitness (CTL), fatigue (ATL), form (TSB), ACWR, monotony and strain."""
    data = rows(
        session,
        """
        SELECT day, load, trimp, activities, ctl, atl, tsb, acwr, monotony, strain
        FROM garmin.daily_load WHERE day BETWEEN :start AND :end ORDER BY day
        """,
        **rng.params(),
    )
    return [TrainingLoadPoint(**r) for r in data]


@router.get("/status", response_model=list[TrainingStatusPoint])
def training_status(session: SessionDep, rng: RangeDep) -> list[TrainingStatusPoint]:
    """Garmin training status, acute/chronic load and load balance per day."""
    data = rows(
        session,
        "SELECT * FROM garmin.training_status WHERE day BETWEEN :start AND :end ORDER BY day",
        **rng.params(),
    )
    return [TrainingStatusPoint(**r) for r in data]


@router.get("/volume", response_model=list[TrainingVolumePoint])
def training_volume(
    session: SessionDep, rng: RangeDep, sport: SportDep, period: PeriodQuery = "week"
) -> list[TrainingVolumePoint]:
    """Volume per week/month and sport group.

    Every period that overlaps the range is returned with its full totals (a range starting
    mid-week includes that whole week).
    """
    view, column = VOLUME_VIEWS[period]
    params: dict[str, Any] = {**rng.params(), "period": period}
    where = f"{column} >= date_trunc(:period, CAST(:start AS timestamp))::date AND {column} <= :end"
    if sport:
        where += " AND sport_group = :sport"
        params["sport"] = sport
    data = rows(
        session,
        f"""
        SELECT {column} AS period_start, sport_group, activities, distance_m, duration_s,
               moving_s, elevation_gain_m, training_load, calories
        FROM {view} WHERE {where} ORDER BY {column}, sport_group
        """,  # noqa: S608 - view/column come from a whitelist
        **params,
    )
    return [TrainingVolumePoint(**r) for r in data]


@router.get("/intensity", response_model=list[TrainingIntensityPoint])
def training_intensity(
    session: SessionDep, rng: RangeDep, sport: SportDep, period: PeriodQuery = "week"
) -> list[TrainingIntensityPoint]:
    """Time in heart-rate zones 1-5 per week/month (activity local start date).

    Periods are selected like in /volume: every period overlapping the range, full totals.
    """
    params: dict[str, Any] = {**rng.params(), "period": period}
    where = "z.kind = 'hr'"
    if sport:
        where += " AND a.sport_group = :sport"
        params["sport"] = sport
    data = rows(
        session,
        f"""
        SELECT p.period_start,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone = 1), 0) AS zone_1_s,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone = 2), 0) AS zone_2_s,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone = 3), 0) AS zone_3_s,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone = 4), 0) AS zone_4_s,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone = 5), 0) AS zone_5_s,
               coalesce(sum(p.seconds) FILTER (WHERE p.zone BETWEEN 1 AND 5), 0) AS total_s
        FROM (
            SELECT date_trunc(:period, a.start_time_local)::date AS period_start,
                   z.zone, z.seconds
            FROM garmin.activity_zone z JOIN garmin.activity a USING (activity_id)
            WHERE {where}
              AND a.start_time_local >= date_trunc(:period, CAST(:start AS timestamp))
              AND a.start_time_local < date_trunc(:period, CAST(:end AS timestamp))
                                       + CAST('1 ' || :period AS interval)
        ) p
        GROUP BY p.period_start ORDER BY p.period_start
        """,  # noqa: S608 - only fixed SQL fragments are interpolated
        **params,
    )
    return [TrainingIntensityPoint(**r) for r in data]


@router.get("/effects", response_model=TrainingEffects)
def training_effects(session: SessionDep, rng: RangeDep, sport: SportDep) -> TrainingEffects:
    """Aerobic/anaerobic training effect of every activity in the range, and label counts."""
    params: dict[str, Any] = rng.params()
    where = (
        "start_time_local >= :start AND start_time_local < :end_excl "
        "AND (aerobic_te IS NOT NULL OR anaerobic_te IS NOT NULL)"
    )
    if sport:
        where += " AND sport_group = :sport"
        params["sport"] = sport
    data = rows(
        session,
        f"""
        SELECT activity_id, start_time_local::date AS day, name, sport_group, aerobic_te,
               anaerobic_te, training_effect_label, training_load
        FROM garmin.activity WHERE {where} ORDER BY start_time_local, activity_id
        """,  # noqa: S608 - only fixed SQL fragments are interpolated
        **params,
    )
    activities = [TrainingEffectActivity(**r) for r in data]
    counts: dict[str, int] = {}
    for a in activities:
        if a.training_effect_label:
            counts[a.training_effect_label] = counts.get(a.training_effect_label, 0) + 1
    labels = [
        TrainingEffectLabel(label=k, activities=v)
        for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return TrainingEffects(activities=activities, labels=labels)
