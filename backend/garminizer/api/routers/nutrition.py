"""Nutrition: logged meals (calories, macros) against Garmin's energy expenditure.

Meals usually arrive from Claude Desktop through the MCP server (`garminizer mcp`); the write
endpoints below let the dashboard add, correct and delete them as well. Without explicit
``start``/``end`` the range ends at the last day with Garmin data or a logged meal.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from garminizer.api.deps import DateRange, SessionDep, data_bounds
from garminizer.nutrition import service
from garminizer.nutrition.schemas import (
    NutritionDailyPoint,
    NutritionDay,
    NutritionMeal,
    NutritionMealIn,
    NutritionMealPatch,
    NutritionSummary,
    NutritionTargets,
)

router = APIRouter(prefix="/api/nutrition", tags=["nutrition"])

MEALS_DEFAULT_DAYS = 7
StartQuery = Annotated[date | None, Query(description="First day (default: 1 year before end)")]
EndQuery = Annotated[
    date | None, Query(description="Last day (default: last day with Garmin data or meals)")
]


def fallback_tz(request: Request) -> str:
    """Time zone used when the athlete profile has none (setting TZ)."""
    return str(request.app.state.settings.tz)


TzDep = Annotated[str, Depends(fallback_tz)]


def _last_day(session: SessionDep) -> date:
    candidates = [d for d in (data_bounds(session)[1], service.last_meal_day(session)) if d]
    return max(candidates) if candidates else date.today()


def nutrition_range(
    session: SessionDep, start: StartQuery = None, end: EndQuery = None
) -> DateRange:
    """Like the shared range filter, but the default end also covers days with only meals."""
    end = end or _last_day(session)
    start = start or end - timedelta(days=364)
    if start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")
    return DateRange(start, end)


NutritionRangeDep = Annotated[DateRange, Depends(nutrition_range)]


@router.get("/daily", response_model=list[NutritionDailyPoint])
def daily(session: SessionDep, rng: NutritionRangeDep) -> list[NutritionDailyPoint]:
    """Per day: intake (kcal, macros, fibre), Garmin total/active burn, balance, meal count.

    Only days with logged meals or Garmin calories are listed.
    """
    return service.daily_series(session, rng.start, rng.end)


@router.get("/summary", response_model=NutritionSummary)
def summary(session: SessionDep, rng: NutritionRangeDep, tz: TzDep) -> NutritionSummary:
    """Averages per logged day, macro energy split, protein per kg, targets, weekly means."""
    return service.summary(session, rng.start, rng.end, fallback_tz=tz)


@router.get("/day", response_model=NutritionDay)
def day(
    session: SessionDep,
    tz: TzDep,
    day: Annotated[date | None, Query(description="Day (default: today, athlete's time)")] = None,
) -> NutritionDay:
    """One day: meals with items, totals, targets and what is left, Garmin burn, balance."""
    return service.get_day(session, day or service.local_today(session, tz), fallback_tz=tz)


@router.get("/meals", response_model=list[NutritionMeal])
def meals(
    session: SessionDep,
    tz: TzDep,
    day: Annotated[date | None, Query(description="Only this day")] = None,
    start: Annotated[date | None, Query(description="First day (default: end - 6 days)")] = None,
    end: EndQuery = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
) -> list[NutritionMeal]:
    """Meals with their items, oldest first (``day`` or ``start``/``end``)."""
    if day is not None:
        start = end = day
    end = end or _last_day(session)
    start = start or end - timedelta(days=MEALS_DEFAULT_DAYS - 1)
    if start > end:
        raise HTTPException(status_code=422, detail="start must not be after end")
    return service.list_meals(session, start, end, fallback_tz=tz, limit=limit)


@router.post("/meals", response_model=NutritionMeal, status_code=201)
def create_meal(session: SessionDep, tz: TzDep, body: NutritionMealIn) -> NutritionMeal:
    """Log a meal by hand (source ``manual``); totals are the sum of the items unless given."""
    try:
        meal = service.log_meal(session, body, source="manual", fallback_tz=tz)
    except service.NutritionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return meal


@router.patch("/meals/{meal_id}", response_model=NutritionMeal)
def patch_meal(
    session: SessionDep, tz: TzDep, meal_id: int, body: NutritionMealPatch
) -> NutritionMeal:
    """Change a meal; ``items`` replaces all items and recomputes kcal and macros."""
    try:
        meal = service.update_meal(session, meal_id, body, fallback_tz=tz)
    except service.MealNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.NutritionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return meal


@router.delete("/meals/{meal_id}", status_code=204, response_class=Response)
def remove_meal(session: SessionDep, meal_id: int) -> Response:
    """Delete a meal and its items."""
    try:
        service.delete_meal(session, meal_id)
    except service.MealNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    session.commit()
    return Response(status_code=204)


@router.get("/targets", response_model=NutritionTargets)
def get_targets(session: SessionDep) -> NutritionTargets:
    """Daily targets; null fields have no target."""
    return service.get_targets(session)


@router.put("/targets", response_model=NutritionTargets)
def put_targets(session: SessionDep, body: NutritionTargets) -> NutritionTargets:
    """Replace all targets (omitted fields are cleared)."""
    stored = service.set_targets(session, body)
    session.commit()
    return stored
