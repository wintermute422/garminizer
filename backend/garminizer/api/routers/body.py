"""Body: weigh-ins with a 7-day trend, blood pressure, latest values and 30-day change.

Measurements are timestamps; the range filter and the trend use the athlete's local day.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter
from pydantic import Field

from garminizer.api.deps import RangeDep, SessionDep, rows
from garminizer.api.routers.wellness import athlete_tz, local_midnight
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/body", tags=["body"])

TREND_DAYS = 7
CHANGE_DAYS = 30
CHANGE_TOLERANCE_DAYS = 7


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


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def trend(daily: list[dict[str, Any]]) -> list[BodyTrendPoint]:
    """One point per weigh-in day: mean of the daily means within the trailing 7 days."""
    out: list[BodyTrendPoint] = []
    lo = 0
    for hi, cur in enumerate(daily):
        while daily[lo]["day"] <= cur["day"] - timedelta(days=TREND_DAYS):
            lo += 1
        window = daily[lo : hi + 1]
        out.append(
            BodyTrendPoint(
                day=cur["day"],
                weight_kg=_avg([w["weight_kg"] for w in window]),
                body_fat_pct=_avg([w["body_fat_pct"] for w in window]),
            )
        )
    return out


def change_30d(points: list[BodyTrendPoint]) -> float | None:
    """Last trend weight minus the trend point closest to 30 days earlier (within 7 days)."""
    weights = [(p.day, p.weight_kg) for p in points if p.weight_kg is not None]
    if not weights:
        return None
    last_day, last_kg = weights[-1]
    target = last_day - timedelta(days=CHANGE_DAYS)
    candidates = [w for w in weights if abs((w[0] - target).days) <= CHANGE_TOLERANCE_DAYS]
    if not candidates:
        return None
    _, ref_kg = min(candidates, key=lambda w: (abs((w[0] - target).days), w[0]))
    return round(last_kg - ref_kg, 2)


@router.get("", response_model=BodyOverview)
def body(session: SessionDep, rng: RangeDep) -> BodyOverview:
    tz = athlete_tz(session)
    t0 = local_midnight(rng.start, tz)
    t1 = local_midnight(rng.end + timedelta(days=1), tz)
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
        tz=tz,
        t1=t1,
    )
    full = trend(daily)
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
