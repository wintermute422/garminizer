"""Meal logging and intake-versus-expenditure summaries over a SQLAlchemy session.

The caller owns the transaction: these functions only flush; the API route or the MCP tool
commits. A meal's ``day`` is the local date of ``eaten_at`` in the athlete's time zone
(the caller's ``AthleteClock``, see garminizer.athlete). Garmin's daily summary supplies
the energy expenditure; ``balance = intake - Garmin total kcal``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.athlete import AthleteClock
from garminizer.nutrition.schemas import (
    ITEM_NUTRIENTS,
    MACRO_FIELDS,
    MEAL_NUTRIENTS,
    TARGET_FIELDS,
    MealSource,
    MealType,
    NutritionActivity,
    NutritionDailyPoint,
    NutritionDay,
    NutritionDaySummary,
    NutritionEnergyContext,
    NutritionGarminEnergy,
    NutritionItemIn,
    NutritionMacroSplit,
    NutritionMeal,
    NutritionMealIn,
    NutritionMealItem,
    NutritionMealPatch,
    NutritionMealTypeStat,
    NutritionRemaining,
    NutritionSummary,
    NutritionTargets,
    NutritionTotals,
    NutritionTotalsIn,
    NutritionWarning,
    NutritionWeek,
)

TARGETS_KEY = "nutrition_targets"
MEAL_TYPE_ORDER: tuple[MealType, ...] = ("breakfast", "lunch", "dinner", "snack", "drink")
# Atwater factors (kcal per gram).
KCAL_PER_G = {"protein_g": 4.0, "carbs_g": 4.0, "fat_g": 9.0, "alcohol_g": 7.0}
MISMATCH_SHARE = 0.15  # flag when macro energy and kcal differ by more than 15 % ...
MISMATCH_FLOOR_KCAL = 10.0  # ... and by more than 10 kcal (a black coffee is not a mismatch)
MAX_FUTURE = timedelta(hours=12)
EARLIEST = datetime(2000, 1, 1, tzinfo=UTC)


class NutritionError(ValueError):
    """Invalid meal input; the message is meant for the user (or Claude) as is."""


class MealNotFoundError(LookupError):
    def __init__(self, meal_id: int) -> None:
        super().__init__(f"no meal with meal_id {meal_id}")
        self.meal_id = meal_id


# --- small helpers -------------------------------------------------------------------------


def _r(value: float | None, ndigits: int = 1) -> float | None:
    return None if value is None else round(float(value), ndigits)


def _sum(values: Iterable[float | None]) -> float | None:
    """Sum of the known values; None when none is known (like SQL ``sum``)."""
    present = [float(v) for v in values if v is not None]
    return round(sum(present), 1) if present else None


def _mean(values: Iterable[float | None]) -> float | None:
    present = [float(v) for v in values if v is not None]
    return round(sum(present) / len(present), 1) if present else None


def _minus(target: float | None, value: float | None) -> float | None:
    return None if target is None else round(target - (value or 0.0), 1)


def infer_meal_type(local: datetime) -> MealType:
    """Meal type from the local time of day."""
    minutes = local.hour * 60 + local.minute
    if 4 * 60 <= minutes < 10 * 60 + 30:
        return "breakfast"
    if 10 * 60 + 30 <= minutes < 15 * 60:
        return "lunch"
    if 17 * 60 <= minutes < 21 * 60 + 30:
        return "dinner"
    return "snack"


def resolve_eaten_at(eaten_at: datetime | None, tz: ZoneInfo, now: datetime) -> datetime:
    """UTC time of the meal: naive values are local to ``tz``; default ``now``."""
    when = now if eaten_at is None else eaten_at
    if when.tzinfo is None:
        when = when.replace(tzinfo=tz)
    when = when.astimezone(UTC)
    if when > now + MAX_FUTURE:
        raise NutritionError(
            f"eaten_at {when.astimezone(tz).isoformat()} is in the future; give the time the meal "
            "was eaten (local time) or leave it out for now"
        )
    if when < EARLIEST:
        raise NutritionError("eaten_at is before the year 2000")
    return when


# --- totals and plausibility -----------------------------------------------------------------


def compute_totals(
    items: Sequence[NutritionItemIn], totals: NutritionTotalsIn | None
) -> dict[str, float | None]:
    """Meal nutrients: every explicit total wins; kcal and macros otherwise sum the items."""
    explicit = totals.model_dump() if totals is not None else {}
    out: dict[str, float | None] = {}
    for key in MEAL_NUTRIENTS:
        given = explicit.get(key)
        if given is not None:
            out[key] = _r(given)
        elif key in ITEM_NUTRIENTS and items:
            out[key] = _sum(getattr(item, key) for item in items)
        else:
            out[key] = None
    if out["kcal"] is None:
        raise NutritionError(
            "kcal unknown: give the foods as items (each with kcal) or totals.kcal"
        )
    return out


def macro_kcal(
    protein_g: float | None, carbs_g: float | None, fat_g: float | None, alcohol_g: float | None
) -> float | None:
    """Energy implied by the macros (Atwater); None unless protein, carbs and fat are known."""
    if protein_g is None or carbs_g is None or fat_g is None:
        return None
    return 4.0 * protein_g + 4.0 * carbs_g + 9.0 * fat_g + 7.0 * (alcohol_g or 0.0)


def _off(a: float, b: float) -> bool:
    return abs(a - b) > max(MISMATCH_SHARE * b, MISMATCH_FLOOR_KCAL)


def meal_warnings(
    kcal: float,
    protein_g: float | None,
    carbs_g: float | None,
    fat_g: float | None,
    alcohol_g: float | None,
    items_kcal: float | None = None,
) -> list[NutritionWarning]:
    """Plausibility checks; the meal is stored either way."""
    out: list[NutritionWarning] = []
    implied = macro_kcal(protein_g, carbs_g, fat_g, alcohol_g)
    if implied is not None and _off(implied, kcal):
        share = f"{abs(implied - kcal) / kcal * 100:.0f} % off" if kcal > 0 else "kcal is 0"
        out.append(
            NutritionWarning(
                code="macro_kcal_mismatch",
                message=f"4 x protein + 4 x carbs + 9 x fat + 7 x alcohol = {implied:.0f} kcal, "
                f"but the meal has {kcal:.0f} kcal ({share}); check the portions or the macros.",
            )
        )
    if items_kcal is not None and _off(items_kcal, kcal):
        out.append(
            NutritionWarning(
                code="items_kcal_mismatch",
                message=f"The items add up to {items_kcal:.0f} kcal, "
                f"but the meal total is {kcal:.0f} kcal.",
            )
        )
    return out


# --- meals -----------------------------------------------------------------------------------


def to_meal_out(meal: m.Meal, tz: ZoneInfo) -> NutritionMeal:
    items = [
        NutritionMealItem(
            idx=i.idx,
            food=i.food,
            amount=_r(i.amount, 2),
            unit=i.unit,
            grams=_r(i.grams),
            kcal=round(float(i.kcal), 1),
            protein_g=_r(i.protein_g),
            carbs_g=_r(i.carbs_g),
            fat_g=_r(i.fat_g),
            fiber_g=_r(i.fiber_g),
        )
        for i in meal.items
    ]
    values: dict[str, Any] = {k: _r(getattr(meal, k)) for k in MEAL_NUTRIENTS}
    items_kcal = _sum(i.kcal for i in items) if items else None
    return NutritionMeal.model_validate(
        {
            **values,
            "meal_id": meal.meal_id,
            "eaten_at": meal.eaten_at.astimezone(tz),
            "day": meal.day,
            "meal_type": meal.meal_type,
            "name": meal.name,
            "notes": meal.notes,
            "source": meal.source,
            "confidence": meal.confidence,
            "created_at": meal.created_at,
            "updated_at": meal.updated_at,
            "items": items,
            "warnings": meal_warnings(
                values["kcal"],
                values["protein_g"],
                values["carbs_g"],
                values["fat_g"],
                values["alcohol_g"],
                items_kcal,
            ),
        }
    )


def _item_rows(items: Sequence[NutritionItemIn]) -> list[m.MealItem]:
    return [
        m.MealItem(
            idx=idx,
            food=item.food.strip(),
            amount=_r(item.amount, 2),
            unit=item.unit.strip() if item.unit else None,
            grams=_r(item.grams),
            kcal=round(item.kcal, 1),
            protein_g=_r(item.protein_g),
            carbs_g=_r(item.carbs_g),
            fat_g=_r(item.fat_g),
            fiber_g=_r(item.fiber_g),
        )
        for idx, item in enumerate(items)
    ]


def log_meal(
    session: Session,
    data: NutritionMealIn,
    *,
    source: MealSource,
    clock: AthleteClock,
) -> NutritionMeal:
    """Store a meal; totals come from the items unless given explicitly."""
    tz = clock.zone
    now = clock.now_utc()
    eaten = resolve_eaten_at(data.eaten_at, tz, now)
    local = eaten.astimezone(tz)
    totals = compute_totals(data.items, data.totals)
    meal = m.Meal(
        eaten_at=eaten,
        day=local.date(),
        meal_type=data.meal_type or infer_meal_type(local),
        name=data.name.strip(),
        notes=data.notes.strip() if data.notes else None,
        source=source,
        confidence=data.confidence,
        created_at=now,
        updated_at=now,
        items=_item_rows(data.items),
        **totals,
    )
    session.add(meal)
    session.flush()
    return to_meal_out(meal, tz)


def _get(session: Session, meal_id: int) -> m.Meal:
    meal = session.get(m.Meal, meal_id)
    if meal is None:
        raise MealNotFoundError(meal_id)
    return meal


def get_meal(session: Session, meal_id: int, *, clock: AthleteClock) -> NutritionMeal:
    return to_meal_out(_get(session, meal_id), clock.zone)


def update_meal(
    session: Session,
    meal_id: int,
    patch: NutritionMealPatch,
    *,
    clock: AthleteClock,
) -> NutritionMeal:
    """Apply ``patch``; new items replace the old ones and recompute kcal and macros."""
    meal = _get(session, meal_id)
    tz = clock.zone
    now = clock.now_utc()
    given = patch.model_fields_set
    if patch.name is not None:
        meal.name = patch.name.strip()
    if patch.eaten_at is not None:
        meal.eaten_at = resolve_eaten_at(patch.eaten_at, tz, now)
        meal.day = meal.eaten_at.astimezone(tz).date()
    if patch.meal_type is not None:
        meal.meal_type = patch.meal_type
    if "notes" in given:
        meal.notes = patch.notes.strip() if patch.notes else None
    if "confidence" in given:
        meal.confidence = patch.confidence
    if patch.items is not None:
        meal.items.clear()
        session.flush()  # delete the old rows before new ones reuse their (meal_id, idx)
        meal.items.extend(_item_rows(patch.items))
        if patch.items:
            for key in ITEM_NUTRIENTS:
                value = _sum(getattr(item, key) for item in patch.items)
                if key != "kcal" or value is not None:
                    setattr(meal, key, value)
    if patch.totals is not None:
        for key in patch.totals.model_fields_set & set(MEAL_NUTRIENTS):
            value = getattr(patch.totals, key)
            if key == "kcal" and value is None:
                continue
            setattr(meal, key, _r(value))
    meal.updated_at = now
    session.flush()
    return to_meal_out(meal, tz)


def delete_meal(session: Session, meal_id: int, *, clock: AthleteClock) -> NutritionMeal:
    """Delete a meal and its items; returns the deleted meal."""
    meal = _get(session, meal_id)
    out = to_meal_out(meal, clock.zone)
    session.delete(meal)
    session.flush()
    return out


def _meals(
    session: Session,
    start: date,
    end: date,
    tz: ZoneInfo,
    *,
    newest_first: bool = False,
    limit: int | None = None,
) -> list[NutritionMeal]:
    order = m.Meal.eaten_at.desc() if newest_first else m.Meal.eaten_at
    query = select(m.Meal).where(m.Meal.day.between(start, end)).order_by(order, m.Meal.meal_id)
    if limit is not None:
        query = query.limit(limit)
    return [to_meal_out(meal, tz) for meal in session.scalars(query)]


def list_meals(
    session: Session,
    start: date,
    end: date,
    *,
    clock: AthleteClock,
    newest_first: bool = False,
    limit: int | None = None,
) -> list[NutritionMeal]:
    """Meals whose local day is within [start, end], with their items."""
    tz = clock.zone
    return _meals(session, start, end, tz, newest_first=newest_first, limit=limit)


def last_meal_day(session: Session) -> date | None:
    return session.scalar(select(func.max(m.Meal.day)))


# --- targets ---------------------------------------------------------------------------------


def get_targets(session: Session) -> NutritionTargets:
    row = session.get(m.AppSetting, TARGETS_KEY)
    if row is None:
        return NutritionTargets()
    known = {k: v for k, v in row.value.items() if k in TARGET_FIELDS}
    try:
        return NutritionTargets.model_validate(known)
    except ValidationError:
        return NutritionTargets()


def set_targets(
    session: Session,
    targets: NutritionTargets,
    *,
    merge: bool = False,
    clear: Iterable[str] = (),
) -> NutritionTargets:
    """Store targets: replace all (default) or merge the given values; ``clear`` unsets fields."""
    values = get_targets(session).model_dump() if merge else {}
    new_values = targets.model_dump()
    values.update({k: v for k, v in new_values.items() if v is not None} if merge else new_values)
    for key in clear:
        if key not in TARGET_FIELDS:
            raise NutritionError(f"unknown target {key!r}; known: {', '.join(TARGET_FIELDS)}")
        values[key] = None
    stored = NutritionTargets.model_validate(values)
    payload = stored.model_dump(exclude_none=True)
    row = session.get(m.AppSetting, TARGETS_KEY)
    if row is None:
        session.add(m.AppSetting(key=TARGETS_KEY, value=payload))
    else:
        row.value = payload
        row.updated_at = datetime.now(UTC)
    session.flush()
    return stored


def protein_target(targets: NutritionTargets, weight_kg: float | None) -> float | None:
    """The protein_g target, or protein_g_per_kg x body weight."""
    if targets.protein_g is not None:
        return targets.protein_g
    if targets.protein_g_per_kg is not None and weight_kg:
        return round(targets.protein_g_per_kg * weight_kg)
    return None


# --- days, series and summaries --------------------------------------------------------------


def weight_on(session: Session, day: date, tz: ZoneInfo) -> float | None:
    """Latest weigh-in before the end of ``day`` (local), else the profile weight."""
    end = datetime.combine(day + timedelta(days=1), time(), tz)
    weight = session.scalar(
        select(m.BodyComposition.weight_kg)
        .where(m.BodyComposition.measured_at < end)
        .order_by(m.BodyComposition.measured_at.desc())
        .limit(1)
    )
    if weight is None:
        weight = session.scalar(select(m.Athlete.weight_kg).order_by(m.Athlete.id).limit(1))
    return _r(weight)


def _garmin(session: Session, day: date) -> tuple[NutritionGarminEnergy, int | None]:
    row = session.execute(
        select(
            m.DailySummary.total_kcal,
            m.DailySummary.active_kcal,
            m.DailySummary.bmr_kcal,
            m.DailySummary.steps,
        ).where(m.DailySummary.day == day)
    ).first()
    if row is None:
        return NutritionGarminEnergy(total_kcal=None, active_kcal=None, bmr_kcal=None), None
    energy = NutritionGarminEnergy(
        total_kcal=_r(row.total_kcal), active_kcal=_r(row.active_kcal), bmr_kcal=_r(row.bmr_kcal)
    )
    return energy, row.steps


def day_totals(meals: Sequence[NutritionMeal]) -> NutritionTotals:
    values: dict[str, Any] = {k: _sum(getattr(x, k) for x in meals) for k in MEAL_NUTRIENTS}
    values["kcal"] = values["kcal"] or 0.0
    return NutritionTotals.model_validate({**values, "meals": len(meals)})


def _balance(totals: NutritionTotals, garmin: NutritionGarminEnergy) -> float | None:
    if not totals.meals or garmin.total_kcal is None:
        return None
    return round(totals.kcal - garmin.total_kcal, 1)


def _day_summary(
    session: Session, day: date, tz: ZoneInfo, meals: Sequence[NutritionMeal], now: datetime
) -> dict[str, Any]:
    totals = day_totals(meals)
    targets = get_targets(session)
    weight = weight_on(session, day, tz)
    p_target = protein_target(targets, weight)
    garmin, _ = _garmin(session, day)
    remaining = NutritionRemaining(
        kcal=_minus(targets.kcal, totals.kcal),
        protein_g=_minus(p_target, totals.protein_g),
        carbs_g=_minus(targets.carbs_g, totals.carbs_g),
        fat_g=_minus(targets.fat_g, totals.fat_g),
        fiber_g=_minus(targets.fiber_g, totals.fiber_g),
    )
    per_kg = round(totals.protein_g / weight, 2) if totals.protein_g and weight else None
    return {
        "day": day,
        "is_today": day == now.astimezone(tz).date(),
        "totals": totals,
        "targets": targets,
        "protein_target_g": p_target,
        "remaining": remaining,
        "garmin": garmin,
        "balance_kcal": _balance(totals, garmin),
        "weight_kg": weight,
        "protein_g_per_kg": per_kg,
    }


def day_summary(session: Session, day: date, *, clock: AthleteClock) -> NutritionDaySummary:
    """Intake totals, targets, what is left, Garmin's burn and the balance of one day."""
    tz = clock.zone
    meals = _meals(session, day, day, tz)
    return NutritionDaySummary.model_validate(
        _day_summary(session, day, tz, meals, clock.now_utc())
    )


def get_day(session: Session, day: date, *, clock: AthleteClock) -> NutritionDay:
    """The day summary plus every meal of the day with its items."""
    tz = clock.zone
    meals = _meals(session, day, day, tz)
    summary = _day_summary(session, day, tz, meals, clock.now_utc())
    return NutritionDay.model_validate({**summary, "meals": meals})


DAILY_SQL = """
WITH n AS (
    SELECT day, count(*) AS meals, sum(kcal) AS intake_kcal, sum(protein_g) AS protein_g,
           sum(carbs_g) AS carbs_g, sum(fat_g) AS fat_g, sum(fiber_g) AS fiber_g,
           sum(alcohol_g) AS alcohol_g
    FROM garmin.meal WHERE day BETWEEN :start AND :end GROUP BY day
), d AS (
    SELECT day, total_kcal, active_kcal FROM garmin.daily_summary
    WHERE day BETWEEN :start AND :end AND (total_kcal IS NOT NULL OR active_kcal IS NOT NULL)
)
SELECT day, coalesce(n.meals, 0) AS meals, n.intake_kcal, n.protein_g, n.carbs_g, n.fat_g,
       n.fiber_g, n.alcohol_g, d.total_kcal, d.active_kcal,
       n.intake_kcal - d.total_kcal AS balance_kcal
FROM n FULL JOIN d USING (day)
ORDER BY day
"""


def daily_series(session: Session, start: date, end: date) -> list[NutritionDailyPoint]:
    """Per day: logged intake and macros, Garmin burn and balance (days with any data)."""
    result = session.execute(text(DAILY_SQL), {"start": start, "end": end}).mappings()
    return [
        NutritionDailyPoint.model_validate(
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
        )
        for r in result
    ]


def _macro_split(points: Sequence[NutritionDailyPoint]) -> NutritionMacroSplit:
    energy = {
        key: KCAL_PER_G[key] * sum(getattr(p, key) or 0.0 for p in points)
        for key in ("protein_g", "carbs_g", "fat_g", "alcohol_g")
    }
    total = sum(energy.values())
    if total <= 0:
        return NutritionMacroSplit(protein_pct=None, carbs_pct=None, fat_pct=None, alcohol_pct=None)
    pct = {k: round(v / total * 100, 1) for k, v in energy.items()}
    return NutritionMacroSplit(
        protein_pct=pct["protein_g"],
        carbs_pct=pct["carbs_g"],
        fat_pct=pct["fat_g"],
        alcohol_pct=pct["alcohol_g"],
    )


def _meal_type_stats(session: Session, start: date, end: date) -> list[NutritionMealTypeStat]:
    data = session.execute(
        select(m.Meal.meal_type, func.count(), func.sum(m.Meal.kcal))
        .where(m.Meal.day.between(start, end))
        .group_by(m.Meal.meal_type)
    ).all()
    by_type = {r[0]: (int(r[1]), float(r[2] or 0.0)) for r in data}
    total = sum(kcal for _, kcal in by_type.values())
    return [
        NutritionMealTypeStat(
            meal_type=mt,
            meals=by_type[mt][0],
            kcal_pct=round(by_type[mt][1] / total * 100, 1) if total > 0 else 0.0,
        )
        for mt in MEAL_TYPE_ORDER
        if mt in by_type
    ]


def _weekly_weights(session: Session, start: date, end: date, tz: ZoneInfo) -> dict[date, float]:
    t0 = datetime.combine(start - timedelta(days=start.weekday()), time(), tz)
    t1 = datetime.combine(end + timedelta(days=7 - end.weekday()), time(), tz)
    data = session.execute(
        text(
            "SELECT date_trunc('week', measured_at AT TIME ZONE :tz)::date AS week, "
            "avg(weight_kg)::float8 AS kg FROM garmin.body_composition "
            "WHERE measured_at >= :t0 AND measured_at < :t1 GROUP BY 1"
        ),
        {"tz": str(tz), "t0": t0, "t1": t1},
    ).all()
    return {r[0]: round(float(r[1]), 2) for r in data}


def _weeks(
    points: Sequence[NutritionDailyPoint], weights: dict[date, float]
) -> list[NutritionWeek]:
    by_week: dict[date, list[NutritionDailyPoint]] = defaultdict(list)
    for p in points:
        if p.meals:
            by_week[p.day - timedelta(days=p.day.weekday())].append(p)
    return [
        NutritionWeek(
            week=week,
            days_logged=len(days),
            intake_kcal=_mean(p.intake_kcal for p in days),
            total_kcal=_mean(p.total_kcal for p in days),
            balance_kcal=_mean(p.balance_kcal for p in days),
            protein_g=_mean(p.protein_g for p in days),
            carbs_g=_mean(p.carbs_g for p in days),
            fat_g=_mean(p.fat_g for p in days),
            weight_kg=weights.get(week),
        )
        for week, days in sorted(by_week.items())
    ]


def summary(session: Session, start: date, end: date, *, clock: AthleteClock) -> NutritionSummary:
    """Averages per logged day, macro split, protein per kg, targets and weekly averages."""
    tz = clock.zone
    points = daily_series(session, start, end)
    logged = [p for p in points if p.meals]
    weight = weight_on(session, end, tz)
    avg_protein = _mean(p.protein_g for p in logged)
    targets = get_targets(session)
    return NutritionSummary(
        start=start,
        end=end,
        days=(end - start).days + 1,
        days_logged=len(logged),
        meals=sum(p.meals for p in logged),
        avg_intake_kcal=_mean(p.intake_kcal for p in logged),
        avg_protein_g=avg_protein,
        avg_carbs_g=_mean(p.carbs_g for p in logged),
        avg_fat_g=_mean(p.fat_g for p in logged),
        avg_fiber_g=_mean(p.fiber_g for p in logged),
        avg_total_kcal=_mean(p.total_kcal for p in logged),
        avg_active_kcal=_mean(p.active_kcal for p in logged),
        avg_balance_kcal=_mean(p.balance_kcal for p in logged),
        weight_kg=weight,
        protein_g_per_kg=round(avg_protein / weight, 2) if avg_protein and weight else None,
        macro_split=_macro_split(logged),
        by_meal_type=_meal_type_stats(session, start, end),
        targets=targets,
        protein_target_g=protein_target(targets, weight),
        weeks=_weeks(points, _weekly_weights(session, start, end, tz)),
    )


def average_burn(session: Session, start: date, end: date) -> float | None:
    """Mean Garmin total kcal per day over [start, end] (days with a value)."""
    value = session.scalar(
        select(func.avg(m.DailySummary.total_kcal)).where(m.DailySummary.day.between(start, end))
    )
    return _r(value)


ACTIVITIES_SQL = """
SELECT activity_id, name, sport_group, sport_type, start_time_local, duration_s, distance_m,
       calories, training_load
FROM garmin.activity
WHERE start_time_local >= :d0 AND start_time_local < :d1
ORDER BY start_time_local
"""


def energy_context(session: Session, day: date, *, clock: AthleteClock) -> NutritionEnergyContext:
    """Garmin's view of a day: calories burned, activities, training load, readiness."""
    tz = clock.zone
    now = clock.now_utc()
    garmin, steps = _garmin(session, day)
    d0 = datetime.combine(day, time())
    acts = [
        NutritionActivity.model_validate(
            {k: (_r(v) if isinstance(v, float) else v) for k, v in r.items()}
        )
        for r in session.execute(
            text(ACTIVITIES_SQL), {"d0": d0, "d1": d0 + timedelta(days=1)}
        ).mappings()
    ]
    load = session.get(m.DailyLoad, day)
    status = session.get(m.TrainingStatus, day)
    readiness = session.get(m.TrainingReadiness, day)
    avg_7d = average_burn(session, day - timedelta(days=7), day - timedelta(days=1))
    meals = _meals(session, day, day, tz)
    totals = day_totals(meals)
    demo = session.scalar(select(m.Athlete.is_demo).order_by(m.Athlete.id).limit(1))
    return NutritionEnergyContext(
        day=day,
        is_today=day == now.astimezone(tz).date(),
        demo_data=bool(demo),
        garmin=garmin,
        steps=steps,
        activities=acts,
        training_load=_r(load.load) if load else None,
        fitness_ctl=_r(load.ctl) if load else None,
        fatigue_atl=_r(load.atl) if load else None,
        form_tsb=_r(load.tsb) if load else None,
        training_status=status.status if status else None,
        readiness=readiness.score if readiness else None,
        avg_total_kcal_7d=avg_7d,
        intake=totals,
        balance_kcal=_balance(totals, garmin),
    )


__all__ = [
    "MACRO_FIELDS",
    "MealNotFoundError",
    "NutritionError",
    "average_burn",
    "compute_totals",
    "daily_series",
    "day_summary",
    "day_totals",
    "delete_meal",
    "energy_context",
    "get_day",
    "get_meal",
    "get_targets",
    "infer_meal_type",
    "last_meal_day",
    "list_meals",
    "log_meal",
    "meal_warnings",
    "protein_target",
    "resolve_eaten_at",
    "set_targets",
    "summary",
    "update_meal",
    "weight_on",
]
