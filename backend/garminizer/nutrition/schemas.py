"""Input and output models of the nutrition service, shared by the API and the MCP server.

Energy in kcal, nutrients in grams (sodium in mg, water in ml). ``day`` is the athlete's local
calendar date; ``eaten_at`` carries the athlete's local UTC offset.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MealType = Literal["breakfast", "lunch", "dinner", "snack", "drink"]
MealSource = Literal["claude", "manual", "demo"]
Confidence = Literal["low", "medium", "high"]

MACRO_FIELDS = ("protein_g", "carbs_g", "fat_g", "fiber_g")
ITEM_NUTRIENTS = ("kcal", *MACRO_FIELDS)
EXTRA_NUTRIENTS = ("sugar_g", "saturated_fat_g", "sodium_mg", "alcohol_g", "water_ml")
MEAL_NUTRIENTS = (*ITEM_NUTRIENTS, *EXTRA_NUTRIENTS)
TARGET_FIELDS = ("kcal", *MACRO_FIELDS, "protein_g_per_kg")


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- input -----------------------------------------------------------------------------------


class NutritionItemIn(_In):
    """One food or drink of a meal: portion and the nutrients of that portion."""

    food: str = Field(min_length=1, max_length=200, description="Food, e.g. 'cooked spaghetti'")
    amount: float | None = Field(
        default=None, ge=0, le=100_000, description="Portion in `unit`, e.g. 1.5 (slices)"
    )
    unit: str | None = Field(
        default=None, max_length=30, description="Unit of amount: g, ml, piece, slice, cup, tbsp"
    )
    grams: float | None = Field(
        default=None, ge=0, le=10_000, description="Estimated portion weight in grams"
    )
    kcal: float = Field(ge=0, le=10_000, description="Energy of this portion (kcal)")
    protein_g: float | None = Field(default=None, ge=0, le=2000, description="Protein (g)")
    carbs_g: float | None = Field(default=None, ge=0, le=2000, description="Carbohydrates (g)")
    fat_g: float | None = Field(default=None, ge=0, le=2000, description="Fat (g)")
    fiber_g: float | None = Field(default=None, ge=0, le=2000, description="Dietary fibre (g)")


class NutritionTotalsIn(_In):
    """Meal totals; every value given here wins over the sum of the items."""

    kcal: float | None = Field(default=None, ge=0, le=20_000, description="Energy (kcal)")
    protein_g: float | None = Field(default=None, ge=0, le=2000, description="Protein (g)")
    carbs_g: float | None = Field(default=None, ge=0, le=2000, description="Carbohydrates (g)")
    fat_g: float | None = Field(default=None, ge=0, le=2000, description="Fat (g)")
    fiber_g: float | None = Field(default=None, ge=0, le=2000, description="Dietary fibre (g)")
    sugar_g: float | None = Field(default=None, ge=0, le=2000, description="Sugars (g)")
    saturated_fat_g: float | None = Field(
        default=None, ge=0, le=2000, description="Saturated fat (g)"
    )
    sodium_mg: float | None = Field(default=None, ge=0, le=50_000, description="Sodium (mg)")
    alcohol_g: float | None = Field(default=None, ge=0, le=2000, description="Alcohol (g)")
    water_ml: float | None = Field(default=None, ge=0, le=10_000, description="Water (ml)")


class NutritionMealIn(_In):
    """A meal to log: either items (totals are their sum) or totals.kcal, or both."""

    name: str = Field(min_length=1, max_length=200, description="Short name of the meal")
    eaten_at: datetime | None = Field(
        default=None,
        description="When it was eaten; without a UTC offset it is the athlete's local time "
        "(default: now)",
    )
    meal_type: MealType | None = Field(
        default=None, description="Inferred from the local time of day when missing"
    )
    items: list[NutritionItemIn] = Field(default_factory=list, max_length=60)
    totals: NutritionTotalsIn | None = None
    notes: str | None = Field(default=None, max_length=2000, description="Assumptions made")
    confidence: Confidence | None = None

    @model_validator(mode="after")
    def _energy_known(self) -> NutritionMealIn:
        if not self.items and (self.totals is None or self.totals.kcal is None):
            raise ValueError("give the foods as items (each with kcal) or totals.kcal")
        return self


class NutritionMealPatch(_In):
    """Changes to a meal; fields left out stay as they are.

    ``items`` replaces all items and recomputes kcal and macros from them (unless given in
    ``totals``); an empty list removes the items but keeps the totals. ``notes`` and
    ``confidence`` can be cleared with null.
    """

    name: str | None = Field(default=None, min_length=1, max_length=200)
    eaten_at: datetime | None = None
    meal_type: MealType | None = None
    items: list[NutritionItemIn] | None = Field(default=None, max_length=60)
    totals: NutritionTotalsIn | None = None
    notes: str | None = Field(default=None, max_length=2000)
    confidence: Confidence | None = None


class NutritionTargets(_In):
    """Daily targets (app setting ``nutrition_targets``); null = no target."""

    kcal: float | None = Field(default=None, gt=0, le=10_000, description="Energy (kcal/day)")
    protein_g: float | None = Field(default=None, ge=0, le=1000, description="Protein (g/day)")
    carbs_g: float | None = Field(default=None, ge=0, le=2000, description="Carbs (g/day)")
    fat_g: float | None = Field(default=None, ge=0, le=1000, description="Fat (g/day)")
    fiber_g: float | None = Field(default=None, ge=0, le=500, description="Fibre (g/day)")
    protein_g_per_kg: float | None = Field(
        default=None,
        gt=0,
        le=5,
        description="Protein per kg body weight; used when protein_g is not set",
    )


# --- output ----------------------------------------------------------------------------------


class NutritionWarning(_Out):
    code: str = Field(description="macro_kcal_mismatch | items_kcal_mismatch")
    message: str


class NutritionMealItem(_Out):
    idx: int
    food: str
    amount: float | None
    unit: str | None
    grams: float | None
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


class NutritionMeal(_Out):
    meal_id: int
    eaten_at: datetime = Field(description="With the athlete's local UTC offset")
    day: date
    meal_type: MealType
    name: str
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    saturated_fat_g: float | None
    sodium_mg: float | None
    alcohol_g: float | None
    water_ml: float | None
    notes: str | None
    source: MealSource
    confidence: Confidence | None
    created_at: datetime
    updated_at: datetime
    items: list[NutritionMealItem]
    warnings: list[NutritionWarning]


class NutritionTotals(_Out):
    """Sum over the meals of a day (macros: null when no meal has a value)."""

    meals: int
    kcal: float
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    sugar_g: float | None
    saturated_fat_g: float | None
    sodium_mg: float | None
    alcohol_g: float | None
    water_ml: float | None


class NutritionGarminEnergy(_Out):
    """Energy expenditure from Garmin's daily summary (so far, for today)."""

    total_kcal: float | None
    active_kcal: float | None
    bmr_kcal: float | None


class NutritionRemaining(_Out):
    """Target minus intake (negative = above the target); null without a target."""

    kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None


class NutritionDaySummary(_Out):
    day: date
    is_today: bool = Field(description="Today: intake and Garmin burn are still growing")
    totals: NutritionTotals
    targets: NutritionTargets
    protein_target_g: float | None = Field(
        description="protein_g target, or protein_g_per_kg x weight"
    )
    remaining: NutritionRemaining
    garmin: NutritionGarminEnergy
    balance_kcal: float | None = Field(
        description="Intake minus Garmin total burn; null without meals or Garmin data"
    )
    weight_kg: float | None = Field(description="Latest weigh-in on or before the day")
    protein_g_per_kg: float | None


class NutritionDay(NutritionDaySummary):
    meals: list[NutritionMeal]


class NutritionDailyPoint(_Out):
    day: date
    meals: int
    intake_kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    fiber_g: float | None
    alcohol_g: float | None
    total_kcal: float | None = Field(description="Garmin total burn")
    active_kcal: float | None = Field(description="Garmin active burn")
    balance_kcal: float | None = Field(description="intake_kcal - total_kcal")


class NutritionMacroSplit(_Out):
    """Share of the energy from protein (4 kcal/g), carbs (4), fat (9) and alcohol (7), in %."""

    protein_pct: float | None
    carbs_pct: float | None
    fat_pct: float | None
    alcohol_pct: float | None


class NutritionWeek(_Out):
    """Averages per logged day of an ISO week (Monday first), for correlations."""

    week: date
    days_logged: int
    intake_kcal: float | None
    total_kcal: float | None
    balance_kcal: float | None
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    weight_kg: float | None = Field(description="Mean of the week's weigh-ins")


class NutritionMealTypeStat(_Out):
    meal_type: MealType
    meals: int
    kcal_pct: float = Field(description="Share of all logged energy in the range (%)")


class NutritionSummary(_Out):
    start: date
    end: date
    days: int
    days_logged: int
    meals: int
    avg_intake_kcal: float | None = Field(description="Per logged day")
    avg_protein_g: float | None
    avg_carbs_g: float | None
    avg_fat_g: float | None
    avg_fiber_g: float | None
    avg_total_kcal: float | None = Field(description="Garmin total burn on logged days")
    avg_active_kcal: float | None
    avg_balance_kcal: float | None = Field(description="Over logged days with Garmin data")
    weight_kg: float | None = Field(description="Latest weigh-in on or before the end")
    protein_g_per_kg: float | None = Field(description="avg_protein_g / weight_kg")
    macro_split: NutritionMacroSplit
    by_meal_type: list[NutritionMealTypeStat]
    targets: NutritionTargets
    protein_target_g: float | None
    weeks: list[NutritionWeek]


class NutritionActivity(_Out):
    activity_id: int
    name: str | None
    sport_group: str
    sport_type: str
    start_time_local: datetime
    duration_s: float | None
    distance_m: float | None
    calories: float | None
    training_load: float | None


class NutritionEnergyContext(_Out):
    """What Garmin knows about a day's energy expenditure and training."""

    day: date
    is_today: bool
    demo_data: bool = Field(description="True when the database holds the synthetic demo athlete")
    garmin: NutritionGarminEnergy
    steps: int | None
    activities: list[NutritionActivity]
    training_load: float | None = Field(description="Garmin training load of the day")
    fitness_ctl: float | None
    fatigue_atl: float | None
    form_tsb: float | None
    training_status: str | None
    readiness: int | None
    avg_total_kcal_7d: float | None = Field(description="Mean Garmin burn of the 7 days before")
    intake: NutritionTotals
    balance_kcal: float | None
