"""Body: weigh-ins with a 7-day trend, blood pressure, latest values and 30-day change.

Measurements are timestamps; the range filter and the trend use the athlete's local day.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, date, datetime

from fastapi import APIRouter
from pydantic import Field

from garminizer.analytics.body import change_30d, weight_trend
from garminizer.api.deps import ClockDep, RangeDep, SessionDep, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/body", tags=["body"])


class BodyWeighIn(Model):
    measured_at: datetime
    weight_kg: float
    bmi: float | None
    body_fat_pct: float | None
    body_water_pct: float | None
    muscle_mass_kg: float | None
    bone_mass_kg: float | None
    visceral_fat: float | None
    metabolic_age: float | None
    source: str | None


class BodyTrendPoint(Model):
    """Trailing 7-day mean over the days that have weigh-ins (daily means first)."""

    day: date
    weight_kg: float | None
    body_fat_pct: float | None


class BodyBloodPressure(Model):
    measured_at: datetime
    systolic: int
    diastolic: int
    pulse: int | None
    category: str | None


class BodyLatest(Model):
    weight_kg: float
    bmi: float | None
    body_fat_pct: float | None
    muscle_mass_kg: float | None
    measured_at: datetime


class BodyOverview(Model):
    weigh_ins: list[BodyWeighIn]
    trend: list[BodyTrendPoint]
    blood_pressure: list[BodyBloodPressure]
    latest: BodyLatest | None = Field(description="Last weigh-in on or before the range end")
    change_30d_kg: float | None = Field(
        description="Latest trend weight minus the trend about 30 days earlier"
    )
    goal: float | None = Field(default=None, description="Goal weight (kg); not available yet")


@router.get("", response_model=BodyOverview)
def body(session: SessionDep, clock: ClockDep, rng: RangeDep) -> BodyOverview:
    t0, t1 = clock.day_span(rng.start, rng.end)
    weigh_ins = rows(
        session,
        "SELECT * FROM garmin.body_composition WHERE measured_at >= :t0 AND measured_at < :t1 "
        "ORDER BY measured_at",
        t0=t0,
        t1=t1,
    )
    pressure = rows(
        session,
        "SELECT * FROM garmin.blood_pressure WHERE measured_at >= :t0 AND measured_at < :t1 "
        "ORDER BY measured_at",
        t0=t0,
        t1=t1,
    )
    # Daily means up to the range end; earlier days feed the trailing window and the change.
    daily = rows(
        session,
        """
        SELECT (measured_at AT TIME ZONE :tz)::date AS day,
               avg(weight_kg)::float8 AS weight_kg, avg(body_fat_pct)::float8 AS body_fat_pct
        FROM garmin.body_composition WHERE measured_at < :t1
        GROUP BY 1 ORDER BY 1
        """,
        tz=clock.name,
        t1=t1,
    )
    full = [BodyTrendPoint(**asdict(p)) for p in weight_trend(daily)]
    last = rows(
        session,
        "SELECT weight_kg, bmi, body_fat_pct, muscle_mass_kg, measured_at "
        "FROM garmin.body_composition WHERE measured_at < :t1 ORDER BY measured_at DESC LIMIT 1",
        t1=t1,
    )
    for r in (*weigh_ins, *pressure, *last):
        r["measured_at"] = r["measured_at"].astimezone(UTC)
    return BodyOverview(
        weigh_ins=[BodyWeighIn(**r) for r in weigh_ins],
        trend=[p for p in full if p.day >= rng.start],
        blood_pressure=[BodyBloodPressure(**r) for r in pressure],
        latest=BodyLatest(**last[0]) if last else None,
        change_30d_kg=change_30d(full),
    )
