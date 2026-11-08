"""Gear: shoes, bikes and other equipment with usage and wear from the linked activities."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException
from pydantic import AfterValidator
from sqlalchemy.orm import Session

from garminizer.api.deps import SessionDep, rows
from garminizer.api.routers.activities import SUMMARY_COLUMNS
from garminizer.api.schemas import ActivitySummary, Model

router = APIRouter(prefix="/api/gear", tags=["gear"])

# Floats rounded to 0.1 (sums of REAL/DOUBLE columns carry binary noise).
R1 = Annotated[float, AfterValidator(lambda v: round(v, 1))]


class GearUsage(Model):
    month: date  # first day of the month
    distance_m: R1


class GearItem(Model):
    uuid: str
    gear_type: str
    display_name: str | None
    make: str | None
    model: str | None
    status: str
    date_begin: date | None
    date_end: date | None
    max_distance_m: R1 | None
    distance_m: R1  # sum over the linked activities
    activities: int
    last_used: date | None
    wear_pct: R1 | None  # distance_m / max_distance_m * 100
    usage: list[GearUsage]


class GearDetail(Model):
    """The gear item and every activity it was used in (newest first)."""

    item: GearItem
    activities: list[ActivitySummary]


def _items(session: Session, uuid: str | None = None) -> list[GearItem]:
    where = "WHERE g.uuid = :uuid" if uuid is not None else ""
    data = rows(
        session,
        f"""
        SELECT g.uuid, g.gear_type, g.display_name, g.make, g.model, g.status, g.date_begin,
               g.date_end, g.max_distance_m, coalesce(sum(a.distance_m), 0) AS distance_m,
               count(a.activity_id) AS activities, max(a.start_time_local)::date AS last_used
        FROM garmin.gear g
        LEFT JOIN garmin.activity_gear ag ON ag.gear_uuid = g.uuid
        LEFT JOIN garmin.activity a ON a.activity_id = ag.activity_id
        {where}
        GROUP BY g.uuid
        ORDER BY g.status = 'active' DESC, max(a.start_time_local) DESC NULLS LAST,
                 g.display_name, g.uuid
        """,  # noqa: S608 - constant WHERE, values are bound
        uuid=uuid,
    )
    usage = rows(
        session,
        f"""
        SELECT ag.gear_uuid, date_trunc('month', a.start_time_local)::date AS month,
               coalesce(sum(a.distance_m), 0) AS distance_m
        FROM garmin.activity_gear ag JOIN garmin.activity a USING (activity_id)
        {where.replace("g.uuid", "ag.gear_uuid")}
        GROUP BY 1, 2 ORDER BY 1, 2
        """,  # noqa: S608 - constant WHERE, values are bound
        uuid=uuid,
    )
    by_gear: dict[str, list[GearUsage]] = defaultdict(list)
    for u in usage:
        by_gear[u["gear_uuid"]].append(GearUsage(month=u["month"], distance_m=u["distance_m"]))
    items = []
    for r in data:
        limit = r["max_distance_m"]
        wear = round(r["distance_m"] / limit * 100, 1) if limit else None
        items.append(GearItem(**r, wear_pct=wear, usage=by_gear.get(r["uuid"], [])))
    return items


@router.get("", response_model=list[GearItem])
def list_gear(session: SessionDep) -> list[GearItem]:
    """All gear: active first, then most recently used."""
    return _items(session)


@router.get("/{uuid}", response_model=GearDetail)
def gear_detail(uuid: str, session: SessionDep) -> GearDetail:
    items = _items(session, uuid)
    if not items:
        raise HTTPException(status_code=404, detail="gear not found")
    activities: list[dict[str, Any]] = rows(
        session,
        f"""
        SELECT {SUMMARY_COLUMNS} FROM garmin.activity a
        JOIN garmin.activity_gear ag ON ag.activity_id = a.activity_id
        WHERE ag.gear_uuid = :uuid ORDER BY a.start_time_utc DESC
        """,  # noqa: S608 - constant columns
        uuid=uuid,
    )
    return GearDetail(item=items[0], activities=[ActivitySummary(**a) for a in activities])
