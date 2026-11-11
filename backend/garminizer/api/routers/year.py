"""Year in review: totals, sports, highlights, months, streaks, best efforts and health.

Activity time is moving time everywhere (elapsed time when an activity has none), so the
totals, sports, months and days add up to the same figure.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Path
from pydantic import AfterValidator, Field
from sqlalchemy.orm import Session

from garminizer.analytics.pipeline import TILE_ZOOM
from garminizer.analytics.stats import streaks
from garminizer.api.activity_sql import SUMMARY_COLUMNS, moving_time
from garminizer.api.deps import SessionDep, one, rows
from garminizer.api.schemas import ActivitySummary, Model

router = APIRouter(prefix="/api/year", tags=["year"])

# Floats rounded to 0.1 (sums of REAL/DOUBLE columns carry binary noise).
R1 = Annotated[float, AfterValidator(lambda v: round(v, 1))]

HIGHLIGHTS = {
    "longest_distance": "a.distance_m",
    "longest_duration": "a.duration_s",
    "most_elevation": "a.elevation_gain_m",
    "hardest_load": "a.training_load",
}
YEAR_WHERE = "a.start_time_local >= :y0 AND a.start_time_local < :y1"


class YearSummary(Model):
    year: int
    activities: int
    distance_m: R1
    duration_s: R1


class YearTotals(Model):
    activities: int
    distance_m: R1
    duration_s: R1
    moving_s: R1
    elevation_gain_m: R1
    calories: R1
    training_load: R1
    active_days: int


class YearSport(Model):
    sport_group: str
    activities: int
    distance_m: R1
    duration_s: R1 = Field(description="Moving time (elapsed time when an activity has none)")
    elevation_gain_m: R1


class YearHighlights(Model):
    longest_distance: ActivitySummary | None
    longest_duration: ActivitySummary | None
    most_elevation: ActivitySummary | None
    hardest_load: ActivitySummary | None


class YearMonth(Model):
    month: int  # 1-12
    activities: int
    distance_m: R1
    duration_s: R1 = Field(description="Moving time (elapsed time when an activity has none)")


class YearBestMonth(Model):
    month: int
    distance_m: R1


class YearBestEffort(Model):
    distance_m: float  # standard distance, exact (e.g. 1609.344)
    seconds: R1
    activity_id: int
    day: date


class YearSleep(Model):
    avg_duration_s: R1 | None
    avg_score: R1 | None


class YearSteps(Model):
    total: int | None
    avg: R1 | None


class YearVo2max(Model):
    first: R1 | None
    last: R1 | None


class YearRestingHr(Model):
    """Averages over the first and the last 30 days with data in the year."""

    first_30d_avg: R1 | None
    last_30d_avg: R1 | None


class YearDay(Model):
    day: date
    duration_s: R1 = Field(description="Moving time (elapsed time when an activity has none)")
    training_load: R1


class YearReview(Model):
    year: int
    totals: YearTotals
    by_sport: list[YearSport]
    highlights: YearHighlights
    monthly: list[YearMonth]
    best_month: YearBestMonth | None
    longest_streak: int
    best_efforts: list[YearBestEffort]
    sleep: YearSleep
    steps: YearSteps
    vo2max: YearVo2max
    resting_hr: YearRestingHr
    new_tiles: int
    days: list[YearDay]


@router.get("", response_model=list[YearSummary])
def years(session: SessionDep) -> list[YearSummary]:
    """Every year with data (activities or daily summaries), newest first."""
    data = rows(
        session,
        f"""
        WITH years AS (
            SELECT DISTINCT extract(year FROM day)::int AS year FROM garmin.daily_summary
            UNION
            SELECT DISTINCT extract(year FROM start_time_local)::int FROM garmin.activity
        )
        SELECT y.year, count(a.activity_id) AS activities,
               coalesce(sum(a.distance_m), 0) AS distance_m,
               coalesce(sum({moving_time()}), 0) AS duration_s
        FROM years y
        LEFT JOIN garmin.activity a
          ON a.start_time_local >= make_date(y.year, 1, 1)
         AND a.start_time_local < make_date(y.year + 1, 1, 1)
        GROUP BY y.year ORDER BY y.year DESC
        """,  # noqa: S608 - constant SQL fragment
    )
    return [YearSummary(**r) for r in data]


def _highlights(session: Session, p: dict[str, Any]) -> YearHighlights:
    found: dict[str, ActivitySummary | None] = {}
    for key, col in HIGHLIGHTS.items():
        r = one(
            session,
            f"""
            SELECT {SUMMARY_COLUMNS} FROM garmin.activity a
            WHERE {YEAR_WHERE} AND {col} > 0
            ORDER BY {col} DESC, a.start_time_utc LIMIT 1
            """,  # noqa: S608 - constant columns
            **p,
        )
        found[key] = ActivitySummary(**r) if r else None
    return YearHighlights(**found)


def _monthly(session: Session, p: dict[str, Any]) -> list[YearMonth]:
    data = rows(
        session,
        f"""
        SELECT extract(month FROM a.start_time_local)::int AS month, count(*) AS activities,
               coalesce(sum(a.distance_m), 0) AS distance_m,
               coalesce(sum({moving_time()}), 0) AS duration_s
        FROM garmin.activity a WHERE {YEAR_WHERE} GROUP BY 1
        """,  # noqa: S608 - constant WHERE
        **p,
    )
    by_month = {r["month"]: r for r in data}
    return [
        YearMonth(**by_month[m])
        if m in by_month
        else YearMonth(month=m, activities=0, distance_m=0.0, duration_s=0.0)
        for m in range(1, 13)
    ]


def _health(session: Session, p: dict[str, Any]) -> dict[str, Any]:
    """Sleep, steps, VO2max and resting HR of the year (daily tables, keyed by day)."""
    r = one(
        session,
        """
        WITH rhr AS (
            SELECT day, resting_hr FROM garmin.daily_summary
            WHERE day >= :y0 AND day < :y1 AND resting_hr IS NOT NULL
        ), vo2 AS (
            SELECT day, vo2max_running FROM garmin.max_metric
            WHERE day >= :y0 AND day < :y1 AND vo2max_running IS NOT NULL
        )
        SELECT
          (SELECT avg(duration_s)::float8 FROM garmin.sleep
           WHERE day >= :y0 AND day < :y1) AS avg_duration_s,
          (SELECT avg(score)::float8 FROM garmin.sleep WHERE day >= :y0 AND day < :y1) AS avg_score,
          (SELECT sum(steps) FROM garmin.daily_summary
           WHERE day >= :y0 AND day < :y1) AS steps_total,
          (SELECT avg(steps)::float8 FROM garmin.daily_summary
           WHERE day >= :y0 AND day < :y1) AS steps_avg,
          (SELECT vo2max_running FROM vo2 ORDER BY day LIMIT 1) AS vo2_first,
          (SELECT vo2max_running FROM vo2 ORDER BY day DESC LIMIT 1) AS vo2_last,
          (SELECT avg(resting_hr)::float8 FROM rhr
           WHERE day < (SELECT min(day) FROM rhr) + 30) AS rhr_first,
          (SELECT avg(resting_hr)::float8 FROM rhr
           WHERE day > (SELECT max(day) FROM rhr) - 30) AS rhr_last,
          EXISTS (SELECT 1 FROM garmin.daily_summary WHERE day >= :y0 AND day < :y1) AS has_daily
        """,
        **p,
    )
    return r or {}


@router.get("/{year}", response_model=YearReview)
def year_review(session: SessionDep, year: Annotated[int, Path(ge=1900, le=2200)]) -> YearReview:
    p: dict[str, Any] = {"y0": date(year, 1, 1), "y1": date(year + 1, 1, 1)}
    totals = one(
        session,
        f"""
        SELECT count(*) AS activities, coalesce(sum(a.distance_m), 0) AS distance_m,
               coalesce(sum(a.duration_s), 0) AS duration_s,
               coalesce(sum({moving_time()}), 0) AS moving_s,
               coalesce(sum(a.elevation_gain_m), 0)::float8 AS elevation_gain_m,
               coalesce(sum(a.calories), 0)::float8 AS calories,
               coalesce(sum(a.training_load), 0)::float8 AS training_load,
               count(DISTINCT a.start_time_local::date) AS active_days
        FROM garmin.activity a WHERE {YEAR_WHERE}
        """,  # noqa: S608 - constant WHERE
        **p,
    )
    health = _health(session, p)
    if not totals or (totals["activities"] == 0 and not health.get("has_daily")):
        raise HTTPException(status_code=404, detail=f"no data in {year}")
    by_sport = rows(
        session,
        f"""
        SELECT a.sport_group, count(*) AS activities,
               coalesce(sum(a.distance_m), 0) AS distance_m,
               coalesce(sum({moving_time()}), 0) AS duration_s,
               coalesce(sum(a.elevation_gain_m), 0)::float8 AS elevation_gain_m
        FROM garmin.activity a WHERE {YEAR_WHERE}
        GROUP BY 1 ORDER BY count(*) DESC, 1
        """,  # noqa: S608 - constant WHERE
        **p,
    )
    days = rows(
        session,
        f"""
        SELECT a.start_time_local::date AS day,
               coalesce(sum({moving_time()}), 0) AS duration_s,
               coalesce(sum(a.training_load), 0)::float8 AS training_load
        FROM garmin.activity a WHERE {YEAR_WHERE} GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 - constant WHERE
        **p,
    )
    efforts = rows(
        session,
        f"""
        SELECT DISTINCT ON (b.distance_m) b.distance_m, b.seconds, b.activity_id,
               a.start_time_local::date AS day
        FROM garmin.activity_best_distance b JOIN garmin.activity a USING (activity_id)
        WHERE {YEAR_WHERE}
        ORDER BY b.distance_m, b.seconds, a.start_time_utc
        """,  # noqa: S608 - constant WHERE
        **p,
    )
    tiles = one(
        session,
        """
        SELECT count(*) AS n FROM (
            SELECT min(a.start_time_local) AS first_visit
            FROM garmin.activity_tile t JOIN garmin.activity a USING (activity_id)
            WHERE t.zoom = :zoom GROUP BY t.x, t.y
        ) s WHERE first_visit >= :y0 AND first_visit < :y1
        """,
        zoom=TILE_ZOOM,
        **p,
    )
    monthly = _monthly(session, p)
    best = max(monthly, key=lambda m: m.distance_m)
    _, longest, _ = streaks([d["day"] for d in days], today=date(year, 12, 31))
    return YearReview(
        year=year,
        totals=YearTotals(**totals),
        by_sport=[YearSport(**r) for r in by_sport],
        highlights=_highlights(session, p),
        monthly=monthly,
        best_month=YearBestMonth(month=best.month, distance_m=best.distance_m)
        if best.distance_m > 0
        else None,
        longest_streak=longest,
        best_efforts=[YearBestEffort(**r) for r in efforts],
        sleep=YearSleep(
            avg_duration_s=health.get("avg_duration_s"), avg_score=health.get("avg_score")
        ),
        steps=YearSteps(total=health.get("steps_total"), avg=health.get("steps_avg")),
        vo2max=YearVo2max(first=health.get("vo2_first"), last=health.get("vo2_last")),
        resting_hr=YearRestingHr(
            first_30d_avg=health.get("rhr_first"), last_30d_avg=health.get("rhr_last")
        ),
        new_tiles=tiles["n"] if tiles else 0,
        days=[YearDay(**r) for r in days],
    )
