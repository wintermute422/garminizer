"""Weight goal service on a test database (synthetic athlete, weigh-ins, meals, activities)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.analytics import goal as g
from garminizer.athlete import AthleteClock, athlete_clock
from garminizer.goal import service
from garminizer.goal.schemas import GoalSettings

BERLIN = "Europe/Berlin"
START = date(2026, 3, 2)  # Monday
TODAY = date(2026, 3, 12)  # Thursday
NOW = datetime(2026, 3, 12, 17, 30, tzinfo=UTC)  # 18:30 in Berlin


def _clock(db: Session, now: datetime = NOW) -> AthleteClock:
    return athlete_clock(db, "UTC", now=lambda: now)


def _athlete(db: Session, **kw: Any) -> None:
    values: dict[str, Any] = {
        "id": 1,
        "time_zone": BERLIN,
        "gender": "MALE",
        "birth_date": date(1986, 1, 1),
        "height_cm": 180.0,
        "weight_kg": 80.0,
        "is_demo": False,
    }
    values.update(kw)
    db.add(m.Athlete(**values))
    db.flush()


def _weigh(db: Session, local: datetime, kg: float, fat: float | None = 20.0) -> None:
    when = local.replace(tzinfo=g_zone()).astimezone(UTC)
    db.add(
        m.BodyComposition(
            measured_at=when,
            weight_kg=kg,
            body_fat_pct=fat,
            muscle_mass_kg=None if fat is None else 35.0,
            body_water_pct=None if fat is None else 58.0,
        )
    )
    db.flush()


def g_zone() -> Any:
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    return ZoneInfo(BERLIN)


def _meal(db: Session, day: date, kcal: float, name: str = "Meal", hour: int = 12) -> None:
    db.add(
        m.Meal(
            eaten_at=datetime(day.year, day.month, day.day, hour, tzinfo=g_zone()),
            day=day,
            meal_type="lunch",
            name=name,
            kcal=kcal,
            protein_g=kcal / 20,
            carbs_g=kcal / 10,
            fat_g=kcal / 40,
            source="manual",
        )
    )
    db.flush()


def _activity(
    db: Session, aid: int, local: datetime, kcal: float, bmr: float | None, dur: float = 3600
) -> None:
    db.add(
        m.Activity(
            activity_id=aid,
            name="Run",
            sport_type="running",
            sport_group="run",
            start_time_utc=local.replace(tzinfo=g_zone()).astimezone(UTC),
            start_time_local=local,
            duration_s=dur,
            distance_m=10_000.0,
            calories=kcal,
            bmr_calories=bmr,
        )
    )
    db.flush()


def _goal(db: Session, **kw: Any) -> GoalSettings:
    values: dict[str, Any] = {
        "start_day": START,
        "start_weight_kg": 80.0,
        "rate_kg_per_week": 0.7,
        "end_day": START + timedelta(days=55),
    }
    values.update(kw)
    return service.set_settings(db, GoalSettings.model_validate(values))


# --- settings --------------------------------------------------------------------------------


def test_settings_roundtrip_and_patch(db: Session) -> None:
    assert service.get_settings(db) is None
    with pytest.raises(service.GoalError, match="start_day"):
        service.patch_settings(db, {"rate_kg_per_week": 0.5})
    _goal(db)
    stored = service.patch_settings(db, {"rate_kg_per_week": 0.5, "end_day": None})
    assert stored.rate_kg_per_week == 0.5
    assert stored.end_day == START + timedelta(days=55)  # None = unchanged
    assert stored.trend_weights == [3.0, 2.0, 1.0]
    with pytest.raises(service.GoalError, match="end_day must be after start_day"):
        service.patch_settings(db, {"end_day": START})
    assert service.clear_settings(db) is True
    assert service.get_settings(db) is None


def test_checkpoints_can_be_accepted_and_undone(db: Session) -> None:
    _goal(db)
    sunday = START + timedelta(days=6)
    assert service.set_checkpoint(db, sunday, accepted=True).accepted_checkpoints == [sunday]
    with pytest.raises(service.GoalError, match="not a checkpoint"):
        service.set_checkpoint(db, sunday + timedelta(days=1), accepted=True)
    assert service.set_checkpoint(db, sunday, accepted=False).accepted_checkpoints == []


# --- weigh-ins -------------------------------------------------------------------------------


def test_weigh_in_of_a_day_prefers_body_composition_and_local_days(db: Session) -> None:
    _athlete(db)
    day = date(2026, 3, 4)
    _weigh(db, datetime(2026, 3, 4, 6, 10), 80.9, fat=None)  # plain weight first
    _weigh(db, datetime(2026, 3, 4, 9, 20), 80.5, fat=19.8)
    _weigh(db, datetime(2026, 3, 4, 21, 0), 81.2, fat=20.4)
    _weigh(db, datetime(2026, 3, 5, 0, 30), 80.2, fat=None)  # 23:30 UTC, local next day
    got = service.daily_weigh_ins(db, day, day + timedelta(days=1), _clock(db))
    assert got[day].weight_kg == 80.5 and got[day].body_fat_pct == 19.8
    assert got[day + timedelta(days=1)].weight_kg == 80.2  # no composition: first one counts


# --- view ------------------------------------------------------------------------------------


def test_view_without_goal(db: Session) -> None:
    _athlete(db)
    v = service.view(db, clock=_clock(db))
    assert v.configured is False and v.days == [] and v.status is None
    assert v.profile.sex == "male" and v.profile.height_cm == 180.0
    assert v.bmr_today is not None and v.bmr_today.source == "formulas"


def test_view_trend_target_checkpoints_and_body_fat(db: Session) -> None:
    _athlete(db)
    weights = [80.0, 79.9, 79.8, 79.6, 79.5, 79.4, 79.0, 79.2, 79.0, 78.9, 78.8]  # days 0..10
    for i, kg in enumerate(weights):
        _weigh(
            db,
            datetime.combine(START + timedelta(days=i), datetime.min.time()).replace(hour=7),
            kg,
            20.0 - 0.1 * i,
        )
    _goal(db)
    v = service.view(db, clock=_clock(db))
    assert v.configured and v.today == TODAY
    assert [r.day for r in v.days] == [START + timedelta(days=i) for i in range(11)]
    sunday = v.days[6]
    exp_trend = (79.0 * 3 + 79.4 * 2 + 79.5) / 6
    assert sunday.trend_kg == pytest.approx(round(exp_trend, 3))
    assert sunday.target_kg == pytest.approx(79.4)
    # trend 79.25 < 79.4 → reached, the line restarts at the trend
    assert v.checkpoints[0].status == "reached"
    assert v.anchors[1].weight_kg == pytest.approx(round(exp_trend, 3))
    last = v.days[-1]
    assert last.target_kg == pytest.approx(round(exp_trend - 0.4, 3))
    assert v.status is not None
    assert v.status.as_of == TODAY
    assert last.trend_kg is not None
    assert v.status.since_start_kg == pytest.approx(round(last.trend_kg - 80.0, 3))
    assert v.status.next_checkpoint is not None
    assert v.status.next_checkpoint.day == START + timedelta(days=13)
    assert v.target_daily_balance_kcal == -770
    # target line: start segment to the anchor, then the anchor segment to the end
    assert [p.day for p in v.target_line] == [START, START + timedelta(days=6)] * 1 + [
        START + timedelta(days=6),
        START + timedelta(days=55),
    ]
    assert len(v.body_fat) == 11
    assert v.body_fat_regression is not None
    assert v.body_fat_regression.slope_pct_per_week == pytest.approx(-0.7)


def test_view_before_the_start(db: Session) -> None:
    _athlete(db)
    _goal(db, start_day=TODAY + timedelta(days=3), end_day=TODAY + timedelta(days=60))
    v = service.view(db, clock=_clock(db))
    assert v.configured and v.days == []
    assert v.status is not None and v.status.trend_kg is None


# --- energy balance --------------------------------------------------------------------------


def test_energy_balance_of_today(db: Session) -> None:
    _athlete(db)
    _weigh(db, datetime(2026, 3, 12, 7, 0), 80.0, fat=20.0)
    _goal(db, start_weight_kg=80.0)
    _meal(db, TODAY, 600, "Oats")
    _meal(db, TODAY, 900, "Pasta", hour=13)
    _activity(db, 1, datetime(2026, 3, 12, 8, 0), 700, 90)
    _activity(db, 2, datetime(2026, 3, 12, 17, 0), 250, None, dur=1800)
    _meal(db, TODAY - timedelta(days=1), 2000)
    bal = service.energy_balance(db, TODAY, clock=_clock(db))
    est = g.bmr(80.0, 180.0, 40, "male", 20.0)
    assert bal.bmr is not None and bal.bmr.source == "formulas"
    assert bal.bmr.kcal == round(est.mean)
    assert bal.baseline_kcal == round(round(est.mean) * 1.25)
    second = round(250 - round(est.mean) * 1800 / 86_400)
    assert [a.active_kcal for a in bal.activities] == [610, second]
    assert bal.training_kcal == 610 + second
    assert bal.intake_kcal == 1500 and bal.meals == 2
    assert bal.burn_kcal == bal.baseline_kcal + bal.training_kcal
    assert bal.balance_kcal == 1500 - bal.burn_kcal
    assert bal.target_balance_kcal == -770
    assert bal.left_to_target_kcal == bal.burn_kcal - 770 - 1500
    assert (bal.is_today, bal.as_of) == (True, "18:30")
    # the week ends yesterday (today is not over): one logged day
    assert (bal.week.end, bal.week.days_logged, bal.week.intake_kcal) == (
        TODAY - timedelta(days=1),
        1,
        2000,
    )


def test_energy_balance_falls_back_to_garmin_bmr(db: Session) -> None:
    _athlete(db, gender=None)
    db.add(m.DailySummary(day=TODAY, total_kcal=2600.0, bmr_kcal=1700.0))
    db.flush()
    bal = service.energy_balance(db, TODAY, clock=_clock(db))
    assert bal.bmr is not None
    assert (bal.bmr.source, bal.bmr.kcal, bal.bmr.missing) == ("garmin", 1700, ["sex"])
    assert bal.baseline_kcal == round(1700 * 1.25)
    assert bal.burn_kcal is not None and bal.balance_kcal == -bal.burn_kcal
    assert bal.target_balance_kcal is None and bal.goal_configured is False
    assert bal.garmin_total_kcal == 2600


def test_settings_override_profile(db: Session) -> None:
    _athlete(db, gender=None, height_cm=None)
    _goal(db, sex="female", height_cm=165.0, birth_date=date(1996, 6, 1))
    bal = service.energy_balance(db, TODAY, clock=_clock(db))
    assert bal.bmr is not None and bal.bmr.source == "formulas"
    assert (bal.bmr.sex, bal.bmr.height_cm, bal.bmr.age_years) == ("female", 165.0, 29)
    assert bal.bmr.weight_kg == 80.0  # athlete profile weight, no weigh-ins
