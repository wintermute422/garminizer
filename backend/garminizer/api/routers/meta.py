"""System health and app metadata."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select, text

from garminizer import __version__
from garminizer.api.deps import SessionDep, data_bounds, rows
from garminizer.api.schemas import AthleteOut, Meta, SportCount, SystemHealth
from garminizer.models import Athlete

router = APIRouter(prefix="/api", tags=["meta"])


@router.get("/health", response_model=SystemHealth)
def health(session: SessionDep) -> SystemHealth:
    try:
        session.execute(text("SELECT 1"))
        ok = True
    except Exception:
        ok = False
    return SystemHealth(status="ok" if ok else "degraded", version=__version__, database=ok)


@router.get("/meta", response_model=Meta)
def meta(session: SessionDep, request: Request) -> Meta:
    athlete = session.scalar(select(Athlete))
    first, last = data_bounds(session)
    sports = rows(
        session,
        "SELECT sport_group, count(*) AS activities FROM garmin.activity "
        "GROUP BY 1 ORDER BY 2 DESC",
    )
    last_sync = session.execute(
        text("SELECT max(finished_at) FROM garmin.sync_run WHERE status = 'ok'")
    ).scalar()
    settings = request.app.state.settings
    return Meta(
        version=__version__,
        athlete=AthleteOut.model_validate(athlete) if athlete else None,
        first_day=first,
        last_day=last,
        activity_count=sum(s["activities"] for s in sports),
        sports=[SportCount(**s) for s in sports],
        last_sync_at=last_sync,
        map_style_url=settings.map_style_url,
        map_style_url_dark=settings.map_style_url_dark,
    )
