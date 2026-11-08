"""Synthetic food diary for the demo athlete: 3-5 meals a day with items, kcal and macros.

Intake follows Garmin's total burn of the day minus the small deficit behind the demo's slow
weight loss (plus noise and a little weekend surplus). Protein is 1.6-2.0 g per kg body weight,
carbohydrates are higher on training days and highest on long-run days, about one day in ten
is not logged. Portions are solved per meal so that a protein, a carbohydrate and a fat food
plus fixed sides hit the meal's macro targets; item nutrients come from per-100 g reference
values, so meal totals are exactly the sum of their items. Deterministic for a given seed.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import insert
from sqlalchemy.orm import Session

from garminizer import models as m

MEAL_STREAM = 0x6D65616C  # separate random stream: the rest of the demo stays unchanged
SKIP_DAY_P = 0.10
WEEKLY_LOSS_KCAL_PER_KG = 7700.0
DEMO_LOSS_KG = 3.0  # matches demo.seed._weight's linear trend


@dataclass(frozen=True)
class Food:
    name: str
    kcal: float  # per 100 g (or 100 ml)
    protein: float
    carbs: float
    fat: float
    fiber: float
    sugar: float = 0.0
    sat_fat: float = 0.0
    sodium_mg: float = 0.0
    alcohol: float = 0.0
    unit: str | None = None  # counted unit, e.g. slice; None = grams (or ml when liquid)
    unit_g: float = 0.0
    liquid: bool = False

    def macros(self) -> np.ndarray[Any, Any]:
        return np.array([self.protein, self.carbs, self.fat]) / 100.0


def _f(
    name: str,
    kcal: float,
    protein: float,
    carbs: float,
    fat: float,
    fiber: float,
    sugar: float = 0.0,
    sat_fat: float = 0.0,
    sodium_mg: float = 0.0,
    **kw: Any,
) -> Food:
    return Food(name, kcal, protein, carbs, fat, fiber, sugar, sat_fat, sodium_mg, **kw)


# Per 100 g, rounded reference values (USDA FoodData Central / BLS style).
F = {
    "greek_yoghurt": _f("Greek yoghurt (2 % fat)", 73, 9.9, 3.9, 2.0, 0, 3.6, 1.3, 36),
    "skyr": _f("Skyr", 63, 11.0, 4.0, 0.2, 0, 4.0, 0.1, 40),
    "eggs": _f("Eggs", 143, 12.6, 0.7, 9.5, 0, 0.4, 3.1, 142, unit="egg", unit_g=50),
    "chicken": _f("Chicken breast, grilled", 165, 31.0, 0, 3.6, 0, 0, 1.0, 74),
    "salmon": _f("Salmon fillet, baked", 206, 22.0, 0, 13.0, 0, 0, 3.1, 61),
    "beef": _f("Lean beef mince, cooked", 217, 26.0, 0, 12.0, 0, 0, 4.7, 72),
    "tofu": _f("Tofu, firm", 144, 17.3, 2.8, 8.7, 2.3, 0.6, 1.3, 14),
    "turkey": _f("Turkey breast slices", 104, 22.0, 1.5, 1.2, 0, 1.0, 0.4, 950),
    "cottage": _f("Cottage cheese", 98, 11.1, 3.4, 4.3, 0, 2.7, 1.7, 364),
    "tuna": _f("Tuna in water, drained", 116, 25.5, 0, 0.8, 0, 0, 0.2, 340),
    "whey": _f(
        "Whey protein powder", 380, 78.0, 7.0, 5.0, 0, 5.0, 2.5, 200, unit="scoop", unit_g=30
    ),
    "lentils": _f("Lentils, cooked", 116, 9.0, 20.1, 0.4, 7.9, 1.8, 0.1, 2),
    "feta": _f("Feta", 264, 14.2, 4.1, 21.3, 0, 4.1, 15.0, 1116),
    "oats": _f("Rolled oats", 379, 13.2, 66.3, 6.5, 10.1, 1.0, 1.1, 6),
    "bread": _f(
        "Wholegrain bread", 247, 13.0, 41.0, 3.4, 7.0, 6.0, 0.7, 450, unit="slice", unit_g=40
    ),
    "spaghetti": _f("Spaghetti, cooked", 158, 5.8, 30.9, 0.9, 1.8, 0.6, 0.2, 1),
    "rice": _f("Rice, cooked", 130, 2.7, 28.2, 0.3, 0.4, 0.1, 0.1, 1),
    "potatoes": _f("Potatoes, boiled", 87, 1.9, 20.1, 0.1, 1.8, 0.9, 0, 5),
    "sweet_potato": _f("Sweet potato, baked", 90, 2.0, 20.7, 0.2, 3.3, 6.5, 0, 36),
    "wrap": _f(
        "Wheat tortilla wrap", 310, 8.3, 51.6, 7.5, 3.5, 2.5, 2.8, 650, unit="wrap", unit_g=60
    ),
    "couscous": _f("Couscous, cooked", 112, 3.8, 23.2, 0.2, 1.4, 0.1, 0, 5),
    "banana": _f("Banana", 89, 1.1, 22.8, 0.3, 2.6, 12.2, 0.1, 1, unit="piece", unit_g=120),
    "granola": _f("Granola", 471, 10.0, 64.0, 20.0, 7.0, 24.0, 3.0, 25),
    "honey": _f("Honey", 304, 0.3, 82.4, 0, 0.2, 82.0, 0, 4),
    "olive_oil": _f("Olive oil", 884, 0, 0, 100.0, 0, 0, 14.0, 2),
    "butter": _f("Butter", 717, 0.9, 0.1, 81.0, 0, 0.1, 51.0, 11),
    "peanut_butter": _f("Peanut butter", 588, 25.0, 20.0, 50.0, 6.0, 9.0, 10.0, 17),
    "almonds": _f("Almonds", 579, 21.2, 21.6, 49.9, 12.5, 4.4, 3.8, 1),
    "avocado": _f("Avocado", 160, 2.0, 8.5, 14.7, 6.7, 0.7, 2.1, 7),
    "cheese": _f("Gouda cheese", 356, 25.0, 2.2, 27.4, 0, 2.2, 17.6, 819, unit="slice", unit_g=25),
    "salad": _f("Mixed salad", 20, 1.3, 3.0, 0.2, 1.8, 1.8, 0, 20),
    "broccoli": _f("Broccoli, steamed", 35, 2.4, 7.2, 0.4, 3.3, 1.4, 0.1, 41),
    "tomato_sauce": _f("Tomato sauce", 50, 1.6, 8.0, 1.5, 1.9, 5.5, 0.2, 400),
    "veg": _f("Stir-fry vegetables", 40, 2.0, 7.0, 0.3, 2.5, 3.5, 0.1, 30),
    "berries": _f("Mixed berries", 50, 0.9, 11.9, 0.3, 3.2, 7.5, 0, 1),
    "apple": _f("Apple", 52, 0.3, 13.8, 0.2, 2.4, 10.4, 0, 1, unit="piece", unit_g=180),
    "milk": _f("Milk (1.5 % fat)", 47, 3.4, 4.8, 1.5, 0, 4.8, 1.0, 44, liquid=True),
    "coffee": _f("Coffee with milk", 15, 0.9, 1.2, 0.5, 0, 1.2, 0.3, 15, liquid=True),
    "beer": _f("Beer", 43, 0.5, 3.6, 0, 0, 0, 0, 4, alcohol=3.9, liquid=True),
    "wine": _f("Red wine", 85, 0.1, 2.6, 0, 0, 0.6, 0, 4, alcohol=10.6, liquid=True),
}

# (name, protein food, carbohydrate food, fat food, fixed sides in g)
Template = tuple[str, str, str, str, tuple[tuple[str, float], ...]]
BREAKFASTS: tuple[Template, ...] = (
    (
        "Porridge with berries and yoghurt",
        "greek_yoghurt",
        "oats",
        "almonds",
        (("berries", 100), ("milk", 150)),
    ),
    ("Scrambled eggs on wholegrain toast", "eggs", "bread", "butter", (("coffee", 250),)),
    ("Skyr bowl with granola and banana", "skyr", "granola", "peanut_butter", (("banana", 120),)),
    ("Wholegrain bread with cheese and turkey", "turkey", "bread", "cheese", (("coffee", 250),)),
)
LUNCHES: tuple[Template, ...] = (
    ("Chicken rice bowl", "chicken", "rice", "olive_oil", (("broccoli", 150),)),
    ("Lentil salad with couscous and feta", "lentils", "couscous", "feta", (("salad", 120),)),
    ("Tuna wrap with avocado", "tuna", "wrap", "avocado", (("salad", 60),)),
    ("Spaghetti bolognese", "beef", "spaghetti", "olive_oil", (("tomato_sauce", 150),)),
    ("Tofu stir-fry with rice", "tofu", "rice", "olive_oil", (("veg", 200),)),
)
DINNERS: tuple[Template, ...] = (
    ("Salmon with potatoes and broccoli", "salmon", "potatoes", "butter", (("broccoli", 150),)),
    (
        "Pasta with chicken and tomato sauce",
        "chicken",
        "spaghetti",
        "olive_oil",
        (("tomato_sauce", 150),),
    ),
    ("Beef with sweet potato and salad", "beef", "sweet_potato", "olive_oil", (("salad", 100),)),
    ("Chicken and vegetable stir-fry with rice", "chicken", "rice", "olive_oil", (("veg", 200),)),
    ("Lentil curry with rice", "lentils", "rice", "olive_oil", (("veg", 150),)),
)
# (name, foods with base grams): scaled as a whole to the snack's energy.
Snack = tuple[str, tuple[tuple[str, float], ...]]
SNACKS: tuple[Snack, ...] = (
    ("Apple and almonds", (("apple", 180), ("almonds", 25))),
    ("Banana and peanut butter", (("banana", 120), ("peanut_butter", 20))),
    ("Cottage cheese with berries", (("cottage", 200), ("berries", 100))),
    ("Greek yoghurt with honey", (("greek_yoghurt", 200), ("honey", 15))),
    ("Wholegrain bread with cheese", (("bread", 40), ("cheese", 25))),
)
RECOVERY: tuple[Snack, ...] = (
    ("Recovery shake", (("whey", 30), ("milk", 300), ("banana", 120))),
    ("Banana and skyr", (("banana", 120), ("skyr", 150))),
)
DRINKS: tuple[tuple[str, str, float], ...] = (
    ("Beer", "beer", 500),
    ("Glass of red wine", "wine", 200),
)
NOTES = (
    "Portions estimated from a photo.",
    "Assumed 1 tbsp olive oil for cooking.",
    "Weighed at home.",
    "Restaurant portion, estimated.",
)
# Portion limits per role (g), applied after scaling to the meal energy.
MIN_G = {"protein": 40.0, "carb": 40.0, "fat": 3.0}
MAX_G = {"protein": 300.0, "carb": 450.0, "fat": 45.0}


@dataclass
class _Meal:
    meal_type: str
    name: str
    at: datetime  # aware, local
    items: list[dict[str, Any]]
    extra: dict[str, float]


def _portion(food: Food, grams: float) -> tuple[float, float, str]:
    """(amount, grams, unit) rounded the way people log: whole/half units or 5 g steps."""
    if food.unit:
        amount = max(round(grams / food.unit_g * 2) / 2, 0.5)
        return amount, amount * food.unit_g, food.unit
    step = 1.0 if grams < 30 else 5.0
    g = max(round(grams / step) * step, step)
    return g, g, "ml" if food.liquid else "g"


def _item(key: str, grams: float) -> tuple[dict[str, Any], dict[str, float]]:
    food = F[key]
    amount, g, unit = _portion(food, grams)
    k = g / 100.0
    item = {
        "food": food.name,
        "amount": amount,
        "unit": unit,
        "grams": g,
        "kcal": round(food.kcal * k, 1),
        "protein_g": round(food.protein * k, 1),
        "carbs_g": round(food.carbs * k, 1),
        "fat_g": round(food.fat * k, 1),
        "fiber_g": round(food.fiber * k, 1),
    }
    extra = {
        "sugar_g": food.sugar * k,
        "saturated_fat_g": food.sat_fat * k,
        "sodium_mg": food.sodium_mg * k,
        "alcohol_g": food.alcohol * k,
        "water_ml": 0.9 * g if food.liquid else 0.0,
    }
    return item, extra


def _build(meal_type: str, name: str, at: datetime, parts: Sequence[tuple[str, float]]) -> _Meal:
    items: list[dict[str, Any]] = []
    extra: defaultdict[str, float] = defaultdict(float)
    for key, grams in parts:
        item, ex = _item(key, grams)
        items.append(item)
        for k, v in ex.items():
            extra[k] += v
    return _Meal(meal_type, name, at, items, dict(extra))


def _solve(
    tpl: Template, kcal: float, shares: tuple[float, float, float], rng: np.random.Generator
) -> list[tuple[str, float]]:
    """Grams of the template's foods so the meal hits kcal and roughly the macro shares."""
    _, pk, ck, fk, sides = tpl
    side_parts = [(key, g * float(rng.uniform(0.85, 1.15))) for key, g in sides]
    side = sum((F[k].macros() * g for k, g in side_parts), np.zeros(3))
    side_kcal = sum(F[k].kcal * g / 100 for k, g in side_parts)
    target = np.array([kcal * shares[0] / 4, kcal * shares[1] / 4, kcal * shares[2] / 9]) - side
    mains = (pk, ck, fk)
    a = np.column_stack([F[k].macros() for k in mains])
    grams = np.linalg.lstsq(a, target, rcond=None)[0]
    roles = ("protein", "carb", "fat")
    grams = np.array([np.clip(g, MIN_G[r], MAX_G[r]) for g, r in zip(grams, roles, strict=True)])
    main_kcal = sum(F[k].kcal * g / 100 for k, g in zip(mains, grams, strict=True))
    scale = float(np.clip((kcal - side_kcal) / max(main_kcal, 1.0), 0.6, 1.6))
    final = [
        float(np.clip(g * scale, MIN_G[r], MAX_G[r])) for g, r in zip(grams, roles, strict=True)
    ]
    return [*zip(mains, final, strict=True), *side_parts]


def _scaled(snack: Snack, kcal: float) -> list[tuple[str, float]]:
    base = sum(F[k].kcal * g / 100 for k, g in snack[1])
    return [(k, g * kcal / base) for k, g in snack[1]]


def _at(day: date, hour: float, tz: ZoneInfo) -> datetime:
    minutes = round(hour * 60)
    return datetime.combine(day, time(), tz) + timedelta(minutes=minutes)


def _day_kind(acts: list[dict[str, Any]]) -> str:
    if any(
        (a["duration_s"] or 0) >= 120 * 60
        or (a["sport_group"] == "run" and (a["duration_s"] or 0) >= 75 * 60)
        for a in acts
    ):
        return "long"
    return "training" if acts else "rest"


def _day_meals(
    day: date,
    burn: float,
    weight: float,
    acts: list[dict[str, Any]],
    deficit: float,
    tz: ZoneInfo,
    rng: np.random.Generator,
) -> list[_Meal]:
    weekend = day.weekday() >= 5
    intake = burn + deficit + float(rng.normal(0, 170)) + (60 if day.weekday() == 5 else 0)
    intake = max(intake, 1400.0)
    kind = _day_kind(acts)
    carb_share = {"long": 0.57, "training": 0.50, "rest": 0.44}[kind] + float(rng.normal(0, 0.02))
    protein = weight * float(rng.uniform(1.5, 1.9))
    meals: list[_Meal] = []

    drink_p = 0.3 if day.weekday() in (4, 5) else 0.04
    if rng.random() < drink_p:
        label, key, ml = DRINKS[int(rng.integers(len(DRINKS)))]
        meals.append(_build("drink", label, _at(day, 20.6 + rng.normal(0, 0.3), tz), [(key, ml)]))
    food_kcal = intake - sum(float(i["kcal"]) for x in meals for i in x.items)
    p_share = float(np.clip(4 * protein / food_kcal, 0.15, 0.32))
    shares = (p_share, carb_share, max(1.0 - p_share - carb_share, 0.18))

    slots: list[tuple[str, float, float]] = [  # meal type, weight, local hour
        ("breakfast", 24, (8.75 if weekend else 7.0) + rng.normal(0, 0.4)),
        ("lunch", 31, 12.5 + rng.normal(0, 0.5)),
        ("dinner", 33, 19.0 + rng.normal(0, 0.55)),
    ]
    longest = max(acts, key=lambda a: a["duration_s"] or 0, default=None)
    recovery_at: float | None = None
    if longest is not None:
        end = longest["start_time_local"] + timedelta(seconds=longest["duration_s"] or 0)
        end_h = end.hour + end.minute / 60
        if end.date() == day and 8 <= end_h < 20 and rng.random() < 0.6:
            recovery_at = end_h + float(rng.uniform(0.3, 0.8))
            slots.append(("recovery", 13, recovery_at))
    if recovery_at is None and rng.random() < 0.65:
        slots.append(("snack", 11, 15.75 + rng.normal(0, 0.5)))
    if len(meals) == 0 and rng.random() < 0.25:
        slots.append(("snack", 9, 21.25 + rng.normal(0, 0.3)))
    weights = np.array([w * float(rng.uniform(0.85, 1.15)) for _, w, _ in slots])
    weights /= weights.sum()

    templates = {"breakfast": BREAKFASTS, "lunch": LUNCHES, "dinner": DINNERS}
    for (slot, _, hour), share in zip(slots, weights, strict=True):
        kcal = food_kcal * float(share)
        at = _at(day, hour, tz)
        if slot in templates:
            options = templates[slot]
            tpl = options[int(rng.integers(len(options)))]
            if kind == "long" and slot == "dinner":
                tpl = DINNERS[1]  # pasta the evening after a long run
            meals.append(_build(slot, tpl[0], at, _solve(tpl, kcal, shares, rng)))
        else:
            pool = RECOVERY if slot == "recovery" else SNACKS
            snack = pool[int(rng.integers(len(pool)))]
            meals.append(_build("snack", snack[0], at, _scaled(snack, kcal)))
    return sorted(meals, key=lambda x: x.at)


def _meal_row(meal: _Meal, rng: np.random.Generator) -> dict[str, Any]:
    def total(key: str) -> float:
        return round(sum(float(i[key]) for i in meal.items), 1)

    confidence = str(rng.choice(["high", "medium", "low"], p=[0.35, 0.5, 0.15]))
    note = NOTES[int(rng.integers(len(NOTES)))] if rng.random() < 0.3 else None
    if note == "Weighed at home.":
        confidence = "high"
    at_utc = meal.at.astimezone(UTC)
    extra = meal.extra
    return {
        "eaten_at": at_utc,
        "day": meal.at.date(),
        "meal_type": meal.meal_type,
        "name": meal.name,
        "kcal": total("kcal"),
        "protein_g": total("protein_g"),
        "carbs_g": total("carbs_g"),
        "fat_g": total("fat_g"),
        "fiber_g": total("fiber_g"),
        "sugar_g": round(extra["sugar_g"], 1),
        "saturated_fat_g": round(extra["saturated_fat_g"], 1),
        "sodium_mg": round(extra["sodium_mg"]),
        "alcohol_g": round(extra["alcohol_g"], 1) or None,
        "water_ml": round(extra["water_ml"]) or None,
        "notes": note,
        "source": "demo",
        "confidence": confidence,
        "created_at": at_utc + timedelta(minutes=int(rng.integers(2, 40))),
        "updated_at": at_utc + timedelta(minutes=45),
    }


def write_demo_meals(
    session: Session,
    summaries: Sequence[dict[str, Any]],
    act_rows: Sequence[dict[str, Any]],
    weights: dict[date, float],
    tz: ZoneInfo,
    seed: int,
    *,
    now: datetime | None = None,
) -> dict[str, int]:
    """Insert the demo food diary; meals after ``now`` (today's dinner, say) are left out."""
    rng = np.random.default_rng([seed, MEAL_STREAM])
    now = now or datetime.now(UTC)
    days = max(len(summaries), 1)
    deficit = float(np.clip(-DEMO_LOSS_KG * WEEKLY_LOSS_KCAL_PER_KG / days, -300.0, -25.0))
    acts_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for a in act_rows:
        acts_by_day[a["start_time_local"].date()].append(a)

    meal_rows: list[dict[str, Any]] = []
    meal_items: list[list[dict[str, Any]]] = []
    for row in summaries:
        day: date = row["day"]
        burn = row.get("total_kcal")
        if burn is None or math.isnan(float(burn)) or rng.random() < SKIP_DAY_P:
            continue
        weight = weights.get(day, 72.0)
        for meal in _day_meals(day, float(burn), weight, acts_by_day[day], deficit, tz, rng):
            if meal.at.astimezone(UTC) > now:
                continue
            meal_rows.append(_meal_row(meal, rng))
            meal_items.append(meal.items)
    if not meal_rows:
        return {"meal": 0, "meal_item": 0}
    ids = session.scalars(
        insert(m.Meal).returning(m.Meal.meal_id, sort_by_parameter_order=True), meal_rows
    ).all()
    item_rows = [
        {"meal_id": meal_id, "idx": idx, **item}
        for meal_id, items in zip(ids, meal_items, strict=True)
        for idx, item in enumerate(items)
    ]
    session.execute(insert(m.MealItem), item_rows)
    return {"meal": len(meal_rows), "meal_item": len(item_rows)}
