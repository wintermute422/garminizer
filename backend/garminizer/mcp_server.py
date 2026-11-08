"""MCP server for Claude Desktop: log meals and compare intake with Garmin's energy expenditure.

`garminizer mcp` serves the Model Context Protocol over stdio. Claude Desktop starts it as a
subprocess and speaks JSON-RPC over stdin/stdout, so nothing else may ever reach stdout: logging
goes to stderr, and while serving the SDK points fd 1 at stderr. Claude does the food
recognition and the nutrient estimate; this server validates and stores the result locally and
answers with the day so far. See docs/claude-desktop.md.
"""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Annotated, Any
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker

from garminizer import __version__
from garminizer.nutrition import service
from garminizer.nutrition.schemas import (
    Confidence,
    MealType,
    NutritionItemIn,
    NutritionMeal,
    NutritionMealIn,
    NutritionMealPatch,
    NutritionTargets,
    NutritionTotalsIn,
)

log = logging.getLogger("garminizer.mcp")
Clock = Callable[[], datetime]

INSTRUCTIONS = """\
Garminizer is the user's own local Garmin data warehouse. With these tools you keep their food
diary: when the user shows or describes something they ate or drank, estimate foods, portions,
calories and macros yourself and store it with log_meal. Then compare what they ate with the
energy Garmin measured (get_day_nutrition, get_energy_context). Energy is in kcal, nutrients in
grams, times are the athlete's local time. Fix a wrong entry with update_meal instead of
logging it twice; check list_recent_meals first when the user refers to an earlier meal. The
numbers are estimates: say so briefly, never invent meals the user did not mention, and give
no medical advice beyond general sports-nutrition guidance."""

ESTIMATION_GUIDE = """\
How to estimate (photo or description):
1. Identify every food and drink separately: main components, sides, bread, sauces, dressings,
   toppings, cooking fat and sugary drinks. Hidden calories matter most: frying oil or butter
   (1 tbsp oil = 13.5 g = about 120 kcal), dressings, mayonnaise, cheese, nuts, sugar in coffee.
2. Estimate each portion in grams (cooked weight for cooked food). Visual cues: a dinner plate
   is about 26-27 cm across, a side plate 20 cm, a fork 19 cm; a palm-sized piece of meat or
   fish is 100-120 g, a fist of cooked rice or pasta 150-180 g, a thumb of butter or peanut
   butter about 15 g. Read package labels when they are visible.
3. Take nutrient values per 100 g from standard references (USDA FoodData Central, the German
   BLS, or the label) and scale them to the portion. Per item give kcal, protein_g, carbs_g,
   fat_g and fiber_g; 4 x protein + 4 x carbs + 9 x fat (+ 7 x alcohol) should be close to kcal.
4. Call log_meal once per meal with one entry per food in `items`; meal totals are the sum of
   the items. Use `totals` only for values you know better (a label) or for nutrients the items
   lack (sugar_g, saturated_fat_g, sodium_mg, alcohol_g, water_ml).
5. Put your assumptions in `notes` (e.g. 'assumed 1 tbsp olive oil, 180 g cooked pasta') and
   set `confidence`: high = weighed or from a label, medium = clear photo or description,
   low = rough guess.
6. `eaten_at` is the local time the meal was eaten ('HH:MM' for today or 'YYYY-MM-DDTHH:MM');
   leave it out for 'just now'. meal_type is inferred from the time when missing."""

LOG_MEAL = f"""\
Store a meal, snack or drink the user had, with the calories and macros YOU estimated.

{ESTIMATION_GUIDE}

Returns the stored meal (meal_id, totals, items), warnings (macro_kcal_mismatch when the macros
do not add up to the kcal: the meal is stored anyway, consider fixing it with update_meal) and
the day so far: intake against the targets, what is left, Garmin's calories burned so far and
the energy balance (intake minus burn). Tell the user the totals briefly, mention the main
assumptions and offer to correct portions with update_meal(meal_id, ...)."""

GET_DAY = """\
One day of the food diary: every meal with its items and meal_id, the day's totals (kcal,
protein, carbs, fat, fibre, ...), the targets and what is left, Garmin's calories burned
(total, active, BMR; for today: so far), the energy balance (intake minus Garmin's total burn;
negative = deficit), body weight and protein per kg."""

LIST_RECENT = """\
Meals of the last `days` days (newest first), grouped by day with day totals, each meal with
meal_id, local time, type, kcal, macros and a short item list. Use it to find a meal to update
or delete, or to look at eating patterns."""

UPDATE_MEAL = """\
Correct a logged meal. Only the arguments you pass change. `items` replaces ALL items of the
meal and recomputes kcal and macros from them (unless you pass `totals`); pass the complete new
item list. Moving `eaten_at` to another day moves the meal there. Returns the updated meal,
warnings and the summary of its day."""

DELETE_MEAL = """\
Delete a logged meal (and its items) by meal_id, e.g. when it was logged twice. Ask the user
first unless they asked for it. Returns the deleted meal and the new summary of its day."""

GET_TARGETS = """\
The user's daily nutrition targets (kcal, protein_g, carbs_g, fat_g, fiber_g, or protein per kg
of body weight), the effective protein target, the latest body weight and Garmin's average total
burn of the last 28 days (a starting point when the user wants help choosing targets)."""

SET_TARGETS = """\
Set daily nutrition targets. Only the values you pass change; list fields in `clear` to remove
a target. protein_g_per_kg (e.g. 1.6-2.0 for endurance athletes) is used when protein_g is not
set. Only set targets the user asked for or agreed to."""

ENERGY_CONTEXT = """\
What Garmin knows about a day's energy expenditure and training: calories burned (total,
active, BMR; so far for today), steps, the activities with their calories and training load,
fitness/fatigue/form (CTL/ATL/TSB), training status and readiness, the average burn of the 7
days before, and the food logged that day with the balance. Use it to advise on fuelling
(e.g. more carbohydrate after a long run) and recovery."""

PHOTO_PROMPT = f"""\
Log a meal from the attached photo (or my description) in Garminizer.

{ESTIMATION_GUIDE}

Then:
- Show me a short table of the items (portion in g, kcal, protein, carbs, fat) and the totals.
- Tell me how the day looks now: intake against my targets, what is left, Garmin's calories
  burned so far and the balance.
- If you were unsure about a portion, ask me and correct it with update_meal."""

READ_ONLY = ToolAnnotations(read_only_hint=True, open_world_hint=False)
ADDITIVE = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False
)
CHANGES = ToolAnnotations(
    read_only_hint=False, destructive_hint=True, idempotent_hint=True, open_world_hint=False
)

_HH_MM = re.compile(r"(\d{1,2}):(\d{2})")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


# --- argument parsing ------------------------------------------------------------------------


def parse_eaten_at(value: str | None, tz: ZoneInfo, now: datetime) -> datetime | None:
    """'HH:MM' (today, or yesterday when that is more than an hour ahead) or ISO date-time.

    Naive date-times stay naive: the service reads them as the athlete's local time.
    """
    if value is None or not value.strip():
        return None
    raw = value.strip()
    hm = _HH_MM.fullmatch(raw)
    if hm:
        hour, minute = int(hm.group(1)), int(hm.group(2))
        if hour > 23 or minute > 59:
            raise ToolError(f"eaten_at {raw!r} is not a valid time of day")
        when = datetime.combine(now.astimezone(tz).date(), time(hour, minute), tz)
        if when > now + timedelta(hours=1):
            when -= timedelta(days=1)
        return when
    if _DATE.fullmatch(raw):
        raise ToolError(f"eaten_at {raw!r} has no time; use 'YYYY-MM-DDTHH:MM' (local time)")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        raise ToolError(
            f"eaten_at {raw!r} is not a time; use 'HH:MM' (today) or 'YYYY-MM-DDTHH:MM' "
            "(local time)"
        ) from None


def parse_day(value: str | None, tz: ZoneInfo, now: datetime) -> date:
    """None / 'today' / 'yesterday' / 'YYYY-MM-DD' (a date-time is cut to its date)."""
    today = now.astimezone(tz).date()
    raw = (value or "").strip().lower()
    if raw in {"", "today"}:
        return today
    if raw == "yesterday":
        return today - timedelta(days=1)
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        raise ToolError(
            f"day {value!r} is not a date; use 'YYYY-MM-DD', 'today' or 'yesterday'"
        ) from None


def _validated[T: BaseModel](model: type[T], **values: Any) -> T:
    try:
        return model.model_validate(values)
    except ValidationError as exc:
        raise ToolError(_validation_message(exc)) from None


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "input"
        parts.append(f"{loc}: {err['msg']}")
    return "invalid input - " + "; ".join(parts)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value)


def _portion(item: Any) -> str:
    if item.grams is not None:
        return f"{item.grams:g} g"
    if item.amount is not None:
        return f"{item.amount:g} {item.unit or ''}".strip()
    return "portion"


def compact_meal(meal: NutritionMeal) -> dict[str, Any]:
    """A meal in a few tokens: what Claude needs to refer to it again."""
    return {
        "meal_id": meal.meal_id,
        "day": meal.day.isoformat(),
        "time": meal.eaten_at.strftime("%H:%M"),
        "meal_type": meal.meal_type,
        "name": meal.name,
        "kcal": _round(meal.kcal),
        "protein_g": meal.protein_g,
        "carbs_g": meal.carbs_g,
        "fat_g": meal.fat_g,
        "fiber_g": meal.fiber_g,
        "items": [f"{i.food} ({_portion(i)}): {i.kcal:.0f} kcal" for i in meal.items],
        "confidence": meal.confidence,
        "source": meal.source,
    }


# --- server ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Runtime:
    factory: sessionmaker[Session]
    fallback_tz: str
    now: Clock

    @contextmanager
    def transaction(self) -> Iterator[Session]:
        """One database transaction per tool call; service errors become tool errors."""
        session = self.factory()
        try:
            yield session
            session.commit()
        except service.MealNotFoundError as exc:
            session.rollback()
            raise ToolError(f"{exc}; list_recent_meals shows the meal ids") from None
        except service.NutritionError as exc:
            session.rollback()
            raise ToolError(str(exc)) from None
        except OperationalError:
            session.rollback()
            log.exception("database error")
            raise ToolError(
                "The Garminizer database is not reachable. Is Garminizer (Docker) running?"
            ) from None
        except BaseException:
            session.rollback()
            raise
        finally:
            session.close()

    def zone(self, session: Session) -> ZoneInfo:
        return service.athlete_zone(session, self.fallback_tz)

    def meal_result(self, session: Session, meal: NutritionMeal, now: datetime) -> dict[str, Any]:
        day = service.day_summary(session, meal.day, fallback_tz=self.fallback_tz, now=now)
        return {
            "meal": meal.model_dump(mode="json"),
            "warnings": [w.model_dump(mode="json") for w in meal.warnings],
            "day_summary": day.model_dump(mode="json"),
        }

    def targets_view(self, session: Session, targets: NutritionTargets) -> dict[str, Any]:
        tz = self.zone(session)
        today = self.now().astimezone(tz).date()
        weight = service.weight_on(session, today, tz)
        return {
            "targets": targets.model_dump(mode="json"),
            "protein_target_g": service.protein_target(targets, weight),
            "weight_kg": weight,
            "garmin_avg_total_kcal_28d": _round(
                service.average_burn(session, today - timedelta(days=28), today)
            ),
        }


def build_server(
    factory: sessionmaker[Session], *, fallback_tz: str = "UTC", clock: Clock | None = None
) -> MCPServer[Any]:
    """The Garminizer MCP server; every tool call runs in its own database transaction."""
    server: MCPServer[Any] = MCPServer(
        name="garminizer",
        title="Garminizer meal log",
        description="Log meals, calories and macros; compare them with Garmin's energy burn.",
        instructions=INSTRUCTIONS,
        version=__version__,
    )
    rt = _Runtime(factory, fallback_tz, clock or (lambda: datetime.now(UTC)))
    _register_meal_tools(server, rt)
    _register_day_tools(server, rt)
    _register_target_tools(server, rt)

    @server.prompt(
        name="log-meal-from-photo",
        title="Log a meal from a photo",
        description="Estimate a meal from a photo or description and log it in Garminizer.",
    )
    def log_meal_from_photo(
        details: Annotated[
            str | None, Field(description="Anything to add, e.g. 'half portion, no dressing'")
        ] = None,
    ) -> str:
        return PHOTO_PROMPT + (f"\n\nDetails from me: {details.strip()}" if details else "")

    return server


def _register_meal_tools(server: MCPServer[Any], rt: _Runtime) -> None:
    @server.tool(
        name="log_meal",
        title="Log a meal",
        description=LOG_MEAL,
        annotations=ADDITIVE,
        structured_output=False,
    )
    def log_meal(
        name: Annotated[
            str, Field(description="Short name of the meal, e.g. 'Spaghetti bolognese, salad'")
        ],
        items: Annotated[
            list[NutritionItemIn] | None,
            Field(description="One entry per food or drink with its portion and nutrients"),
        ] = None,
        eaten_at: Annotated[
            str | None,
            Field(
                description="Local time eaten: 'HH:MM' (today) or 'YYYY-MM-DDTHH:MM'. Default: now"
            ),
        ] = None,
        meal_type: Annotated[
            MealType | None,
            Field(description="breakfast, lunch, dinner, snack or drink (default: from time)"),
        ] = None,
        notes: Annotated[
            str | None, Field(description="Assumptions behind the estimate (portions, oil ...)")
        ] = None,
        confidence: Annotated[
            Confidence | None,
            Field(description="high = weighed/label, medium = clear photo, low = rough guess"),
        ] = None,
        totals: Annotated[
            NutritionTotalsIn | None,
            Field(description="Optional meal totals that override the sum of the items"),
        ] = None,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            moment = rt.now()
            data = _validated(
                NutritionMealIn,
                name=name,
                eaten_at=parse_eaten_at(eaten_at, rt.zone(s), moment),
                meal_type=meal_type,
                items=items or [],
                totals=totals,
                notes=notes,
                confidence=confidence,
            )
            meal = service.log_meal(
                s, data, source="claude", fallback_tz=rt.fallback_tz, now=moment
            )
            log.info("logged meal %s (%s kcal)", meal.meal_id, round(meal.kcal))
            return {"stored": True, **rt.meal_result(s, meal, moment)}

    @server.tool(
        name="update_meal",
        title="Correct a meal",
        description=UPDATE_MEAL,
        annotations=CHANGES,
        structured_output=False,
    )
    def update_meal(
        meal_id: Annotated[int, Field(description="meal_id from log_meal or list_recent_meals")],
        name: Annotated[str | None, Field(description="New name")] = None,
        items: Annotated[
            list[NutritionItemIn] | None,
            Field(description="The complete new item list (replaces all items)"),
        ] = None,
        eaten_at: Annotated[
            str | None, Field(description="New local time: 'HH:MM' or 'YYYY-MM-DDTHH:MM'")
        ] = None,
        meal_type: Annotated[MealType | None, Field(description="New meal type")] = None,
        notes: Annotated[str | None, Field(description="New notes")] = None,
        confidence: Annotated[Confidence | None, Field(description="New confidence")] = None,
        totals: Annotated[
            NutritionTotalsIn | None, Field(description="Totals to set explicitly")
        ] = None,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            moment = rt.now()
            given = {
                "name": name,
                "items": items,
                "eaten_at": parse_eaten_at(eaten_at, rt.zone(s), moment),
                "meal_type": meal_type,
                "notes": notes,
                "confidence": confidence,
                "totals": totals,
            }
            patch = _validated(
                NutritionMealPatch, **{k: v for k, v in given.items() if v is not None}
            )
            meal = service.update_meal(s, meal_id, patch, fallback_tz=rt.fallback_tz, now=moment)
            return {"updated": True, **rt.meal_result(s, meal, moment)}

    @server.tool(
        name="delete_meal",
        title="Delete a meal",
        description=DELETE_MEAL,
        annotations=CHANGES,
        structured_output=False,
    )
    def delete_meal(
        meal_id: Annotated[int, Field(description="meal_id of the meal to delete")],
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            moment = rt.now()
            meal = service.delete_meal(s, meal_id, fallback_tz=rt.fallback_tz)
            day = service.day_summary(s, meal.day, fallback_tz=rt.fallback_tz, now=moment)
            return {"deleted": compact_meal(meal), "day_summary": day.model_dump(mode="json")}


def _register_day_tools(server: MCPServer[Any], rt: _Runtime) -> None:
    @server.tool(
        name="get_day_nutrition",
        title="Day of food diary",
        description=GET_DAY,
        annotations=READ_ONLY,
        structured_output=False,
    )
    def get_day_nutrition(
        day: Annotated[
            str | None, Field(description="'YYYY-MM-DD', 'today' or 'yesterday' (default today)")
        ] = None,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            moment = rt.now()
            d = parse_day(day, rt.zone(s), moment)
            out = service.get_day(s, d, fallback_tz=rt.fallback_tz, now=moment)
            return out.model_dump(mode="json")

    @server.tool(
        name="list_recent_meals",
        title="Recent meals",
        description=LIST_RECENT,
        annotations=READ_ONLY,
        structured_output=False,
    )
    def list_recent_meals(
        days: Annotated[int, Field(ge=1, le=60, description="How many days back (1-60)")] = 7,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            today = parse_day(None, rt.zone(s), rt.now())
            start = today - timedelta(days=days - 1)
            meals = service.list_meals(
                s, start, today + timedelta(days=1), fallback_tz=rt.fallback_tz, newest_first=True
            )
            by_day: dict[date, list[NutritionMeal]] = {}
            for meal in meals:
                by_day.setdefault(meal.day, []).append(meal)
            return {
                "from": start.isoformat(),
                "to": today.isoformat(),
                "meals": len(meals),
                "days": [
                    {
                        "day": d.isoformat(),
                        "totals": service.day_totals(day_meals).model_dump(mode="json"),
                        "meals": [compact_meal(x) for x in day_meals],
                    }
                    for d, day_meals in by_day.items()
                ],
            }

    @server.tool(
        name="get_energy_context",
        title="Garmin energy and training",
        description=ENERGY_CONTEXT,
        annotations=READ_ONLY,
        structured_output=False,
    )
    def get_energy_context(
        day: Annotated[
            str | None, Field(description="'YYYY-MM-DD', 'today' or 'yesterday' (default today)")
        ] = None,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            moment = rt.now()
            d = parse_day(day, rt.zone(s), moment)
            ctx = service.energy_context(s, d, fallback_tz=rt.fallback_tz, now=moment)
            return ctx.model_dump(mode="json")


def _register_target_tools(server: MCPServer[Any], rt: _Runtime) -> None:
    @server.tool(
        name="get_nutrition_targets",
        title="Nutrition targets",
        description=GET_TARGETS,
        annotations=READ_ONLY,
        structured_output=False,
    )
    def get_nutrition_targets() -> dict[str, Any]:
        with rt.transaction() as s:
            return rt.targets_view(s, service.get_targets(s))

    @server.tool(
        name="set_nutrition_targets",
        title="Set nutrition targets",
        description=SET_TARGETS,
        annotations=CHANGES,
        structured_output=False,
    )
    def set_nutrition_targets(
        kcal: Annotated[float | None, Field(description="Energy target (kcal/day)")] = None,
        protein_g: Annotated[float | None, Field(description="Protein target (g/day)")] = None,
        carbs_g: Annotated[float | None, Field(description="Carbohydrate target (g/day)")] = None,
        fat_g: Annotated[float | None, Field(description="Fat target (g/day)")] = None,
        fiber_g: Annotated[float | None, Field(description="Fibre target (g/day)")] = None,
        protein_g_per_kg: Annotated[
            float | None, Field(description="Protein per kg body weight (used without protein_g)")
        ] = None,
        clear: Annotated[
            list[str] | None, Field(description="Targets to remove, e.g. ['carbs_g']")
        ] = None,
    ) -> dict[str, Any]:
        with rt.transaction() as s:
            targets = _validated(
                NutritionTargets,
                kcal=kcal,
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                fiber_g=fiber_g,
                protein_g_per_kg=protein_g_per_kg,
            )
            stored = service.set_targets(s, targets, merge=True, clear=clear or ())
            return {"saved": True, **rt.targets_view(s, stored)}


def main(env_file: Path | None = None) -> None:
    """Entry point of `garminizer mcp`: migrate, then serve over stdio until stdin closes."""
    from garminizer.config import Settings  # noqa: PLC0415 - keep the import graph small
    from garminizer.db import migrate  # noqa: PLC0415

    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    for noisy in ("alembic", "httpx", "mcp"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    settings = Settings(_env_file=env_file) if env_file else Settings()
    if env_file is None and "database_url" not in settings.model_fields_set:
        log.warning("DATABASE_URL is not set: using the development default database")
    with redirect_stdout(sys.stderr):  # belt and braces: nothing but JSON-RPC on stdout
        migrate.upgrade(settings.database_url)
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    server = build_server(sessionmaker(engine, expire_on_commit=False), fallback_tz=settings.tz)
    log.info("garminizer MCP server %s ready (stdio)", __version__)
    try:
        server.run("stdio")
    finally:
        engine.dispose()
