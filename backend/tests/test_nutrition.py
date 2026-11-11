"""Nutrition service: totals from items, plausibility flags, local-day assignment, targets."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.athlete import AthleteClock, athlete_clock
from garminizer.nutrition import service
from garminizer.nutrition.schemas import (
    NutritionItemIn,
    NutritionMealIn,
    NutritionMealPatch,
    NutritionTargets,
    NutritionTotalsIn,
)

BERLIN = "Europe/Berlin"
NOW = datetime(2026, 3, 11, 12, 0, tzinfo=UTC)  # 13:00 in Berlin
LATER = datetime(2026, 12, 31, tzinfo=UTC)


def _athlete(db: Session, tz: str | None = BERLIN, weight: float | None = 70.0) -> None:
    db.add(m.Athlete(id=1, time_zone=tz, weight_kg=weight, is_demo=False))
    db.flush()


def _clock(db: Session, now: datetime = NOW, fallback: str | None = "UTC") -> AthleteClock:
    """The athlete's clock with a fixed "now" (zone: athlete row, else ``fallback``)."""
    return athlete_clock(db, fallback, now=lambda: now)


def _item(
    food: str, kcal: float, p: float, c: float, f: float, fib: float = 0.0
) -> NutritionItemIn:
    return NutritionItemIn(
        food=food, grams=100, kcal=kcal, protein_g=p, carbs_g=c, fat_g=f, fiber_g=fib
    )


PASTA = [
    _item("Spaghetti, cooked", 284, 10.4, 55.6, 1.6, 3.2),
    _item("Olive oil", 88, 0, 0, 10),
    _item("Tomato sauce", 75, 2.4, 12, 2.3, 2.9),
]


def _meal(**kw: Any) -> NutritionMealIn:
    values: dict[str, Any] = {"name": "Pasta", "items": PASTA, "eaten_at": NOW}
    values.update(kw)
    return NutritionMealIn.model_validate(values)


# --- pure helpers ----------------------------------------------------------------------------


def test_totals_are_the_sum_of_items() -> None:
    totals = service.compute_totals(PASTA, None)
    assert totals["kcal"] == pytest.approx(447.0)
    assert totals["protein_g"] == pytest.approx(12.8)
    assert totals["carbs_g"] == pytest.approx(67.6)
    assert totals["fat_g"] == pytest.approx(13.9)
    assert totals["fiber_g"] == pytest.approx(6.1)
    assert totals["sodium_mg"] is None  # items carry no sodium


def test_explicit_totals_win_per_field() -> None:
    totals = service.compute_totals(PASTA, NutritionTotalsIn(kcal=500, sodium_mg=800))
    assert totals["kcal"] == 500
    assert totals["protein_g"] == pytest.approx(12.8)  # still from the items
    assert totals["sodium_mg"] == 800


def test_unknown_item_macros_stay_unknown() -> None:
    items = [NutritionItemIn(food="Apple", kcal=95), NutritionItemIn(food="Nuts", kcal=180)]
    totals = service.compute_totals(items, None)
    assert totals["kcal"] == 275
    assert totals["protein_g"] is None
    partial = [*items, NutritionItemIn(food="Yoghurt", kcal=100, protein_g=10)]
    assert service.compute_totals(partial, None)["protein_g"] == 10


def test_meal_needs_energy_and_rejects_negative_values() -> None:
    with pytest.raises(ValidationError, match=r"totals\.kcal"):
        NutritionMealIn(name="Mystery")
    with pytest.raises(ValidationError):
        NutritionItemIn(food="Anti-food", kcal=-5)
    with pytest.raises(ValidationError):
        NutritionItemIn(food="Odd", kcal=10, protein_g=-1)
    with pytest.raises(ValidationError):
        NutritionTotalsIn(fat_g=-0.1)
    with pytest.raises(ValidationError):  # typos are reported, not silently dropped
        NutritionItemIn.model_validate({"food": "Egg", "kcal": 70, "protein": 6})
    assert NutritionMealIn(name="Bar", totals=NutritionTotalsIn(kcal=220)).items == []


@pytest.mark.parametrize(
    ("kcal", "p", "c", "f", "alcohol", "flagged"),
    [
        (500, 25, 60, 17, None, False),  # 493 kcal from macros: 1.4 % off
        (500, 25, 60, 22, None, False),  # 538: 7.6 % off
        (500, 30, 70, 25, None, True),  # 625: 25 % off
        (300, 10, 20, 5, None, True),  # 165: 45 % off
        (215, 2.5, 18, 0, 19.5, False),  # beer: alcohol counts 7 kcal/g
        (215, 2.5, 18, 0, None, True),  # ... and without alcohol it does not add up
        (2, 0.3, 0, 0, None, False),  # black coffee: within the 10 kcal floor
        (0, 1, 1, 1, None, True),  # 17 kcal of macros in a 0 kcal meal
    ],
)
def test_macro_kcal_mismatch(
    kcal: float, p: float, c: float, f: float, alcohol: float | None, flagged: bool
) -> None:
    codes = [w.code for w in service.meal_warnings(kcal, p, c, f, alcohol)]
    assert ("macro_kcal_mismatch" in codes) is flagged


def test_mismatch_needs_all_three_macros() -> None:
    assert service.meal_warnings(500, None, 10, 10, None) == []


@pytest.mark.parametrize(
    ("hhmm", "expected"),
    [
        ("03:59", "snack"),
        ("04:00", "breakfast"),
        ("10:29", "breakfast"),
        ("10:30", "lunch"),
        ("14:59", "lunch"),
        ("15:00", "snack"),
        ("17:00", "dinner"),
        ("21:29", "dinner"),
        ("21:30", "snack"),
    ],
)
def test_meal_type_from_local_time(hhmm: str, expected: str) -> None:
    hour, minute = map(int, hhmm.split(":"))
    assert service.infer_meal_type(datetime(2026, 1, 1, hour, minute)) == expected


# --- meals in the database -------------------------------------------------------------------


def test_log_meal_stores_meal_and_items(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(db, _meal(notes="assumed 10 g oil"), source="claude", clock=_clock(db))
    assert meal.meal_id > 0
    assert meal.kcal == pytest.approx(447.0)
    assert meal.meal_type == "lunch"  # 13:00 local
    assert meal.eaten_at.utcoffset() == timedelta(hours=1)  # Berlin, winter time
    assert [i.idx for i in meal.items] == [0, 1, 2]
    assert meal.warnings == []
    row = db.get(m.Meal, meal.meal_id)
    assert row is not None
    assert row.source == "claude"
    assert row.notes == "assumed 10 g oil"
    assert db.scalar(select(func.count()).select_from(m.MealItem)) == 3
    assert db.scalar(select(func.sum(m.MealItem.kcal))) == pytest.approx(row.kcal, abs=0.1)


def test_mismatching_meal_is_stored_with_warning(db: Session) -> None:
    _athlete(db)
    data = _meal(items=[], totals=NutritionTotalsIn(kcal=300, protein_g=40, carbs_g=60, fat_g=20))
    meal = service.log_meal(db, data, source="manual", clock=_clock(db))
    assert [w.code for w in meal.warnings] == ["macro_kcal_mismatch"]
    assert db.get(m.Meal, meal.meal_id) is not None


def test_items_total_mismatch_is_flagged(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(
        db, _meal(totals=NutritionTotalsIn(kcal=900)), source="claude", clock=_clock(db)
    )
    assert "items_kcal_mismatch" in [w.code for w in meal.warnings]


@pytest.mark.parametrize(
    ("tz", "eaten_at", "expected_day", "expected_type"),
    [
        # 23:30 UTC is 00:30 the next day in Berlin (winter, UTC+1).
        (BERLIN, datetime(2026, 3, 10, 23, 30, tzinfo=UTC), date(2026, 3, 11), "snack"),
        # ... and 01:30 in summer (UTC+2): 22:30 UTC.
        (BERLIN, datetime(2026, 7, 10, 22, 30, tzinfo=UTC), date(2026, 7, 11), "snack"),
        (BERLIN, datetime(2026, 7, 10, 21, 30, tzinfo=UTC), date(2026, 7, 10), "snack"),
        # A naive time is the athlete's local time.
        (BERLIN, datetime(2026, 3, 10, 23, 30), date(2026, 3, 10), "snack"),
        (BERLIN, datetime(2026, 3, 10, 7, 15), date(2026, 3, 10), "breakfast"),
        # West of UTC: 03:00 UTC is still the previous evening in New York.
        ("America/New_York", datetime(2026, 3, 11, 3, 0, tzinfo=UTC), date(2026, 3, 10), "snack"),
        ("America/New_York", datetime(2026, 3, 11, 0, 0, tzinfo=UTC), date(2026, 3, 10), "dinner"),
    ],
)
def test_day_is_the_local_date_of_eaten_at(
    db: Session, tz: str, eaten_at: datetime, expected_day: date, expected_type: str
) -> None:
    _athlete(db, tz=tz)
    meal = service.log_meal(db, _meal(eaten_at=eaten_at), source="claude", clock=_clock(db, LATER))
    assert meal.day == expected_day
    assert meal.meal_type == expected_type
    assert meal.eaten_at.astimezone(ZoneInfo(tz)).date() == expected_day


def test_fallback_time_zone_without_athlete(db: Session) -> None:
    eaten = datetime(2026, 3, 11, 3, 0, tzinfo=UTC)
    meal = service.log_meal(
        db, _meal(eaten_at=eaten), source="claude", clock=_clock(db, fallback="America/New_York")
    )
    assert meal.day == date(2026, 3, 10)
    utc_meal = service.log_meal(db, _meal(eaten_at=eaten), source="claude", clock=_clock(db))
    assert utc_meal.day == date(2026, 3, 11)
    assert _clock(db, fallback="Not/AZone").name == "UTC"


def test_default_eaten_at_is_now_and_future_is_rejected(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(db, _meal(eaten_at=None), source="claude", clock=_clock(db))
    assert meal.eaten_at == NOW
    with pytest.raises(service.NutritionError, match="future"):
        service.log_meal(
            db, _meal(eaten_at=NOW + timedelta(hours=13)), source="claude", clock=_clock(db)
        )


def test_update_replaces_items_and_recomputes_totals(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(
        db, _meal(totals=NutritionTotalsIn(sodium_mg=600)), source="claude", clock=_clock(db)
    )
    patch = NutritionMealPatch(items=[_item("Rice, cooked", 260, 5.4, 56.4, 0.6)])
    updated = service.update_meal(db, meal.meal_id, patch, clock=_clock(db))
    assert updated.kcal == 260
    assert updated.protein_g == pytest.approx(5.4)
    assert updated.sodium_mg == 600  # not derivable from items: kept
    assert [i.food for i in updated.items] == ["Rice, cooked"]
    assert db.scalar(select(func.count()).select_from(m.MealItem)) == 1


def test_update_moves_day_and_clears_notes(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(
        db, _meal(notes="guess", confidence="low"), source="claude", clock=_clock(db)
    )
    patch = NutritionMealPatch.model_validate(
        {"eaten_at": "2026-03-10T19:30:00", "notes": None, "totals": {"kcal": 480}}
    )
    updated = service.update_meal(db, meal.meal_id, patch, clock=_clock(db))
    assert updated.day == date(2026, 3, 10)
    assert updated.notes is None
    assert updated.confidence == "low"  # not in the patch
    assert updated.kcal == 480
    assert updated.meal_type == "lunch"  # meal_type is not re-inferred


def test_update_and_delete_unknown_meal(db: Session) -> None:
    with pytest.raises(service.MealNotFoundError):
        service.update_meal(db, 987654, NutritionMealPatch(name="x"), clock=_clock(db))
    with pytest.raises(service.MealNotFoundError):
        service.delete_meal(db, 987654, clock=_clock(db))


def test_delete_removes_items(db: Session) -> None:
    _athlete(db)
    meal = service.log_meal(db, _meal(), source="claude", clock=_clock(db))
    deleted = service.delete_meal(db, meal.meal_id, clock=_clock(db))
    assert deleted.meal_id == meal.meal_id
    assert db.get(m.Meal, meal.meal_id) is None
    assert db.scalar(select(func.count()).select_from(m.MealItem)) == 0


# --- targets, days and summaries -------------------------------------------------------------


def test_targets_replace_merge_and_clear(db: Session) -> None:
    assert service.get_targets(db) == NutritionTargets()
    service.set_targets(db, NutritionTargets(kcal=2600, protein_g_per_kg=1.8))
    merged = service.set_targets(db, NutritionTargets(fiber_g=35), merge=True)
    assert (merged.kcal, merged.protein_g_per_kg, merged.fiber_g) == (2600, 1.8, 35)
    cleared = service.set_targets(db, NutritionTargets(), merge=True, clear=["kcal"])
    assert cleared.kcal is None
    assert cleared.fiber_g == 35
    replaced = service.set_targets(db, NutritionTargets(carbs_g=300))
    assert replaced.model_dump(exclude_none=True) == {"carbs_g": 300}
    row = db.get(m.AppSetting, service.TARGETS_KEY)
    assert row is not None
    assert row.value == {"carbs_g": 300}
    with pytest.raises(service.NutritionError):
        service.set_targets(db, NutritionTargets(), merge=True, clear=["bogus"])
    with pytest.raises(ValidationError):
        NutritionTargets(kcal=-100)


def test_broken_stored_targets_are_ignored(db: Session) -> None:
    db.add(m.AppSetting(key=service.TARGETS_KEY, value={"kcal": "lots", "other": 1}))
    db.flush()
    assert service.get_targets(db) == NutritionTargets()


def test_day_summary_against_garmin_and_targets(db: Session) -> None:
    _athlete(db, weight=72.0)
    day = date(2026, 3, 11)
    db.add(m.DailySummary(day=day, total_kcal=2800, active_kcal=900, bmr_kcal=1900))
    db.add(m.BodyComposition(measured_at=datetime(2026, 3, 11, 6, 0, tzinfo=UTC), weight_kg=70.0))
    db.add(m.BodyComposition(measured_at=datetime(2026, 3, 12, 6, 0, tzinfo=UTC), weight_kg=69.0))
    service.set_targets(db, NutritionTargets(kcal=2700, protein_g_per_kg=2.0, carbs_g=350))
    service.log_meal(db, _meal(), source="claude", clock=_clock(db))
    service.log_meal(
        db,
        _meal(name="Shake", items=[_item("Whey", 120, 24, 3, 1.5)], meal_type="snack"),
        source="claude",
        clock=_clock(db),
    )
    out = service.get_day(db, day, clock=_clock(db))
    assert out.is_today
    assert out.totals.meals == 2
    assert out.totals.kcal == pytest.approx(567.0)
    assert out.totals.protein_g == pytest.approx(36.8)
    assert out.garmin.total_kcal == 2800
    assert out.balance_kcal == pytest.approx(567.0 - 2800)
    assert out.weight_kg == 70.0  # the weigh-in of that day, not the later one
    assert out.protein_target_g == 140  # 2.0 g/kg x 70 kg
    assert out.remaining.kcal == pytest.approx(2700 - 567.0)
    assert out.remaining.protein_g == pytest.approx(140 - 36.8)
    assert out.remaining.fat_g is None  # no target
    assert out.protein_g_per_kg == pytest.approx(36.8 / 70, abs=0.01)
    assert [x.name for x in out.meals] == ["Pasta", "Shake"]

    empty = service.get_day(db, day - timedelta(days=1), clock=_clock(db))
    assert empty.totals.meals == 0
    assert empty.totals.kcal == 0
    assert empty.balance_kcal is None
    assert not empty.is_today


def test_daily_series_and_summary(db: Session) -> None:
    _athlete(db, weight=70.0)
    d1, d2, d3 = date(2026, 3, 9), date(2026, 3, 10), date(2026, 3, 11)
    for d, burn in ((d1, 2500), (d2, 2700), (d3, 3000)):
        db.add(m.DailySummary(day=d, total_kcal=burn, active_kcal=burn - 1800))
    db.flush()
    for d, kcal, protein in ((d1, 2400, 140), (d3, 2900, 150)):
        totals = NutritionTotalsIn(kcal=kcal, protein_g=protein, carbs_g=300, fat_g=80)
        at = datetime.combine(d, datetime.min.time()) + timedelta(hours=12)
        service.log_meal(
            db, _meal(items=[], totals=totals, eaten_at=at), source="manual", clock=_clock(db)
        )

    points = service.daily_series(db, d1, d3)
    assert [p.day for p in points] == [d1, d2, d3]
    assert [p.meals for p in points] == [1, 0, 1]
    assert points[1].intake_kcal is None
    assert points[1].balance_kcal is None
    assert points[0].balance_kcal == -100
    assert points[2].balance_kcal == -100

    s = service.summary(db, d1, d3, clock=_clock(db))
    assert (s.days, s.days_logged, s.meals) == (3, 2, 2)
    assert s.avg_intake_kcal == 2650
    assert s.avg_total_kcal == 2750  # Garmin burn on logged days only
    assert s.avg_balance_kcal == -100
    assert s.avg_protein_g == 145
    assert s.protein_g_per_kg == pytest.approx(145 / 70, abs=0.01)
    energy = {"p": 4 * 290, "c": 4 * 600, "f": 9 * 160}
    total = sum(energy.values())
    assert s.macro_split.protein_pct == pytest.approx(energy["p"] / total * 100, abs=0.05)
    assert s.macro_split.alcohol_pct == 0
    assert [(w.week, w.days_logged, w.intake_kcal) for w in s.weeks] == [(d1, 2, 2650)]
    assert [x.meal_type for x in s.by_meal_type] == ["lunch"]


def test_energy_context(db: Session) -> None:
    _athlete(db)
    day = date(2026, 3, 11)
    db.add(m.DailySummary(day=day, total_kcal=3100, active_kcal=1200, steps=14000))
    db.add(m.DailySummary(day=day - timedelta(days=1), total_kcal=2500))
    db.add(
        m.Activity(
            activity_id=1,
            name="Long run",
            sport_type="running",
            sport_group="run",
            start_time_utc=datetime(2026, 3, 11, 8, 0, tzinfo=UTC),
            start_time_local=datetime(2026, 3, 11, 9, 0),
            duration_s=7200,
            distance_m=24000,
            calories=1500,
            training_load=210,
        )
    )
    db.add(m.DailyLoad(day=day, load=210, trimp=200, activities=1, ctl=60, atl=70, tsb=-5))
    db.flush()
    service.log_meal(db, _meal(), source="claude", clock=_clock(db))
    ctx = service.energy_context(db, day, clock=_clock(db))
    assert ctx.garmin.total_kcal == 3100
    assert ctx.steps == 14000
    assert [a.name for a in ctx.activities] == ["Long run"]
    assert ctx.training_load == 210
    assert ctx.avg_total_kcal_7d == 2500
    assert ctx.intake.kcal == pytest.approx(447.0)
    assert ctx.balance_kcal == pytest.approx(447.0 - 3100)
    assert not ctx.demo_data
