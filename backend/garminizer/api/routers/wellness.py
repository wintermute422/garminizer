"""Wellness: daily summaries with HRV and readiness, intraday series and hour-of-day heatmaps.

Daily tables are keyed by the athlete's local day; intraday samples are UTC timestamps that are
bucketed in the athlete's time zone (garminizer.athlete: Garmin's zone, else TZ).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from sqlalchemy.orm import Session

from garminizer.api.deps import ClockDep, RangeDep, SessionDep, data_bounds, one, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/wellness", tags=["wellness"])

# Intraday series: table and value expression (stress: -1/-2 mean "no measurement" -> null).
SERIES: dict[str, tuple[str, str]] = {
    "hr": ("hr_sample", "bpm::float8"),
    "stress": ("stress_sample", "CASE WHEN level >= 0 THEN level::float8 END"),
    "body_battery": ("body_battery_sample", "level::float8"),
    "respiration": ("respiration_sample", "breaths_per_min::float8"),
    "spo2": ("spo2_sample", "spo2_pct::float8"),
}
# Heatmap metrics: table, timestamp column, value column, row filter, mean (else sum) per hour.
HEATMAP: dict[str, tuple[str, str, str, str, bool]] = {
    "hr": ("hr_sample", "ts", "bpm", "true", True),
    "stress": ("stress_sample", "ts", "level", "level >= 0", True),
    "body_battery": ("body_battery_sample", "ts", "level", "true", True),
    "respiration": ("respiration_sample", "ts", "breaths_per_min", "true", True),
    "steps": ("steps_interval", "start_utc", "steps", "true", False),
}
# Samples are first summed into 15-minute UTC bins (cheap integer arithmetic); every real-world
# UTC offset is a multiple of 15 minutes, so each bin lies inside one local hour and only the
# bins need the (expensive) time-zone conversion.
HEATMAP_SQL = """
    WITH bins AS (
      SELECT date_bin('15 minutes', {ts}, TIMESTAMPTZ '2000-01-01 00:00Z') AS bin,
             sum({value}::float8) FILTER (WHERE {cond}) AS s,
             count({value}) FILTER (WHERE {cond}) AS n
      FROM garmin.{table} WHERE {ts} >= :t0 AND {ts} < :t1
      GROUP BY 1)
    SELECT date_trunc('hour', bin AT TIME ZONE :tz) AS h, {final} AS v
    FROM bins GROUP BY 1
"""
HeatmapMetric = Literal["hr", "stress", "body_battery", "steps", "respiration"]


def as_utc(ts: datetime | None) -> datetime | None:
    return ts.astimezone(UTC) if ts is not None else None


def series_rows(
    session: Session, key: str, t0: datetime, t1: datetime, *, include_end: bool = False
) -> list[dict[str, Any]]:
    """``[{ts, value}]`` of one intraday series in ``[t0, t1)`` (``[t0, t1]`` with include_end)."""
    table, expr = SERIES[key]
    op = "<=" if include_end else "<"
    data = rows(
        session,
        f"SELECT ts, {expr} AS value FROM garmin.{table} "  # noqa: S608 - whitelisted
        f"WHERE ts >= :t0 AND ts {op} :t1 ORDER BY ts",
        t0=t0,
        t1=t1,
    )
    return [{"ts": r["ts"].astimezone(UTC), "value": r["value"]} for r in data]


class WellnessDay(Model):
    day: date
    steps: int | None
    step_goal: int | None
    distance_m: float | None
    floors_up: float | None
    floors_down: float | None
    floors_goal: float | None
    total_kcal: float | None
    active_kcal: float | None
    bmr_kcal: float | None
    resting_hr: int | None
    min_hr: int | None
    max_hr: int | None
    avg_stress: int | None
    max_stress: int | None
    stress_rest_s: int | None
    stress_low_s: int | None
    stress_medium_s: int | None
    stress_high_s: int | None
    body_battery_high: int | None
    body_battery_low: int | None
    body_battery_charged: int | None
    body_battery_drained: int | None
    body_battery_at_wake: int | None
    moderate_intensity_min: int | None
    vigorous_intensity_min: int | None
    intensity_goal_min: int | None
    avg_spo2: float | None
    lowest_spo2: float | None
    avg_waking_respiration: float | None
    hydration_ml: float | None
    hydration_goal_ml: float | None
    sedentary_s: int | None
    active_s: int | None
    highly_active_s: int | None
    sleeping_s: int | None
    hrv_last_night_avg_ms: float | None
    hrv_weekly_avg_ms: float | None
    hrv_baseline_balanced_low_ms: float | None
    hrv_baseline_balanced_upper_ms: float | None
    hrv_status: str | None
    readiness_score: int | None
    readiness_level: str | None


class WellnessPoint(Model):
    ts: datetime
    value: float | None


class WellnessStepsInterval(Model):
    start: datetime
    end: datetime
    steps: int
    activity_level: str | None


class WellnessActivity(Model):
    activity_id: int
    name: str | None
    sport_group: str
    start: datetime
    end: datetime


class WellnessSleepWindow(Model):
    start: datetime
    end: datetime


class WellnessIntraday(Model):
    """One local day [00:00, 24:00) in the athlete's time zone; timestamps in UTC."""

    day: date
    time_zone: str
    hr: list[WellnessPoint]
    stress: list[WellnessPoint]
    body_battery: list[WellnessPoint]
    respiration: list[WellnessPoint]
    spo2: list[WellnessPoint]
    steps: list[WellnessStepsInterval]
    activities: list[WellnessActivity]
    sleep: WellnessSleepWindow | None


class WellnessHeatmap(Model):
    """``values[i][h]``: mean (steps: sum) of ``days[i]`` in local hour ``h``."""

    metric: str
    hours: list[int]
    days: list[date]
    values: list[list[float | None]]


class WellnessReadiness(Model):
    day: date
    score: int | None
    level: str | None
    sleep_score_factor: int | None
    recovery_time_min: int | None
    recovery_factor: int | None
    acwr_factor: int | None
    hrv_factor: int | None
    stress_history_factor: int | None
    sleep_history_factor: int | None
    feedback: str | None


@router.get("/daily", response_model=list[WellnessDay])
def daily(session: SessionDep, rng: RangeDep) -> list[WellnessDay]:
    data = rows(
        session,
        """
        SELECT d.*,
               h.last_night_avg_ms AS hrv_last_night_avg_ms,
               h.weekly_avg_ms AS hrv_weekly_avg_ms,
               h.baseline_balanced_low_ms AS hrv_baseline_balanced_low_ms,
               h.baseline_balanced_upper_ms AS hrv_baseline_balanced_upper_ms,
               h.status AS hrv_status,
               r.score AS readiness_score,
               r.level AS readiness_level
        FROM garmin.daily_summary d
        LEFT JOIN garmin.hrv_daily h ON h.day = d.day
        LEFT JOIN garmin.training_readiness r ON r.day = d.day
        WHERE d.day BETWEEN :start AND :end
        ORDER BY d.day
        """,
        **rng.params(),
    )
    return [WellnessDay(**r) for r in data]


@router.get("/intraday", response_model=WellnessIntraday)
def intraday(
    session: SessionDep,
    clock: ClockDep,
    day: Annotated[
        date | None, Query(description="Local day (default: last day with data)")
    ] = None,
) -> WellnessIntraday:
    if day is None:
        day = data_bounds(session)[1] or clock.today()
    t0, t1 = clock.day_span(day, day)
    points = {
        key: [WellnessPoint(**p) for p in series_rows(session, key, t0, t1)] for key in SERIES
    }
    steps = rows(
        session,
        "SELECT start_utc, end_utc, steps, activity_level FROM garmin.steps_interval "
        "WHERE start_utc >= :t0 AND start_utc < :t1 ORDER BY start_utc",
        t0=t0,
        t1=t1,
    )
    activities = rows(
        session,
        """
        SELECT activity_id, name, sport_group, start_time_utc AS start,
               start_time_utc + make_interval(secs => coalesce(elapsed_s, duration_s, 0)) AS "end"
        FROM garmin.activity
        WHERE start_time_utc < :t1
          AND start_time_utc + make_interval(secs => coalesce(elapsed_s, duration_s, 0)) > :t0
        ORDER BY start_time_utc
        """,
        t0=t0,
        t1=t1,
    )
    sleep = one(
        session,
        "SELECT start_utc, end_utc FROM garmin.sleep WHERE day = :day "
        "AND start_utc IS NOT NULL AND end_utc IS NOT NULL",
        day=day,
    )
    return WellnessIntraday(
        day=day,
        time_zone=clock.name,
        hr=points["hr"],
        stress=points["stress"],
        body_battery=points["body_battery"],
        respiration=points["respiration"],
        spo2=points["spo2"],
        steps=[
            WellnessStepsInterval(
                start=s["start_utc"].astimezone(UTC),
                end=s["end_utc"].astimezone(UTC),
                steps=s["steps"],
                activity_level=s["activity_level"],
            )
            for s in steps
        ],
        activities=[
            WellnessActivity(
                activity_id=a["activity_id"],
                name=a["name"],
                sport_group=a["sport_group"],
                start=a["start"].astimezone(UTC),
                end=a["end"].astimezone(UTC),
            )
            for a in activities
        ],
        sleep=WellnessSleepWindow(
            start=sleep["start_utc"].astimezone(UTC), end=sleep["end_utc"].astimezone(UTC)
        )
        if sleep
        else None,
    )


@router.get("/heatmap", response_model=WellnessHeatmap)
def heatmap(
    session: SessionDep,
    clock: ClockDep,
    rng: RangeDep,
    metric: Annotated[HeatmapMetric, Query()] = "hr",
) -> WellnessHeatmap:
    """Days from the first to the last day with data in the range (gaps inside are kept)."""
    table, ts_col, value, cond, mean = HEATMAP[metric]
    t0, t1 = clock.day_span(rng.start, rng.end)
    final = "sum(s) / nullif(sum(n), 0)" if mean else "sum(s)"
    data = rows(
        session,
        HEATMAP_SQL.format(ts=ts_col, value=value, cond=cond, table=table, final=final),
        tz=clock.name,
        t0=t0,
        t1=t1,
    )
    cells: dict[date, list[float | None]] = {}
    for r in data:
        h: datetime = r["h"]
        row = cells.setdefault(h.date(), [None] * 24)
        row[h.hour] = None if r["v"] is None else round(r["v"], 1)
    days: list[date] = []
    if cells:
        first, last = min(cells), max(cells)
        days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    return WellnessHeatmap(
        metric=metric,
        hours=list(range(24)),
        days=days,
        values=[cells.get(d, [None] * 24) for d in days],
    )


@router.get("/readiness", response_model=list[WellnessReadiness])
def readiness(session: SessionDep, rng: RangeDep) -> list[WellnessReadiness]:
    data = rows(
        session,
        "SELECT * FROM garmin.training_readiness WHERE day BETWEEN :start AND :end ORDER BY day",
        **rng.params(),
    )
    return [WellnessReadiness(**r) for r in data]
