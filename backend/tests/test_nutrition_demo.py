"""Demo food diary: present, deterministic, consistent with Garmin's burn and physiology."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.db import migrate
from garminizer.demo.seed import seed_demo
from tests.conftest import create_fresh_database

END = date(2026, 6, 30)


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    url = create_fresh_database("_nutrition_demo")
    migrate.upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
        s.rollback()
    engine.dispose()


def _one(s: Session, sql: str) -> dict[str, Any]:
    return dict(s.execute(text(sql)).mappings().one())


def _fingerprint(s: Session) -> tuple[object, ...]:
    r = _one(
        s,
        "SELECT count(*) AS n, round(sum(kcal)) AS kcal, round(sum(protein_g)) AS p, "
        "string_agg(name, '|' ORDER BY meal_id) AS names, "
        "(SELECT count(*) FROM garmin.meal_item) AS items FROM garmin.meal",
    )
    return tuple(r.values())


def test_demo_meals_are_deterministic(session: Session) -> None:
    seed_demo(session, end=END, days=21, seed=5)
    first = _fingerprint(session)
    assert first[0]
    seed_demo(session, end=END, days=21, seed=5)
    assert _fingerprint(session) == first
    seed_demo(session, end=END, days=21, seed=6)
    assert _fingerprint(session) != first


def test_demo_meals_are_plausible(session: Session) -> None:
    report = seed_demo(session, end=END, days=90, seed=3)
    assert report.rows["meal"] > 200
    assert report.rows["meal_item"] > report.rows["meal"] * 2
    per_day = _one(
        session,
        "SELECT min(n) AS lo, max(n) AS hi, count(*) AS days FROM "
        "(SELECT day, count(*) AS n FROM garmin.meal GROUP BY day) d",
    )
    assert 3 <= per_day["lo"] <= per_day["hi"] <= 5
    assert 70 <= per_day["days"] <= 87  # ~10 % of days not logged
    assert _one(session, "SELECT count(*) AS n FROM garmin.meal WHERE source <> 'demo'")["n"] == 0
    # Meal totals are exactly the sum of their items.
    off = _one(
        session,
        "SELECT count(*) AS n FROM garmin.meal m JOIN (SELECT meal_id, sum(kcal) AS k, "
        "sum(protein_g) AS p FROM garmin.meal_item GROUP BY meal_id) i USING (meal_id) "
        "WHERE abs(m.kcal - i.k) > 0.5 OR abs(m.protein_g - i.p) > 0.5",
    )
    assert off["n"] == 0
    # Macros add up to the energy (Atwater) for every meal.
    bad = _one(
        session,
        "SELECT count(*) AS n FROM garmin.meal WHERE abs(4 * protein_g + 4 * carbs_g + "
        "9 * fat_g + 7 * coalesce(alcohol_g, 0) - kcal) > greatest(0.15 * kcal, 10)",
    )
    assert bad["n"] == 0
    energy = _one(
        session,
        "SELECT avg(n.kcal - d.total_kcal)::float8 AS balance, "
        "stddev(n.kcal - d.total_kcal)::float8 AS sd, avg(n.p / w.kg)::float8 AS p_per_kg "
        "FROM (SELECT day, sum(kcal) AS kcal, sum(protein_g) AS p FROM garmin.meal GROUP BY day) n "
        "JOIN garmin.daily_summary d USING (day) "
        "CROSS JOIN (SELECT avg(weight_kg) AS kg FROM garmin.body_composition) w",
    )
    assert -350 < energy["balance"] < 0  # slight deficit: the demo athlete slowly loses weight
    assert 80 < energy["sd"] < 400  # day-to-day noise, not a copy of Garmin's number
    assert 1.6 <= energy["p_per_kg"] <= 2.0
    carbs = session.execute(
        text(
            "SELECT (a.day IS NOT NULL) AS trained, avg(n.c * 4 / n.kcal)::float8 AS share "
            "FROM (SELECT day, sum(carbs_g) AS c, sum(kcal) AS kcal FROM garmin.meal "
            "GROUP BY day) n LEFT JOIN (SELECT DISTINCT start_time_local::date AS day "
            "FROM garmin.activity) a USING (day) GROUP BY 1"
        )
    ).all()
    share = {bool(r[0]): float(r[1]) for r in carbs}
    assert share[True] > share[False] + 0.03  # more carbohydrate on training days
    portions = _one(session, "SELECT max(grams) AS hi FROM garmin.meal_item")
    assert portions["hi"] <= 500
