"""Weight goal: settings, the daily log (weigh-ins, food, training, energy balance), the target
line with checkpoints, body-fat trend and the energy balance of a day.

Everything is a read model over Garmin's weigh-ins (``body_composition``) and activities and the
logged meals; nothing is copied. Rules and formulas: ``garminizer.analytics.goal`` and
docs/metrics.md ("Weight goal").

- Weigh-in of a day: the first one with a body-fat reading (scales sometimes save a plain
  weight first); without any, the first one. Days are the athlete's local calendar days.
- Burn = baseline (BMR x activity factor: rest + everyday life) + training (active calories of
  the activities, i.e. Garmin's calories minus their resting share, so rest is not counted
  twice). BMR = mean of Mifflin-St Jeor, Harris-Benedict and (with body fat) Katch-McArdle from
  the day's trend weight, height, age and sex; Garmin's own BMR when an input is missing.
"""

from __future__ import annotations

import bisect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.analytics import goal as g
from garminizer.athlete import AthleteClock
from garminizer.goal.schemas import (
    DEFAULT_ACTIVITY_FACTOR,
    GoalActivity,
    GoalAnchor,
    GoalBmr,
    GoalCheckpoint,
    GoalDay,
    GoalEnergyBalance,
    GoalFatPoint,
    GoalLinePoint,
    GoalProfile,
    GoalRegression,
    GoalSettings,
    GoalStatus,
    GoalView,
    GoalWeek,
    Sex,
)

GOAL_KEY = "weight_goal"
WEEK_DAYS = 7


class GoalError(ValueError):
    """Invalid goal input (message is safe to show)."""


# --- settings --------------------------------------------------------------------------------


def get_settings(session: Session) -> GoalSettings | None:
    row = session.get(m.AppSetting, GOAL_KEY)
    if row is None:
        return None
    try:
        return GoalSettings.model_validate(row.value)
    except ValidationError:
        return None


def set_settings(session: Session, settings: GoalSettings) -> GoalSettings:
    payload = settings.model_dump(mode="json")
    row = session.get(m.AppSetting, GOAL_KEY)
    if row is None:
        session.add(m.AppSetting(key=GOAL_KEY, value=payload))
    else:
        row.value = payload
        row.updated_at = datetime.now(UTC)
    session.flush()
    return settings


def patch_settings(session: Session, values: Mapping[str, Any]) -> GoalSettings:
    """Merge ``values`` (None = unchanged) into the stored goal; a new goal needs start_day,
    start_weight_kg, rate_kg_per_week and end_day."""
    current = get_settings(session)
    merged = current.model_dump() if current else {}
    merged.update({k: v for k, v in values.items() if v is not None})
    try:
        settings = GoalSettings.model_validate(merged)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'goal'}: {e['msg']}" for e in exc.errors()
        )
        raise GoalError(problems) from None
    return set_settings(session, settings)


def clear_settings(session: Session) -> bool:
    row = session.get(m.AppSetting, GOAL_KEY)
    if row is None:
        return False
    session.delete(row)
    session.flush()
    return True


def _plan(settings: GoalSettings) -> g.GoalPlan:
    return g.GoalPlan(
        start=settings.start_day,
        start_weight_kg=settings.start_weight_kg,
        rate_kg_per_week=settings.rate_kg_per_week,
        end=settings.end_day,
        checkpoint_weekday=settings.checkpoint_weekday,
        accepted=frozenset(settings.accepted_checkpoints),
    )


def set_checkpoint(session: Session, day: date, *, accepted: bool) -> GoalSettings:
    """Count a checkpoint as reached (or undo that)."""
    settings = get_settings(session)
    if settings is None:
        raise GoalError("no weight goal is set")
    if day not in g.checkpoint_days(_plan(settings)):
        raise GoalError(
            f"{day.isoformat()} is not a checkpoint of this goal "
            "(checkpoint weekday after the start day, up to the end day)"
        )
    days = set(settings.accepted_checkpoints)
    if accepted:
        days.add(day)
    else:
        days.discard(day)
    return set_settings(session, settings.model_copy(update={"accepted_checkpoints": sorted(days)}))


# --- loading ---------------------------------------------------------------------------------


def _sex(value: str | None) -> Sex | None:
    v = (value or "").strip().lower()
    return "male" if v == "male" else "female" if v == "female" else None


def profile(session: Session) -> GoalProfile:
    a = session.scalar(select(m.Athlete).order_by(m.Athlete.id).limit(1))
    if a is None:
        return GoalProfile(sex=None, height_cm=None, birth_date=None)
    return GoalProfile(sex=_sex(a.gender), height_cm=a.height_cm, birth_date=a.birth_date)


@dataclass(frozen=True)
class _WeighIn:
    weight_kg: float
    body_fat_pct: float | None
    muscle_mass_kg: float | None
    body_water_pct: float | None


@dataclass(frozen=True)
class _MealDay:
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    meals: int
    names: list[str]


WEIGH_INS_SQL = """
SELECT measured_at, weight_kg, body_fat_pct, muscle_mass_kg, body_water_pct
FROM garmin.body_composition
WHERE measured_at >= :t0 AND measured_at < :t1
ORDER BY measured_at
"""

LAST_WEIGH_IN_SQL = """
SELECT weight_kg, body_fat_pct FROM garmin.body_composition
WHERE measured_at < :t0 ORDER BY measured_at DESC LIMIT 1
"""

LAST_FAT_SQL = """
SELECT body_fat_pct FROM garmin.body_composition
WHERE measured_at < :t0 AND body_fat_pct IS NOT NULL ORDER BY measured_at DESC LIMIT 1
"""

MEALS_SQL = """
SELECT day, sum(kcal) AS kcal, sum(protein_g) AS protein_g, sum(carbs_g) AS carbs_g,
       sum(fat_g) AS fat_g, count(*) AS meals, array_agg(name ORDER BY eaten_at) AS names
FROM garmin.meal
WHERE day BETWEEN :d0 AND :d1
GROUP BY day
"""

ACTIVITIES_SQL = """
SELECT activity_id, name, sport_type, sport_group, start_time_local, duration_s, distance_m,
       avg_hr, calories, bmr_calories
FROM garmin.activity
WHERE start_time_local >= :d0 AND start_time_local < :d1
ORDER BY start_time_local
"""

GARMIN_SQL = """
SELECT day, total_kcal, bmr_kcal FROM garmin.daily_summary WHERE day BETWEEN :d0 AND :d1
"""


def daily_weigh_ins(
    session: Session, start: date, end: date, clock: AthleteClock
) -> dict[date, _WeighIn]:
    """The weigh-in of every local day in [start, end] that has one (see module doc)."""
    t0, t1 = clock.day_span(start, end)
    by_day: dict[date, list[Any]] = {}
    for r in session.execute(text(WEIGH_INS_SQL), {"t0": t0, "t1": t1}):
        by_day.setdefault(clock.local_day(r.measured_at), []).append(r)
    out: dict[date, _WeighIn] = {}
    for day, rows in by_day.items():
        pick = next((r for r in rows if r.body_fat_pct is not None), rows[0])
        out[day] = _WeighIn(
            pick.weight_kg, pick.body_fat_pct, pick.muscle_mass_kg, pick.body_water_pct
        )
    return out


def _r(value: float | None, ndigits: int = 0) -> float | None:
    return None if value is None else round(float(value), ndigits)


@dataclass
class _Data:
    """Everything the day rows of [start, end] need, loaded in a handful of queries."""

    start: date
    end: date
    settings: GoalSettings | None
    profile: GoalProfile
    weigh_ins: dict[date, _WeighIn]
    trend: dict[date, float]
    meals: dict[date, _MealDay]
    activities: dict[date, list[Any]]
    garmin: dict[date, tuple[float | None, float | None]]
    fallback_weight: float | None
    fallback_fat: float | None
    _days: list[date] = field(default_factory=list)
    _fat_days: list[date] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._days = sorted(self.weigh_ins)
        self._fat_days = sorted(d for d, w in self.weigh_ins.items() if w.body_fat_pct is not None)

    @property
    def factor(self) -> float:
        return self.settings.activity_factor if self.settings else DEFAULT_ACTIVITY_FACTOR

    def weight_on(self, day: date) -> float | None:
        if day in self.trend:
            return self.trend[day]
        i = bisect.bisect_right(self._days, day)
        return self.weigh_ins[self._days[i - 1]].weight_kg if i else self.fallback_weight

    def fat_on(self, day: date) -> float | None:
        i = bisect.bisect_right(self._fat_days, day)
        return self.weigh_ins[self._fat_days[i - 1]].body_fat_pct if i else self.fallback_fat

    def bmr(self, day: date) -> GoalBmr | None:
        s, p = self.settings, self.profile
        sex = (s.sex if s else None) or p.sex
        height = (s.height_cm if s else None) or p.height_cm
        birth = (s.birth_date if s else None) or p.birth_date
        weight = self.weight_on(day)
        fat = self.fat_on(day)
        age = g.age_on(birth, day) if birth else None
        missing = [
            name
            for name, value in (
                ("weight_kg", weight),
                ("height_cm", height),
                ("birth_date", birth),
                ("sex", sex),
            )
            if value is None
        ]
        common = {
            "weight_kg": _r(weight, 2),
            "body_fat_pct": fat,
            "height_cm": height,
            "age_years": age,
            "sex": sex,
            "missing": missing,
        }
        if weight is not None and height is not None and age is not None and sex is not None:
            est = g.bmr(weight, height, age, sex, fat)
            return GoalBmr(
                source="formulas",
                kcal=round(est.mean),
                mifflin_st_jeor=round(est.mifflin_st_jeor),
                harris_benedict=round(est.harris_benedict),
                katch_mcardle=_r(est.katch_mcardle),
                **common,
            )
        garmin_bmr = self.garmin.get(day, (None, None))[1]
        if garmin_bmr is None:
            return None
        return GoalBmr(
            source="garmin",
            kcal=round(garmin_bmr),
            mifflin_st_jeor=None,
            harris_benedict=None,
            katch_mcardle=None,
            **common,
        )

    def activities_on(self, day: date, bmr_kcal: float | None) -> list[GoalActivity]:
        return [
            GoalActivity(
                activity_id=r.activity_id,
                name=r.name,
                sport_type=r.sport_type,
                sport_group=r.sport_group,
                start_time_local=r.start_time_local,
                duration_s=r.duration_s,
                distance_m=r.distance_m,
                avg_hr=r.avg_hr,
                calories=_r(r.calories),
                active_kcal=_r(g.active_kcal(r.calories, r.bmr_calories, r.duration_s, bmr_kcal)),
            )
            for r in self.activities.get(day, [])
        ]


def _trend_factors(settings: GoalSettings | None) -> list[float]:
    return settings.trend_weights if settings else list(g.DEFAULT_TREND_WEIGHTS)


def _load(
    session: Session,
    clock: AthleteClock,
    settings: GoalSettings | None,
    start: date,
    end: date,
) -> _Data:
    factors = _trend_factors(settings)
    lead = start - timedelta(days=len(factors) - 1)
    weigh_ins = daily_weigh_ins(session, lead, end, clock)
    t0 = clock.midnight(lead)
    last = session.execute(text(LAST_WEIGH_IN_SQL), {"t0": t0}).first()
    fallback_weight = last.weight_kg if last else None
    if fallback_weight is None:
        fallback_weight = session.scalar(
            select(m.Athlete.weight_kg).order_by(m.Athlete.id).limit(1)
        )
    meals = {
        r.day: _MealDay(r.kcal, r.protein_g, r.carbs_g, r.fat_g, r.meals, [n for n in r.names if n])
        for r in session.execute(text(MEALS_SQL), {"d0": start, "d1": end})
    }
    activities: dict[date, list[Any]] = {}
    d0 = datetime.combine(start, datetime.min.time())
    for r in session.execute(
        text(ACTIVITIES_SQL), {"d0": d0, "d1": d0 + timedelta(days=(end - start).days + 1)}
    ):
        activities.setdefault(r.start_time_local.date(), []).append(r)
    garmin = {
        r.day: (r.total_kcal, r.bmr_kcal)
        for r in session.execute(text(GARMIN_SQL), {"d0": start, "d1": end})
    }
    return _Data(
        start=start,
        end=end,
        settings=settings,
        profile=profile(session),
        weigh_ins=weigh_ins,
        trend=g.weighted_trend({d: w.weight_kg for d, w in weigh_ins.items()}, factors),
        meals=meals,
        activities=activities,
        garmin=garmin,
        fallback_weight=fallback_weight,
        fallback_fat=session.scalar(text(LAST_FAT_SQL), {"t0": t0}),
    )


# --- day rows --------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Energy:
    bmr: GoalBmr | None
    baseline: float | None
    activities: list[GoalActivity]
    training: float
    burn: float | None


def _energy(data: _Data, day: date) -> _Energy:
    bmr = data.bmr(day)
    baseline = None if bmr is None else round(bmr.kcal * data.factor)
    acts = data.activities_on(day, None if bmr is None else bmr.kcal)
    training = float(sum(a.active_kcal or 0 for a in acts))
    burn = None if baseline is None else baseline + training
    return _Energy(bmr, baseline, acts, training, burn)


def _day_row(data: _Data, day: date, line: g.GoalLine | None) -> GoalDay:
    w = data.weigh_ins.get(day)
    trend = data.trend.get(day)
    target = line.target_on(day) if line else None
    delta = trend - target if trend is not None and target is not None else None
    food = data.meals.get(day)
    en = _energy(data, day)
    total, _ = data.garmin.get(day, (None, None))
    sport = [a.calories for a in en.activities if a.calories is not None]
    return GoalDay(
        day=day,
        weight_kg=w.weight_kg if w else None,
        trend_kg=_r(trend, 3),
        target_kg=_r(target, 3),
        delta_kg=_r(delta, 3),
        on_plan=g.on_plan(trend, target),
        body_fat_pct=w.body_fat_pct if w else None,
        muscle_mass_kg=w.muscle_mass_kg if w else None,
        body_water_pct=w.body_water_pct if w else None,
        intake_kcal=_r(food.kcal) if food else None,
        protein_g=_r(food.protein_g, 1) if food else None,
        carbs_g=_r(food.carbs_g, 1) if food else None,
        fat_g=_r(food.fat_g, 1) if food else None,
        meals=food.meals if food else 0,
        meal_names=food.names if food else [],
        sport_kcal=_r(sum(sport)) if sport else None,
        training_kcal=_r(en.training) if en.activities else None,
        baseline_kcal=en.baseline,
        burn_kcal=_r(en.burn),
        balance_kcal=_r(food.kcal - en.burn) if food and en.burn is not None else None,
        garmin_total_kcal=_r(total),
        activities=en.activities,
    )


def _days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def _week(rows: Sequence[GoalDay], start: date, end: date, daily_target: float | None) -> GoalWeek:
    logged = [r for r in rows if start <= r.day <= end and r.intake_kcal is not None]
    with_burn = [r for r in logged if r.burn_kcal is not None]
    intake = sum(r.intake_kcal or 0 for r in with_burn)
    burn = sum(r.burn_kcal or 0 for r in with_burn)
    return GoalWeek(
        start=start,
        end=end,
        days_logged=len(logged),
        intake_kcal=_r(sum(r.intake_kcal or 0 for r in logged)) if logged else None,
        burn_kcal=_r(burn) if with_burn else None,
        balance_kcal=_r(intake - burn) if with_burn else None,
        target_balance_kcal=_r(daily_target * len(with_burn))
        if daily_target is not None and with_burn
        else None,
    )


def _week_end(day: date, today: date) -> date:
    """Weeks end on ``day``, but today is not over yet: then they end yesterday."""
    return day - timedelta(days=1) if day == today else day


# --- the view --------------------------------------------------------------------------------


def _target_line(line: g.GoalLine, until: date) -> list[GoalLinePoint]:
    rate = line.plan.rate_kg_per_week
    points: list[GoalLinePoint] = []
    anchors = line.anchors
    for i, a in enumerate(anchors):
        nxt = anchors[i + 1].day if i + 1 < len(anchors) else until
        points.append(GoalLinePoint(day=a.day, target_kg=round(a.weight_kg, 3)))
        points.append(GoalLinePoint(day=nxt, target_kg=round(g.line_value(a, nxt, rate), 3)))
    return points


def _body_fat(rows: Sequence[GoalDay]) -> tuple[list[GoalFatPoint], GoalRegression | None]:
    pts = [(r.day, r.body_fat_pct) for r in rows if r.body_fat_pct is not None]
    trend = g.ewma(pts)
    reg = g.regression(pts)
    out = [
        GoalFatPoint(day=d, body_fat_pct=v, trend_pct=round(t, 2))
        for (d, v), t in zip(pts, trend, strict=True)
    ]
    if reg is None:
        return out, None
    return out, GoalRegression(
        start_day=reg.start_day,
        end_day=reg.end_day,
        start_pct=round(reg.start_value, 2),
        end_pct=round(reg.end_value, 2),
        slope_pct_per_week=round(reg.slope_per_week, 3),
        points=reg.points,
    )


def _status(
    settings: GoalSettings,
    line: g.GoalLine,
    rows: Sequence[GoalDay],
    today: date,
    daily_target: float,
) -> GoalStatus:
    with_trend = [r for r in rows if r.trend_kg is not None]
    last = with_trend[-1] if with_trend else None
    fat = next((r for r in reversed(rows) if r.body_fat_pct is not None), None)
    muscle = next((r for r in reversed(rows) if r.muscle_mass_kg is not None), None)
    water = next((r for r in reversed(rows) if r.body_water_pct is not None), None)
    upcoming = next((c for c in line.checkpoints if c.status == "upcoming"), None)
    week_end = _week_end(today, today)
    trend = last.trend_kg if last else None
    return GoalStatus(
        as_of=last.day if last else None,
        trend_kg=trend,
        target_kg=last.target_kg if last else None,
        delta_kg=last.delta_kg if last else None,
        on_plan=last.on_plan if last else None,
        since_start_kg=_r(trend - settings.start_weight_kg, 3) if trend is not None else None,
        target_today_kg=_r(line.target_on(today), 3),
        target_end_kg=_r(line.target_on(settings.end_day), 3),
        days_left=max(0, (settings.end_day - today).days),
        next_checkpoint=_checkpoint(upcoming) if upcoming else None,
        body_fat_pct=fat.body_fat_pct if fat else None,
        body_fat_day=fat.day if fat else None,
        muscle_mass_kg=muscle.muscle_mass_kg if muscle else None,
        body_water_pct=water.body_water_pct if water else None,
        week=_week(rows, week_end - timedelta(days=WEEK_DAYS - 1), week_end, daily_target),
    )


def _checkpoint(c: g.Checkpoint) -> GoalCheckpoint:
    return GoalCheckpoint(
        day=c.day, target_kg=round(c.target_kg, 3), trend_kg=_r(c.trend_kg, 3), status=c.status
    )


def view(session: Session, *, clock: AthleteClock) -> GoalView:
    """Everything the weight goal page shows."""
    today = clock.today()
    settings = get_settings(session)
    if settings is None:
        data = _load(session, clock, None, today, today)
        return GoalView(
            configured=False,
            today=today,
            settings=None,
            profile=data.profile,
            target_daily_balance_kcal=None,
            status=None,
            days=[],
            anchors=[],
            checkpoints=[],
            target_line=[],
            body_fat=[],
            body_fat_regression=None,
            bmr_today=data.bmr(today),
        )
    start = settings.start_day
    last_day = max(today, start)
    data = _load(session, clock, settings, start, last_day)
    line = g.goal_line(_plan(settings), data.trend, today)
    rows = [_day_row(data, d, line) for d in _days(start, today)] if today >= start else []
    fat, reg = _body_fat(rows)
    daily_target = round(g.target_daily_balance(settings.rate_kg_per_week))
    return GoalView(
        configured=True,
        today=today,
        settings=settings,
        profile=data.profile,
        target_daily_balance_kcal=daily_target,
        status=_status(settings, line, rows, today, daily_target),
        days=rows,
        anchors=[
            GoalAnchor(day=a.day, weight_kg=round(a.weight_kg, 3), kind=a.kind)
            for a in line.anchors
        ],
        checkpoints=[_checkpoint(c) for c in line.checkpoints],
        target_line=_target_line(line, max(settings.end_day, today)),
        body_fat=fat,
        body_fat_regression=reg,
        bmr_today=data.bmr(today),
    )


# --- energy balance of one day ---------------------------------------------------------------


def energy_balance(session: Session, day: date, *, clock: AthleteClock) -> GoalEnergyBalance:
    """Intake vs computed burn of ``day`` plus the 7 (completed) days up to it."""
    today = clock.today()
    settings = get_settings(session)
    week_end = _week_end(day, today)
    week_start = week_end - timedelta(days=WEEK_DAYS - 1)
    data = _load(session, clock, settings, min(week_start, day), day)
    line = g.goal_line(_plan(settings), data.trend, today) if settings else None
    daily_target = round(g.target_daily_balance(settings.rate_kg_per_week)) if settings else None
    rows = [_day_row(data, d, line) for d in _days(min(week_start, day), day)]
    row = rows[-1]
    en = _energy(data, day)
    total, _ = data.garmin.get(day, (None, None))
    intake = row.intake_kcal or 0.0
    balance = None if en.burn is None else round(intake - en.burn)
    left = (
        round(en.burn + daily_target - intake)
        if en.burn is not None and daily_target is not None
        else None
    )
    return GoalEnergyBalance(
        day=day,
        is_today=day == today,
        as_of=clock.now().strftime("%H:%M") if day == today else None,
        intake_kcal=intake,
        meals=row.meals,
        protein_g=row.protein_g,
        carbs_g=row.carbs_g,
        fat_g=row.fat_g,
        bmr=en.bmr,
        activity_factor=data.factor,
        baseline_kcal=en.baseline,
        activities=en.activities,
        training_kcal=round(en.training),
        burn_kcal=_r(en.burn),
        balance_kcal=balance,
        target_balance_kcal=daily_target,
        left_to_target_kcal=left,
        garmin_total_kcal=_r(total),
        week=_week(rows, week_start, week_end, daily_target),
        goal_configured=settings is not None,
    )


def checkpoint_days(settings: GoalSettings) -> list[date]:
    return g.checkpoint_days(_plan(settings))


__all__ = [
    "GOAL_KEY",
    "GoalError",
    "checkpoint_days",
    "clear_settings",
    "daily_weigh_ins",
    "energy_balance",
    "get_settings",
    "patch_settings",
    "profile",
    "set_checkpoint",
    "set_settings",
    "view",
]
