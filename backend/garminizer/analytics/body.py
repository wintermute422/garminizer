"""Body composition series: trailing weight trend and the change over about 30 days."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

TREND_DAYS = 7
CHANGE_DAYS = 30
CHANGE_TOLERANCE_DAYS = 7


@dataclass(frozen=True)
class TrendPoint:
    """Trailing 7-day mean over the days that have weigh-ins (daily means first)."""

    day: date
    weight_kg: float | None
    body_fat_pct: float | None


class _HasWeight(Protocol):
    @property
    def day(self) -> date: ...

    @property
    def weight_kg(self) -> float | None: ...


def _avg(values: list[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return round(sum(present) / len(present), 2) if present else None


def weight_trend(daily: Sequence[Mapping[str, Any]]) -> list[TrendPoint]:
    """One point per weigh-in day: mean of the daily means within the trailing 7 days."""
    out: list[TrendPoint] = []
    lo = 0
    for hi, cur in enumerate(daily):
        while daily[lo]["day"] <= cur["day"] - timedelta(days=TREND_DAYS):
            lo += 1
        window = daily[lo : hi + 1]
        out.append(
            TrendPoint(
                day=cur["day"],
                weight_kg=_avg([w["weight_kg"] for w in window]),
                body_fat_pct=_avg([w["body_fat_pct"] for w in window]),
            )
        )
    return out


def change_30d(points: Sequence[_HasWeight]) -> float | None:
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
