"""Sleep: nightly list with local bed/wake times, one night in detail, range statistics.

A night is keyed by its wake-up day. ``bedtime_min`` / ``waketime_min`` count minutes after local
noon of the previous day (23:30 bed = 690, 07:00 wake = 1140), so they stay continuous across
midnight for consistency charts.
"""

from __future__ import annotations

import statistics
from datetime import UTC, date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session

from garminizer.api.deps import ClockDep, RangeDep, SessionDep, rows
from garminizer.api.routers.wellness import as_utc, series_rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/sleep", tags=["sleep"])

NIGHT_SQL = """
    SELECT s.*,
           s.start_utc AT TIME ZONE :tz AS bed_local,
           s.end_utc AT TIME ZONE :tz AS wake_local,
           (extract(epoch FROM (s.start_utc AT TIME ZONE :tz) - ((s.day - 1) + time '12:00'))
              / 60)::float8 AS bedtime_min,
           (extract(epoch FROM (s.end_utc AT TIME ZONE :tz) - ((s.day - 1) + time '12:00'))
              / 60)::float8 AS waketime_min,
           h.status AS hrv_status
    FROM garmin.sleep s
    LEFT JOIN garmin.hrv_daily h ON h.day = s.day
"""
QUALITY_ORDER = ("EXCELLENT", "GOOD", "FAIR", "POOR")
DETAIL_SERIES = ("hr", "spo2", "respiration", "body_battery")


class SleepNight(Model):
    day: date
    start_utc: datetime | None
    end_utc: datetime | None
    duration_s: int | None
    deep_s: int | None
    light_s: int | None
    rem_s: int | None
    awake_s: int | None
    unmeasurable_s: int | None
    score: int | None
    score_quality: str | None
    score_duration: int | None
    score_deep: int | None
    score_rem: int | None
    score_light: int | None
    score_awakenings: int | None
    score_stress: int | None
    avg_hr: float | None
    lowest_hr: int | None
    avg_respiration: float | None
    lowest_respiration: float | None
    highest_respiration: float | None
    avg_spo2: float | None
    lowest_spo2: float | None
    avg_stress: float | None
    avg_overnight_hrv: float | None
    restless_moments: int | None
    awake_count: int | None
    body_battery_change: int | None
    sleep_need_min: int | None
    feedback: str | None
    bed_local: datetime | None
    wake_local: datetime | None
    bedtime_min: float | None
    waketime_min: float | None
    hrv_status: str | None


class SleepStageInterval(Model):
    start: datetime
    end: datetime
    stage: str


class SleepPoint(Model):
    ts: datetime
    value: float | None


class SleepDetail(Model):
    night: SleepNight
    stages: list[SleepStageInterval]
    hr: list[SleepPoint]
    spo2: list[SleepPoint]
    respiration: list[SleepPoint]
    body_battery: list[SleepPoint]


class SleepGroupStats(Model):
    nights: int
    avg_duration_s: float | None
    avg_score: float | None
    avg_bedtime_min: float | None
    avg_waketime_min: float | None


class SleepQualityCount(Model):
    quality: str
    nights: int


class SleepStats(Model):
    """Weekend = nights ending on Saturday or Sunday."""

    nights: int
    avg_duration_s: float | None
    avg_score: float | None
    avg_deep_s: float | None
    avg_rem_s: float | None
    avg_light_s: float | None
    avg_awake_s: float | None
    weekday: SleepGroupStats
    weekend: SleepGroupStats
    bedtime_sd_min: float | None
    waketime_sd_min: float | None
    sleep_debt_7d_s: float | None
    score_distribution: list[SleepQualityCount]


def _nights(session: Session, tz: str, where: str, **params: Any) -> list[SleepNight]:
    data = rows(
        session,
        f"{NIGHT_SQL} WHERE {where} ORDER BY s.day",
        tz=tz,
        **params,
    )
    for r in data:
        r["start_utc"], r["end_utc"] = as_utc(r["start_utc"]), as_utc(r["end_utc"])
    return [SleepNight(**r) for r in data]


def _mean(values: list[Any]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return round(statistics.fmean(present), 1) if present else None


def _sd(values: list[Any]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return round(statistics.stdev(present), 1) if len(present) >= 2 else None


def _group(nights: list[SleepNight]) -> SleepGroupStats:
    return SleepGroupStats(
        nights=len(nights),
        avg_duration_s=_mean([n.duration_s for n in nights]),
        avg_score=_mean([n.score for n in nights]),
        avg_bedtime_min=_mean([n.bedtime_min for n in nights]),
        avg_waketime_min=_mean([n.waketime_min for n in nights]),
    )


@router.get("", response_model=list[SleepNight])
def list_nights(session: SessionDep, clock: ClockDep, rng: RangeDep) -> list[SleepNight]:
    return _nights(
        session, clock.name, "s.day BETWEEN :start AND :end", start=rng.start, end=rng.end
    )


@router.get("/stats", response_model=SleepStats)
def sleep_stats(session: SessionDep, clock: ClockDep, rng: RangeDep) -> SleepStats:
    nights = _nights(
        session, clock.name, "s.day BETWEEN :start AND :end", start=rng.start, end=rng.end
    )
    debts = [
        max(0, n.sleep_need_min * 60 - n.duration_s)
        for n in nights[-7:]
        if n.sleep_need_min is not None and n.duration_s is not None
    ]
    counts: dict[str, int] = {}
    for n in nights:
        if n.score_quality:
            counts[n.score_quality] = counts.get(n.score_quality, 0) + 1
    order = [q for q in QUALITY_ORDER if q in counts] + sorted(set(counts) - set(QUALITY_ORDER))
    return SleepStats(
        nights=len(nights),
        avg_duration_s=_mean([n.duration_s for n in nights]),
        avg_score=_mean([n.score for n in nights]),
        avg_deep_s=_mean([n.deep_s for n in nights]),
        avg_rem_s=_mean([n.rem_s for n in nights]),
        avg_light_s=_mean([n.light_s for n in nights]),
        avg_awake_s=_mean([n.awake_s for n in nights]),
        weekday=_group([n for n in nights if n.day.weekday() < 5]),
        weekend=_group([n for n in nights if n.day.weekday() >= 5]),
        bedtime_sd_min=_sd([n.bedtime_min for n in nights]),
        waketime_sd_min=_sd([n.waketime_min for n in nights]),
        sleep_debt_7d_s=float(sum(debts)) if debts else None,
        score_distribution=[SleepQualityCount(quality=q, nights=counts[q]) for q in order],
    )


@router.get("/{day}", response_model=SleepDetail)
def night_detail(day: date, session: SessionDep, clock: ClockDep) -> SleepDetail:
    found = _nights(session, clock.name, "s.day = :day", day=day)
    if not found:
        raise HTTPException(status_code=404, detail="no sleep recorded for this day")
    night = found[0]
    stages = rows(
        session,
        "SELECT start_utc, end_utc, stage FROM garmin.sleep_stage WHERE day = :day "
        "ORDER BY start_utc",
        day=day,
    )
    series: dict[str, list[SleepPoint]] = {key: [] for key in DETAIL_SERIES}
    if night.start_utc is not None and night.end_utc is not None:
        series = {
            key: [
                SleepPoint(**p)
                for p in series_rows(session, key, night.start_utc, night.end_utc, include_end=True)
            ]
            for key in DETAIL_SERIES
        }
    return SleepDetail(
        night=night,
        stages=[
            SleepStageInterval(
                start=s["start_utc"].astimezone(UTC),
                end=s["end_utc"].astimezone(UTC),
                stage=s["stage"],
            )
            for s in stages
        ],
        hr=series["hr"],
        spo2=series["spo2"],
        respiration=series["respiration"],
        body_battery=series["body_battery"],
    )
