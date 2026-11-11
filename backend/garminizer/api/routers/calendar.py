"""Calendar: active days with totals, streaks, active weeks and a weekday x hour punchcard.

Days and hours come from the activity's local start time; time is moving time (elapsed when an
activity has none), as everywhere else.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter
from pydantic import Field

from garminizer.analytics.stats import streaks
from garminizer.api.deps import RangeDep, SessionDep, SportDep, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/calendar", tags=["calendar"])

ONE_WEEK = timedelta(days=7)


class CalendarDay(Model):
    day: date
    activities: int
    duration_s: float = Field(description="Moving time (elapsed when an activity has none)")
    distance_m: float
    training_load: float
    sport_groups: list[str]


class CalendarStreak(Model):
    current: int
    longest: int
    longest_start: date | None


class CalendarTotals(Model):
    active_days: int
    activities: int


class CalendarOverview(Model):
    """Only days with activities are listed; streaks count consecutive active days."""

    days: list[CalendarDay]
    streak: CalendarStreak
    active_weeks_in_row: int
    totals: CalendarTotals


class CalendarPunchcardCell(Model):
    weekday: int
    hour: int
    activities: int
    duration_s: float = Field(description="Moving time (elapsed when an activity has none)")


def weeks_in_row(days: list[date], end: date) -> int:
    """Consecutive ISO weeks with an activity, ending with the week of ``end``.

    Like the day streak, a still-empty current week does not break the run.
    """
    weeks = {d - timedelta(days=d.weekday()) for d in days}
    ref = end - timedelta(days=end.weekday())
    if ref not in weeks:
        ref -= ONE_WEEK
    count = 0
    while ref in weeks:
        count += 1
        ref -= ONE_WEEK
    return count


@router.get("", response_model=CalendarOverview)
def calendar(session: SessionDep, rng: RangeDep, sport: SportDep) -> CalendarOverview:
    params = rng.params()
    sport_sql = ""
    if sport:
        sport_sql = " AND sport_group = :sport"
        params["sport"] = sport
    data = rows(
        session,
        f"""
        SELECT start_time_local::date AS day, count(*) AS activities,
               coalesce(sum(coalesce(moving_s, duration_s)), 0)::float8 AS duration_s,
               coalesce(sum(distance_m), 0)::float8 AS distance_m,
               coalesce(sum(training_load), 0)::float8 AS training_load,
               array_agg(DISTINCT sport_group ORDER BY sport_group) AS sport_groups
        FROM garmin.activity
        WHERE start_time_local >= :start AND start_time_local < :end_excl{sport_sql}
        GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 - fixed fragment
        **params,
    )
    days = [CalendarDay(**r) for r in data]
    active = [d.day for d in days]
    current, longest, longest_start = streaks(active, today=rng.end)
    return CalendarOverview(
        days=days,
        streak=CalendarStreak(current=current, longest=longest, longest_start=longest_start),
        active_weeks_in_row=weeks_in_row(active, rng.end),
        totals=CalendarTotals(active_days=len(days), activities=sum(d.activities for d in days)),
    )


@router.get("/punchcard", response_model=list[CalendarPunchcardCell])
def punchcard(session: SessionDep, rng: RangeDep, sport: SportDep) -> list[CalendarPunchcardCell]:
    """Non-empty cells only; weekday 0 = Monday, hour of the local start time."""
    where = "start_time_local >= :start AND start_time_local < :end_excl"
    params = rng.params()
    if sport:
        where += " AND sport_group = :sport"
        params["sport"] = sport
    data = rows(
        session,
        f"""
        SELECT extract(isodow FROM start_time_local)::int - 1 AS weekday,
               extract(hour FROM start_time_local)::int AS hour,
               count(*) AS activities,
               coalesce(sum(coalesce(moving_s, duration_s)), 0)::float8 AS duration_s
        FROM garmin.activity WHERE {where}
        GROUP BY 1, 2 ORDER BY 1, 2
        """,  # noqa: S608 - fixed fragments
        **params,
    )
    return [CalendarPunchcardCell(**r) for r in data]
