"""Weight goal maths: weighted weight trend, the target line with weekly checkpoints, body-fat
trend and regression, resting energy (BMR) and the energy balance. Pure functions, no I/O.

Rules (docs/metrics.md, "Weight goal"):
- Trend: weighted mean over calendar days, today x3, yesterday x2, the day before x1; missing
  days drop out of numerator and denominator. Only days with their own weigh-in get a trend.
- Target: a straight line falling ``rate_kg_per_week`` from the last anchor. Anchors are the
  start and checkpoints. On every checkpoint day (default Sunday) after the start, a trend
  below the target becomes the new anchor (the line restarts lower); a trend above it leaves
  the line alone. A checkpoint the user accepted as reached anchors at min(trend, target), so
  it never lifts the line.
- Body fat: time-aware exponential moving average (half-life 4 days) and a linear regression
  over the last 21 days (from 4 measurements), drawn 7 days ahead.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal

KCAL_PER_KG = 7700.0  # energy content of 1 kg body weight loss (mixed tissue, rule of thumb)
DEFAULT_TREND_WEIGHTS = (3.0, 2.0, 1.0)
SUNDAY = 6  # date.weekday(): Monday 0 .. Sunday 6
FAT_HALF_LIFE_DAYS = 4.0
REGRESSION_WINDOW_DAYS = 21
REGRESSION_MIN_POINTS = 4
REGRESSION_AHEAD_DAYS = 7
ON_PLAN_TOLERANCE_KG = 0.2  # trend up to this much above the target still counts as on plan

Sex = Literal["male", "female"]
AnchorKind = Literal["start", "reached", "accepted"]
CheckpointStatus = Literal["reached", "accepted", "missed", "no_weigh_in", "upcoming"]


# --- trend -----------------------------------------------------------------------------------


def weighted_trend(
    weights: Mapping[date, float], factors: Sequence[float] = DEFAULT_TREND_WEIGHTS
) -> dict[date, float]:
    """Trend per weigh-in day: sum(factor[k] * weight(day - k)) / sum(factors of present days)."""
    out: dict[date, float] = {}
    for day in sorted(weights):
        num = den = 0.0
        for k, factor in enumerate(factors):
            value = weights.get(day - timedelta(days=k))
            if value is not None:
                num += value * factor
                den += factor
        out[day] = num / den
    return out


# --- target line and checkpoints -------------------------------------------------------------


@dataclass(frozen=True)
class GoalPlan:
    start: date
    start_weight_kg: float
    rate_kg_per_week: float
    end: date
    checkpoint_weekday: int = SUNDAY
    accepted: frozenset[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Anchor:
    day: date
    weight_kg: float
    kind: AnchorKind


@dataclass(frozen=True)
class Checkpoint:
    day: date
    target_kg: float
    trend_kg: float | None
    status: CheckpointStatus


@dataclass(frozen=True)
class GoalLine:
    plan: GoalPlan
    anchors: tuple[Anchor, ...]
    checkpoints: tuple[Checkpoint, ...]

    def target_on(self, day: date) -> float | None:
        """The target weight of ``day``; None before the start."""
        return target_on(day, self.anchors, self.plan.rate_kg_per_week)


def line_value(anchor: Anchor, day: date, rate_kg_per_week: float) -> float:
    return anchor.weight_kg - rate_kg_per_week * (day - anchor.day).days / 7


def target_on(day: date, anchors: Sequence[Anchor], rate_kg_per_week: float) -> float | None:
    if not anchors or day < anchors[0].day:
        return None
    current = anchors[0]
    for anchor in anchors:
        if anchor.day <= day:
            current = anchor
    return line_value(current, day, rate_kg_per_week)


def checkpoint_days(plan: GoalPlan) -> list[date]:
    """Every checkpoint weekday after the start, up to and including the end."""
    first = plan.start + timedelta(days=(plan.checkpoint_weekday - plan.start.weekday()) % 7 or 7)
    days = []
    day = first
    while day <= plan.end:
        days.append(day)
        day += timedelta(days=7)
    return days


def goal_line(plan: GoalPlan, trend: Mapping[date, float], today: date) -> GoalLine:
    """Anchors and checkpoint verdicts from the start up to ``today``; later ones are upcoming.

    A checkpoint today without a weigh-in yet is upcoming too (the scale may still come).
    """
    anchors: list[Anchor] = [Anchor(plan.start, plan.start_weight_kg, "start")]
    checkpoints: list[Checkpoint] = []
    rate = plan.rate_kg_per_week
    for day in checkpoint_days(plan):
        target = line_value(anchors[-1], day, rate)
        value = trend.get(day)
        if day > today or (day == today and value is None):
            checkpoints.append(Checkpoint(day, target, value, "upcoming"))
            continue
        if value is not None and value < target:
            anchors.append(Anchor(day, value, "reached"))
            checkpoints.append(Checkpoint(day, target, value, "reached"))
        elif day in plan.accepted:
            level = target if value is None else min(value, target)
            anchors.append(Anchor(day, level, "accepted"))
            checkpoints.append(Checkpoint(day, target, value, "accepted"))
        else:
            status: CheckpointStatus = "missed" if value is not None else "no_weigh_in"
            checkpoints.append(Checkpoint(day, target, value, status))
    return GoalLine(plan, tuple(anchors), tuple(checkpoints))


def on_plan(trend_kg: float | None, target_kg: float | None) -> bool | None:
    if trend_kg is None or target_kg is None:
        return None
    return round(trend_kg - target_kg, 6) <= ON_PLAN_TOLERANCE_KG


# --- body fat --------------------------------------------------------------------------------


def ewma(
    points: Sequence[tuple[date, float]], half_life_days: float = FAT_HALF_LIFE_DAYS
) -> list[float]:
    """Time-aware EWMA: alpha = 1 - 0.5 ** (gap_days / half_life); points sorted by day."""
    out: list[float] = []
    for i, (day, value) in enumerate(points):
        if i == 0:
            out.append(value)
            continue
        gap = (day - points[i - 1][0]).days
        alpha = 1 - math.pow(0.5, gap / half_life_days)
        out.append(out[-1] + alpha * (value - out[-1]))
    return out


@dataclass(frozen=True)
class Regression:
    start_day: date
    end_day: date
    start_value: float
    end_value: float
    slope_per_week: float
    points: int


def regression(
    points: Sequence[tuple[date, float]],
    window_days: int = REGRESSION_WINDOW_DAYS,
    min_points: int = REGRESSION_MIN_POINTS,
    ahead_days: int = REGRESSION_AHEAD_DAYS,
) -> Regression | None:
    """Least squares over the points of the last ``window_days`` before the newest point,
    drawn from the first point of the window to ``ahead_days`` after the newest one."""
    if not points:
        return None
    last = points[-1][0]
    win = [(d, v) for d, v in points if d >= last - timedelta(days=window_days)]
    if len(win) < min_points:
        return None
    xs = [(d - last).days for d, _ in win]
    ys = [v for _, v in win]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / sxx
    icpt = my - slope * mx
    return Regression(
        start_day=win[0][0],
        end_day=last + timedelta(days=ahead_days),
        start_value=icpt + slope * xs[0],
        end_value=icpt + slope * ahead_days,
        slope_per_week=slope * 7,
        points=len(win),
    )


# --- energy ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class BmrEstimate:
    """Resting energy (kcal/day) by three formulas and their mean."""

    mifflin_st_jeor: float
    harris_benedict: float
    katch_mcardle: float | None
    mean: float


def age_on(birth: date, day: date) -> int:
    return day.year - birth.year - ((day.month, day.day) < (birth.month, birth.day))


def bmr(
    weight_kg: float,
    height_cm: float,
    age_years: float,
    sex: Sex,
    body_fat_pct: float | None = None,
) -> BmrEstimate:
    """Mifflin-St Jeor, revised Harris-Benedict (Roza & Shizgal 1984) and, with a body-fat
    value, Katch-McArdle (370 + 21.6 x lean mass); ``mean`` averages the available ones."""
    male = sex == "male"
    mifflin = 10 * weight_kg + 6.25 * height_cm - 5 * age_years + (5 if male else -161)
    if male:
        harris = 88.362 + 13.397 * weight_kg + 4.799 * height_cm - 5.677 * age_years
    else:
        harris = 447.593 + 9.247 * weight_kg + 3.098 * height_cm - 4.330 * age_years
    katch = None
    if body_fat_pct is not None and 0 < body_fat_pct < 100:
        katch = 370 + 21.6 * weight_kg * (1 - body_fat_pct / 100)
    values = [v for v in (mifflin, harris, katch) if v is not None]
    return BmrEstimate(mifflin, harris, katch, sum(values) / len(values))


def active_kcal(
    calories: float | None,
    bmr_calories: float | None,
    duration_s: float | None,
    bmr_per_day: float | None,
) -> float | None:
    """An activity's calories without the resting share: Garmin's total minus its resting
    calories, else minus the resting rate (BMR / 24 h) over the duration."""
    if calories is None:
        return None
    if bmr_calories is not None:
        return max(0.0, calories - bmr_calories)
    if duration_s is not None and bmr_per_day is not None:
        return max(0.0, calories - bmr_per_day * duration_s / 86_400)
    return calories


def target_daily_balance(rate_kg_per_week: float) -> float:
    """The daily energy balance (kcal, negative = deficit) that loses the weekly rate."""
    return -rate_kg_per_week * KCAL_PER_KG / 7
