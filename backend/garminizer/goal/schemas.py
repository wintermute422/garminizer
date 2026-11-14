"""Input and output models of the weight goal, shared by the API and the MCP server.

Weights in kg, energy in kcal, nutrients in grams; ``day`` is the athlete's local calendar date.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from garminizer.analytics.goal import DEFAULT_TREND_WEIGHTS, SUNDAY

Sex = Literal["male", "female"]
AnchorKind = Literal["start", "reached", "accepted"]
CheckpointStatus = Literal["reached", "accepted", "missed", "no_weigh_in", "upcoming"]
BmrSource = Literal["formulas", "garmin"]
DEFAULT_ACTIVITY_FACTOR = 1.25


class _Out(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- input -----------------------------------------------------------------------------------


class _GoalFields(_In):
    start_weight_kg: float = Field(ge=20, le=400, description="Weight on the start day (kg)")
    rate_kg_per_week: float = Field(gt=0, le=2, description="Planned loss per week (kg)")
    checkpoint_weekday: int = Field(
        default=SUNDAY, ge=0, le=6, description="Checkpoint weekday: 0 = Monday .. 6 = Sunday"
    )
    accepted_checkpoints: list[date] = Field(
        default_factory=list,
        max_length=520,
        description="Checkpoints counted as reached although the trend was above the target",
    )
    activity_factor: float = Field(
        default=DEFAULT_ACTIVITY_FACTOR,
        ge=1.0,
        le=2.5,
        description="Resting energy x this = everyday burn without training (1.2 desk job)",
    )
    trend_weights: list[float] = Field(
        default_factory=lambda: list(DEFAULT_TREND_WEIGHTS),
        min_length=1,
        max_length=14,
        description="Trend weights for today, yesterday, ... (default 3, 2, 1)",
    )
    sex: Sex | None = Field(default=None, description="For the BMR formulas; default: profile")
    height_cm: float | None = Field(
        default=None, ge=100, le=250, description="For the BMR formulas; default: profile"
    )
    birth_date: date | None = Field(
        default=None, description="For the BMR formulas (age); default: profile"
    )

    @field_validator("trend_weights")
    @classmethod
    def _positive_weights(cls, value: list[float]) -> list[float]:
        if any(w <= 0 for w in value):
            raise ValueError("trend weights must be positive")
        return value

    @field_validator("accepted_checkpoints")
    @classmethod
    def _sorted_unique(cls, value: list[date]) -> list[date]:
        return sorted(set(value))


class GoalSettings(_GoalFields):
    """The weight goal (app setting ``weight_goal``)."""

    start_day: date = Field(description="First day of the programme")
    end_day: date = Field(description="Last day of the programme")

    @model_validator(mode="after")
    def _end_after_start(self) -> GoalSettings:
        if self.end_day <= self.start_day:
            raise ValueError("end_day must be after start_day")
        return self


class GoalCheckpointIn(_In):
    accepted: bool = Field(description="Count this checkpoint as reached")


# --- output ----------------------------------------------------------------------------------


class GoalProfile(_Out):
    """BMR inputs from the Garmin profile (used where the goal settings leave them empty)."""

    sex: Sex | None
    height_cm: float | None
    birth_date: date | None


class GoalBmr(_Out):
    """Resting energy (kcal/day) of one day and what it was computed from."""

    source: BmrSource = Field(description="formulas, or Garmin's BMR when inputs are missing")
    kcal: float
    mifflin_st_jeor: float | None
    harris_benedict: float | None
    katch_mcardle: float | None = Field(description="Needs a body-fat value")
    weight_kg: float | None
    body_fat_pct: float | None
    height_cm: float | None
    age_years: int | None
    sex: Sex | None
    missing: list[str] = Field(description="Inputs that were missing for the formulas")


class GoalActivity(_Out):
    activity_id: int
    name: str | None
    sport_type: str
    sport_group: str
    start_time_local: datetime
    duration_s: float | None
    distance_m: float | None
    avg_hr: int | None
    calories: float | None = Field(description="Garmin's total calories (resting share included)")
    active_kcal: float | None = Field(description="Calories minus the resting share")


class GoalDay(_Out):
    day: date
    weight_kg: float | None = Field(description="First weigh-in of the day with body composition")
    trend_kg: float | None
    target_kg: float | None
    delta_kg: float | None = Field(description="Trend minus target (positive = above)")
    on_plan: bool | None
    body_fat_pct: float | None
    muscle_mass_kg: float | None
    body_water_pct: float | None
    intake_kcal: float | None = Field(description="Logged food; null without meals")
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    meals: int
    meal_names: list[str]
    sport_kcal: float | None = Field(description="Garmin calories of all activities (total)")
    training_kcal: float | None = Field(description="Active calories of all activities")
    baseline_kcal: float | None = Field(description="BMR x activity factor")
    burn_kcal: float | None = Field(description="Baseline + training")
    balance_kcal: float | None = Field(description="Intake - burn; null without meals")
    garmin_total_kcal: float | None = Field(description="Garmin's own total burn (comparison)")
    activities: list[GoalActivity]


class GoalAnchor(_Out):
    day: date
    weight_kg: float
    kind: AnchorKind


class GoalCheckpoint(_Out):
    day: date
    target_kg: float
    trend_kg: float | None
    status: CheckpointStatus


class GoalLinePoint(_Out):
    day: date
    target_kg: float


class GoalFatPoint(_Out):
    day: date
    body_fat_pct: float
    trend_pct: float = Field(description="EWMA, half-life 4 days")


class GoalRegression(_Out):
    start_day: date
    end_day: date
    start_pct: float
    end_pct: float
    slope_pct_per_week: float
    points: int


class GoalWeek(_Out):
    """The 7 days ending on a day: only days with logged meals count."""

    start: date
    end: date
    days_logged: int
    intake_kcal: float | None
    burn_kcal: float | None
    balance_kcal: float | None
    target_balance_kcal: float | None = Field(description="Daily target x days logged")


class GoalStatus(_Out):
    as_of: date | None = Field(description="Latest day with a trend")
    trend_kg: float | None
    target_kg: float | None = Field(description="Target on as_of")
    delta_kg: float | None
    on_plan: bool | None
    since_start_kg: float | None = Field(description="Trend minus start weight")
    target_today_kg: float | None
    target_end_kg: float | None = Field(description="Target on the last day (current anchors)")
    days_left: int
    next_checkpoint: GoalCheckpoint | None
    body_fat_pct: float | None
    body_fat_day: date | None
    muscle_mass_kg: float | None
    body_water_pct: float | None
    week: GoalWeek


class GoalView(_Out):
    configured: bool
    today: date
    settings: GoalSettings | None
    profile: GoalProfile
    target_daily_balance_kcal: float | None = Field(description="-rate x 7700 / 7")
    status: GoalStatus | None
    days: list[GoalDay] = Field(description="Every day from the start up to today, oldest first")
    anchors: list[GoalAnchor]
    checkpoints: list[GoalCheckpoint]
    target_line: list[GoalLinePoint] = Field(
        description="Start and end point of every anchor segment, up to the end day"
    )
    body_fat: list[GoalFatPoint]
    body_fat_regression: GoalRegression | None
    bmr_today: GoalBmr | None


class GoalEnergyBalance(_Out):
    """One day's energy balance: intake against the computed burn (not Garmin's estimate)."""

    day: date
    is_today: bool
    as_of: str | None = Field(description="Local time HH:MM for today")
    intake_kcal: float = Field(description="Logged food so far")
    meals: int
    protein_g: float | None
    carbs_g: float | None
    fat_g: float | None
    bmr: GoalBmr | None
    activity_factor: float
    baseline_kcal: float | None = Field(description="Rest + everyday life, without training")
    activities: list[GoalActivity]
    training_kcal: float = Field(description="Active calories of the activities")
    burn_kcal: float | None = Field(description="Baseline + training")
    balance_kcal: float | None = Field(description="Intake - burn (negative = deficit)")
    target_balance_kcal: float | None = Field(description="Daily balance the goal needs")
    left_to_target_kcal: float | None = Field(
        description="What can still be eaten today to end on the target balance"
    )
    garmin_total_kcal: float | None = Field(description="Garmin's own estimate (comparison)")
    week: GoalWeek
    goal_configured: bool
