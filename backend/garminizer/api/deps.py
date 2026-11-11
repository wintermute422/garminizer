"""Request dependencies: DB session, athlete clock, date range and sport filters, query helpers."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Query, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from garminizer.athlete import AthleteClock, athlete_clock
from garminizer.sports import SPORT_GROUPS


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_session)]


def get_clock(request: Request, session: SessionDep) -> AthleteClock:
    """The athlete's time zone (stored by Garmin, else the configured TZ) and "now"."""
    return athlete_clock(session, request.app.state.settings.tz)


ClockDep = Annotated[AthleteClock, Depends(get_clock)]


def rows(session: Session, sql: str, **params: Any) -> list[dict[str, Any]]:
    """Run a read-only SQL statement and return plain dicts."""
    return [dict(r._mapping) for r in session.execute(text(sql), params)]


def one(session: Session, sql: str, **params: Any) -> dict[str, Any] | None:
    result = rows(session, sql, **params)
    return result[0] if result else None


def data_bounds(session: Session) -> tuple[date | None, date | None]:
    """First and last day that has any data (activities or daily summaries)."""
    r = one(
        session,
        """
        SELECT least(
                 (SELECT min(day) FROM garmin.daily_summary),
                 (SELECT min(start_time_local)::date FROM garmin.activity)) AS first,
               greatest(
                 (SELECT max(day) FROM garmin.daily_summary),
                 (SELECT max(start_time_local)::date FROM garmin.activity)) AS last
        """,
    )
    return (r["first"], r["last"]) if r else (None, None)


@dataclass(frozen=True)
class DateRange:
    start: date
    end: date

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def params(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "end_excl": self.end + timedelta(days=1)}


def date_range(
    session: SessionDep,
    clock: ClockDep,
    start: Annotated[
        date | None, Query(description="First day (default: 1 year before end)")
    ] = None,
    end: Annotated[date | None, Query(description="Last day (default: last day with data)")] = None,
) -> DateRange:
    if end is None:
        end = data_bounds(session)[1] or clock.today()
    if start is None:
        start = end - timedelta(days=364)
    if start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")
    return DateRange(start, end)


RangeDep = Annotated[DateRange, Depends(date_range)]


def sport_filter(
    sport: Annotated[
        str | None, Query(description=f"Sport group: one of {', '.join(SPORT_GROUPS)}")
    ] = None,
) -> str | None:
    if sport is not None and sport not in SPORT_GROUPS:
        raise HTTPException(status_code=422, detail=f"unknown sport group {sport!r}")
    return sport


SportDep = Annotated[str | None, Depends(sport_filter)]
