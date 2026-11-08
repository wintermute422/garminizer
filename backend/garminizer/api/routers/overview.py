"""Overview: one day's snapshot (readiness, sleep, recovery, load) plus recent training."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Query
from pydantic import AfterValidator
from sqlalchemy.orm import Session

from garminizer.analytics.stats import streaks
from garminizer.api.deps import SessionDep, data_bounds, one, rows
from garminizer.api.routers.activities import SUMMARY_COLUMNS
from garminizer.api.schemas import ActivitySummary, Model

router = APIRouter(prefix="/api/overview", tags=["overview"])

INTENSITY_GOAL_MIN = 150  # WHO weekly recommendation, used when Garmin has no goal
RECENT_ACTIVITIES = 6
# Floats rounded to 0.1 (averages and sums of REAL columns carry binary noise).
R1 = Annotated[float, AfterValidator(lambda v: round(v, 1))]
ATHLETE_TZ = "coalesce((SELECT time_zone FROM garmin.athlete ORDER BY id LIMIT 1), 'UTC')"


class OverviewReadiness(Model):
    score: int | None
    level: str | None
    sleep_score_factor: int | None
    hrv_factor: int | None
    recovery_time_min: int | None
    acwr_factor: int | None


class OverviewSleep(Model):
    score: int | None
    quality: str | None
    duration_s: int | None
    deep_s: int | None
    light_s: int | None
    rem_s: int | None
    awake_s: int | None
    start_utc: datetime | None
    end_utc: datetime | None


class OverviewHrv(Model):
    last_night_avg_ms: float | None
    weekly_avg_ms: float | None
    baseline_balanced_low_ms: float | None
    baseline_balanced_upper_ms: float | None
    status: str | None


class OverviewRestingHr(Model):
    value: int | None
    avg_7d: R1 | None
    avg_30d: R1 | None


class OverviewBodyBatteryPoint(Model):
    ts: datetime
    value: int


class OverviewBodyBattery(Model):
    at_wake: int | None
    high: int | None
    low: int | None
    latest: int | None
    series: list[OverviewBodyBatteryPoint]


class OverviewStress(Model):
    avg: int | None
    max: int | None


class OverviewSteps(Model):
    value: int | None
    goal: int | None
    avg_7d: R1 | None


class OverviewIntensityMinutes(Model):
    """Moderate minutes + 2 x vigorous minutes from Monday through the day."""

    week_total: int
    goal: int


class OverviewTrainingStatus(Model):
    status: str | None
    acwr: float | None
    acwr_status: str | None
    acute_load: float | None
    chronic_load: float | None
    load_low_aerobic: float | None
    load_high_aerobic: float | None
    load_anaerobic: float | None


class OverviewFitness(Model):
    ctl: float | None
    atl: float | None
    tsb: float | None
    ctl_delta_28d: R1 | None


class OverviewVo2max(Model):
    running: float | None
    delta_30d: float | None


class OverviewRacePredictions(Model):
    time_5k_s: float | None
    time_10k_s: float | None
    time_half_s: float | None
    time_marathon_s: float | None


class OverviewSportWeek(Model):
    sport_group: str
    activities: int
    distance_m: R1 | None
    duration_s: R1 | None


class OverviewWeek(Model):
    """``this_week``: Monday through the day; ``last_week``: the full week before."""

    this_week: list[OverviewSportWeek]
    last_week: list[OverviewSportWeek]


class OverviewStreak(Model):
    current: int
    longest: int


class OverviewToday(Model):
    day: date
    readiness: OverviewReadiness | None
    sleep: OverviewSleep | None
    hrv: OverviewHrv | None
    resting_hr: OverviewRestingHr
    body_battery: OverviewBodyBattery
    stress: OverviewStress
    steps: OverviewSteps
    intensity_minutes: OverviewIntensityMinutes
    training_status: OverviewTrainingStatus | None
    fitness: OverviewFitness
    vo2max: OverviewVo2max
    race_predictions: OverviewRacePredictions | None
    week: OverviewWeek
    recent_activities: list[ActivitySummary]
    streak: OverviewStreak


def _daily(session: Session, day: date) -> dict[str, Any]:
    monday = day - timedelta(days=day.weekday())
    r = one(
        session,
        """
        SELECT d.resting_hr, d.body_battery_at_wake, d.body_battery_high, d.body_battery_low,
               d.avg_stress, d.max_stress, d.steps, d.step_goal, d.intensity_goal_min,
               (SELECT avg(resting_hr)::float8 FROM garmin.daily_summary
                WHERE day BETWEEN :d7 AND :day) AS rhr_7d,
               (SELECT avg(resting_hr)::float8 FROM garmin.daily_summary
                WHERE day BETWEEN :d30 AND :day) AS rhr_30d,
               (SELECT avg(steps)::float8 FROM garmin.daily_summary
                WHERE day BETWEEN :d7 AND :day) AS steps_7d,
               (SELECT sum(coalesce(moderate_intensity_min, 0)
                           + 2 * coalesce(vigorous_intensity_min, 0))
                FROM garmin.daily_summary WHERE day BETWEEN :monday AND :day) AS im_week
        FROM (SELECT 1) AS x LEFT JOIN garmin.daily_summary d ON d.day = :day
        """,
        day=day,
        d7=day - timedelta(days=6),
        d30=day - timedelta(days=29),
        monday=monday,
    )
    return r or {}


def _week(session: Session, day: date) -> OverviewWeek:
    monday = day - timedelta(days=day.weekday())
    data = rows(
        session,
        """
        SELECT start_time_local >= :monday AS this_week, sport_group, count(*) AS activities,
               sum(distance_m) AS distance_m, sum(duration_s) AS duration_s
        FROM garmin.activity
        WHERE start_time_local >= :last_monday AND start_time_local < :day_excl
        GROUP BY 1, 2 ORDER BY 1, count(*) DESC, sport_group
        """,
        monday=monday,
        last_monday=monday - timedelta(days=7),
        day_excl=day + timedelta(days=1),
    )
    return OverviewWeek(
        this_week=[OverviewSportWeek(**r) for r in data if r["this_week"]],
        last_week=[OverviewSportWeek(**r) for r in data if not r["this_week"]],
    )


@router.get("", response_model=OverviewToday)
def overview(
    session: SessionDep,
    day: Annotated[
        date | None, Query(description="Day to show (default: last day with data)")
    ] = None,
) -> OverviewToday:
    if day is None:
        day = data_bounds(session)[1] or date.today()
    p = {"day": day}
    d = _daily(session, day)
    readiness = one(
        session,
        "SELECT score, level, sleep_score_factor, hrv_factor, recovery_time_min, acwr_factor "
        "FROM garmin.training_readiness WHERE day = :day",
        **p,
    )
    sleep = one(
        session,
        "SELECT score, score_quality AS quality, duration_s, deep_s, light_s, rem_s, awake_s, "
        "start_utc, end_utc FROM garmin.sleep WHERE day = :day",
        **p,
    )
    hrv = one(
        session,
        "SELECT last_night_avg_ms, weekly_avg_ms, baseline_balanced_low_ms, "
        "baseline_balanced_upper_ms, status FROM garmin.hrv_daily WHERE day = :day",
        **p,
    )
    status = one(
        session,
        "SELECT status, acwr, acwr_status, acute_load, chronic_load, load_low_aerobic, "
        "load_high_aerobic, load_anaerobic FROM garmin.training_status WHERE day = :day",
        **p,
    )
    fitness = one(
        session,
        """
        SELECT ctl, atl, tsb,
               ctl - (SELECT ctl FROM garmin.daily_load WHERE day = :d28) AS ctl_delta_28d
        FROM garmin.daily_load WHERE day = :day
        """,
        d28=day - timedelta(days=28),
        **p,
    )
    vo2 = one(
        session,
        """
        SELECT (SELECT vo2max_running FROM garmin.max_metric
                WHERE day <= :day AND vo2max_running IS NOT NULL
                ORDER BY day DESC LIMIT 1) AS running,
               (SELECT vo2max_running FROM garmin.max_metric
                WHERE day <= :d30 AND vo2max_running IS NOT NULL
                ORDER BY day DESC LIMIT 1) AS before
        """,
        d30=day - timedelta(days=30),
        **p,
    )
    race = one(
        session,
        "SELECT time_5k_s, time_10k_s, time_half_s, time_marathon_s FROM garmin.race_prediction "
        "WHERE day <= :day ORDER BY day DESC LIMIT 1",
        **p,
    )
    battery = rows(
        session,
        f"""
        SELECT ts, level AS value FROM garmin.body_battery_sample
        WHERE ts >= (CAST(:day AS timestamp) AT TIME ZONE {ATHLETE_TZ})
          AND ts < (CAST(:next_day AS timestamp) AT TIME ZONE {ATHLETE_TZ})
        ORDER BY ts
        """,  # noqa: S608 - constant SQL fragment
        next_day=day + timedelta(days=1),
        **p,
    )
    recent = rows(
        session,
        f"SELECT {SUMMARY_COLUMNS} FROM garmin.activity a "  # noqa: S608 - constant columns
        "WHERE a.start_time_local < :day_excl ORDER BY a.start_time_utc DESC LIMIT :n",
        day_excl=day + timedelta(days=1),
        n=RECENT_ACTIVITIES,
    )
    active_days = rows(
        session,
        "SELECT DISTINCT start_time_local::date AS d FROM garmin.activity "
        "WHERE start_time_local < :day_excl",
        day_excl=day + timedelta(days=1),
    )
    current, longest, _ = streaks([r["d"] for r in active_days], today=day)
    running = vo2["running"] if vo2 else None
    before = vo2["before"] if vo2 else None
    return OverviewToday(
        day=day,
        readiness=OverviewReadiness(**readiness) if readiness else None,
        sleep=OverviewSleep(**sleep) if sleep else None,
        hrv=OverviewHrv(**hrv) if hrv else None,
        resting_hr=OverviewRestingHr(
            value=d.get("resting_hr"), avg_7d=d.get("rhr_7d"), avg_30d=d.get("rhr_30d")
        ),
        body_battery=OverviewBodyBattery(
            at_wake=d.get("body_battery_at_wake"),
            high=d.get("body_battery_high"),
            low=d.get("body_battery_low"),
            latest=battery[-1]["value"] if battery else None,
            series=[OverviewBodyBatteryPoint(**r) for r in battery],
        ),
        stress=OverviewStress(avg=d.get("avg_stress"), max=d.get("max_stress")),
        steps=OverviewSteps(
            value=d.get("steps"), goal=d.get("step_goal"), avg_7d=d.get("steps_7d")
        ),
        intensity_minutes=OverviewIntensityMinutes(
            week_total=int(d.get("im_week") or 0),
            goal=int(d.get("intensity_goal_min") or INTENSITY_GOAL_MIN),
        ),
        training_status=OverviewTrainingStatus(**status) if status else None,
        fitness=OverviewFitness(**fitness)
        if fitness
        else OverviewFitness(ctl=None, atl=None, tsb=None, ctl_delta_28d=None),
        vo2max=OverviewVo2max(
            running=running,
            delta_30d=round(running - before, 2)
            if running is not None and before is not None
            else None,
        ),
        race_predictions=OverviewRacePredictions(**race) if race else None,
        week=_week(session, day),
        recent_activities=[ActivitySummary(**r) for r in recent],
        streak=OverviewStreak(current=current, longest=longest),
    )
