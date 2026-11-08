"""/api/nutrition: daily intake vs Garmin burn, meals, day view, summary, targets, writes.

GET results are cross-checked against SQL on the demo database (which has synthetic meals).
Write tests clean up after themselves so the shared API database stays as seeded.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_DAYS, API_END, CSRF

START = API_END - timedelta(days=API_DAYS - 1)
RANGE = {"start": START.isoformat(), "end": API_END.isoformat()}
LUNCH = {
    "name": "Chicken rice bowl",
    "eaten_at": f"{API_END.isoformat()}T12:30:00",
    "items": [
        {
            "food": "Chicken breast",
            "grams": 150,
            "kcal": 248,
            "protein_g": 46.5,
            "fat_g": 5.4,
            "carbs_g": 0,
        },
        {
            "food": "Rice, cooked",
            "grams": 200,
            "kcal": 260,
            "protein_g": 5.4,
            "carbs_g": 56.4,
            "fat_g": 0.6,
            "fiber_g": 0.8,
        },
    ],
    "confidence": "medium",
}


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    s.rollback()  # fresh snapshot: the API commits in its own connection
    return [dict(r._mapping) for r in s.execute(text(query), params)]


def test_daily_matches_sql(client: TestClient, sql: Session) -> None:
    body = client.get("/api/nutrition/daily", params=RANGE).json()
    expected = _rows(
        sql,
        """
        SELECT coalesce(n.day, d.day) AS day, coalesce(n.meals, 0) AS meals, n.kcal, n.protein,
               d.total_kcal, d.active_kcal
        FROM (SELECT day, count(*) AS meals, sum(kcal)::float8 AS kcal,
                     sum(protein_g)::float8 AS protein
              FROM garmin.meal WHERE day BETWEEN :a AND :b GROUP BY day) n
        FULL JOIN (SELECT day, total_kcal::float8, active_kcal::float8 FROM garmin.daily_summary
                   WHERE day BETWEEN :a AND :b AND total_kcal IS NOT NULL) d ON d.day = n.day
        ORDER BY 1
        """,
        a=START,
        b=API_END,
    )
    assert len(body) == len(expected) == API_DAYS
    for got, exp in zip(body, expected, strict=True):
        assert date.fromisoformat(got["day"]) == exp["day"]
        assert got["meals"] == exp["meals"]
        assert got["total_kcal"] == pytest.approx(exp["total_kcal"], abs=0.1)
        if exp["meals"]:
            assert got["intake_kcal"] == pytest.approx(exp["kcal"], abs=0.1)
            assert got["protein_g"] == pytest.approx(exp["protein"], abs=0.1)
            assert got["balance_kcal"] == pytest.approx(exp["kcal"] - exp["total_kcal"], abs=0.2)
        else:
            assert got["intake_kcal"] is None
            assert got["balance_kcal"] is None
    logged = sum(1 for p in body if p["meals"])
    assert 0.75 * API_DAYS < logged < API_DAYS  # about one day in ten is not logged


def test_default_range_ends_on_the_last_day_with_data(client: TestClient) -> None:
    body = client.get("/api/nutrition/daily").json()
    assert body[-1]["day"] == API_END.isoformat()
    assert (
        client.get(
            "/api/nutrition/daily", params={"start": "2026-02-01", "end": "2026-01-01"}
        ).status_code
        == 422
    )


def test_summary_matches_sql(client: TestClient, sql: Session) -> None:
    s = client.get("/api/nutrition/summary", params=RANGE).json()
    exp = _rows(
        sql,
        """
        WITH n AS (SELECT day, count(*) AS meals, sum(kcal) AS kcal, sum(protein_g) AS p,
                          sum(carbs_g) AS c, sum(fat_g) AS f, sum(coalesce(alcohol_g, 0)) AS a
                   FROM garmin.meal WHERE day BETWEEN :a AND :b GROUP BY day)
        SELECT count(*) AS days_logged, sum(meals) AS meals, avg(kcal)::float8 AS kcal,
               avg(p)::float8 AS p, avg(n.kcal - d.total_kcal)::float8 AS balance,
               avg(d.total_kcal)::float8 AS burn,
               (sum(4 * p) / sum(4 * p + 4 * c + 9 * f + 7 * a))::float8 AS p_share
        FROM n LEFT JOIN garmin.daily_summary d USING (day)
        """,
        a=START,
        b=API_END,
    )[0]
    assert s["days"] == API_DAYS
    assert s["days_logged"] == exp["days_logged"]
    assert s["meals"] == exp["meals"]
    assert s["avg_intake_kcal"] == pytest.approx(exp["kcal"], abs=0.2)
    assert s["avg_protein_g"] == pytest.approx(exp["p"], abs=0.2)
    assert s["avg_total_kcal"] == pytest.approx(exp["burn"], abs=0.2)
    assert s["avg_balance_kcal"] == pytest.approx(exp["balance"], abs=0.2)
    split = s["macro_split"]
    assert split["protein_pct"] == pytest.approx(exp["p_share"] * 100, abs=0.1)
    assert sum(split.values()) == pytest.approx(100, abs=0.3)
    weight = _rows(
        sql,
        "SELECT weight_kg::float8 AS w FROM garmin.body_composition "
        "WHERE measured_at < :t ORDER BY measured_at DESC LIMIT 1",
        t=API_END + timedelta(days=1),
    )[0]["w"]
    assert s["weight_kg"] == pytest.approx(weight, abs=0.05)
    assert s["protein_g_per_kg"] == pytest.approx(exp["p"] / weight, abs=0.01)
    # Demo calibration: endurance-athlete protein, slight deficit (slow weight loss).
    assert 1.5 <= s["protein_g_per_kg"] <= 2.2
    assert -400 < s["avg_balance_kcal"] < 0
    assert [t["meal_type"] for t in s["by_meal_type"]][:3] == ["breakfast", "lunch", "dinner"]
    assert sum(t["kcal_pct"] for t in s["by_meal_type"]) == pytest.approx(100, abs=0.3)
    weeks = s["weeks"]
    assert 20 <= len(weeks) <= 23
    assert all(date.fromisoformat(w["week"]).weekday() == 0 for w in weeks)
    assert sum(w["days_logged"] for w in weeks) == exp["days_logged"]
    assert sum(1 for w in weeks if w["weight_kg"] is not None) >= len(weeks) - 2


def test_meals_of_a_day_with_items(client: TestClient, sql: Session) -> None:
    day = API_END - timedelta(days=3)
    meals = client.get("/api/nutrition/meals", params={"day": day.isoformat()}).json()
    count = _rows(sql, "SELECT count(*) AS n FROM garmin.meal WHERE day = :d", d=day)[0]["n"]
    assert len(meals) == count
    for meal in meals:
        assert meal["day"] == day.isoformat()
        assert meal["source"] == "demo"
        assert meal["items"]
        assert sum(i["kcal"] for i in meal["items"]) == pytest.approx(meal["kcal"], abs=0.5)
        assert meal["warnings"] == []
    times = [meal["eaten_at"] for meal in meals]
    assert times == sorted(times)
    week = client.get("/api/nutrition/meals").json()  # default: last 7 days up to the last day
    assert {m["day"] for m in week} <= {(API_END - timedelta(days=i)).isoformat() for i in range(7)}
    assert week


def test_day_view_matches_sql(client: TestClient, sql: Session) -> None:
    day = API_END - timedelta(days=1)
    body = client.get("/api/nutrition/day", params={"day": day.isoformat()}).json()
    exp = _rows(
        sql,
        "SELECT count(*) AS n, coalesce(sum(kcal), 0)::float8 AS kcal FROM garmin.meal "
        "WHERE day = :d",
        d=day,
    )[0]
    burn = _rows(
        sql, "SELECT total_kcal::float8 AS t FROM garmin.daily_summary WHERE day = :d", d=day
    )[0]["t"]
    assert body["totals"]["meals"] == exp["n"] == len(body["meals"])
    assert body["totals"]["kcal"] == pytest.approx(exp["kcal"], abs=0.5)
    assert body["garmin"]["total_kcal"] == pytest.approx(burn, abs=0.1)
    if exp["n"]:
        assert body["balance_kcal"] == pytest.approx(exp["kcal"] - burn, abs=0.5)
    assert client.get("/api/nutrition/day").status_code == 200  # default: today


def test_v_daily_has_intake_columns(sql: Session) -> None:
    rows = _rows(
        sql,
        """
        SELECT v.day, v.intake_kcal::float8 AS v_kcal, v.energy_balance_kcal::float8 AS v_bal,
               n.kcal, d.total_kcal::float8 AS burn
        FROM garmin.v_daily v
        JOIN garmin.daily_summary d USING (day)
        LEFT JOIN (SELECT day, sum(kcal)::float8 AS kcal FROM garmin.meal GROUP BY day) n
          USING (day)
        """,
    )
    assert rows
    for r in rows:
        if r["kcal"] is None:
            assert r["v_kcal"] is None
            assert r["v_bal"] is None
        else:
            assert r["v_kcal"] == pytest.approx(r["kcal"], abs=0.5)
            assert r["v_bal"] == pytest.approx(r["kcal"] - r["burn"], abs=0.5)


def test_targets_round_trip(client: TestClient) -> None:
    before = client.get("/api/nutrition/targets").json()
    try:
        assert client.put("/api/nutrition/targets", json={"kcal": 2500}).status_code == 403
        resp = client.put(
            "/api/nutrition/targets",
            json={"kcal": 2600, "protein_g_per_kg": 1.8, "fiber_g": 35},
            headers=CSRF,
        )
        assert resp.status_code == 200
        assert client.get("/api/nutrition/targets").json() == {
            "kcal": 2600,
            "protein_g": None,
            "carbs_g": None,
            "fat_g": None,
            "fiber_g": 35,
            "protein_g_per_kg": 1.8,
        }
        day = client.get("/api/nutrition/day", params={"day": API_END.isoformat()}).json()
        assert day["protein_target_g"] == pytest.approx(round(1.8 * day["weight_kg"]))
        assert day["remaining"]["kcal"] == pytest.approx(2600 - day["totals"]["kcal"], abs=0.1)
        bad = client.put("/api/nutrition/targets", json={"kcal": -1}, headers=CSRF)
        assert bad.status_code == 422
    finally:
        client.put("/api/nutrition/targets", json=before, headers=CSRF)


def test_create_update_delete_meal(client: TestClient, sql: Session) -> None:
    assert client.post("/api/nutrition/meals", json=LUNCH).status_code == 403  # CSRF guard
    resp = client.post("/api/nutrition/meals", json=LUNCH, headers=CSRF)
    assert resp.status_code == 201, resp.text
    meal = resp.json()
    meal_id = meal["meal_id"]
    try:
        assert meal["source"] == "manual"
        assert meal["day"] == API_END.isoformat()
        assert meal["meal_type"] == "lunch"
        assert meal["kcal"] == pytest.approx(508)
        assert meal["protein_g"] == pytest.approx(51.9)
        assert meal["eaten_at"].endswith("+02:00")  # demo athlete: Europe/Berlin, summer
        stored = _rows(
            sql, "SELECT kcal::float8, source FROM garmin.meal WHERE meal_id = :i", i=meal_id
        )
        assert stored == [{"kcal": pytest.approx(508), "source": "manual"}]
        day = client.get("/api/nutrition/day", params={"day": API_END.isoformat()}).json()
        assert meal_id in [x["meal_id"] for x in day["meals"]]

        patch = {"items": [LUNCH["items"][0]], "notes": "no rice after all"}
        assert client.patch(f"/api/nutrition/meals/{meal_id}", json=patch).status_code == 403
        resp = client.patch(f"/api/nutrition/meals/{meal_id}", json=patch, headers=CSRF)
        assert resp.status_code == 200, resp.text
        updated = resp.json()
        assert updated["kcal"] == pytest.approx(248)
        assert len(updated["items"]) == 1
        assert updated["notes"] == "no rice after all"
        moved = client.patch(
            f"/api/nutrition/meals/{meal_id}",
            json={"eaten_at": f"{(API_END - timedelta(days=1)).isoformat()}T23:45:00"},
            headers=CSRF,
        ).json()
        assert moved["day"] == (API_END - timedelta(days=1)).isoformat()
        assert moved["meal_type"] == "lunch"
    finally:
        assert client.delete(f"/api/nutrition/meals/{meal_id}").status_code == 403
        assert client.delete(f"/api/nutrition/meals/{meal_id}", headers=CSRF).status_code == 204
    assert (
        _rows(sql, "SELECT count(*) AS n FROM garmin.meal_item WHERE meal_id = :i", i=meal_id)[0][
            "n"
        ]
        == 0
    )
    assert client.delete(f"/api/nutrition/meals/{meal_id}", headers=CSRF).status_code == 404
    assert (
        client.patch(
            f"/api/nutrition/meals/{meal_id}", json={"name": "x"}, headers=CSRF
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Nothing"},  # neither items nor totals.kcal
        {"name": "Neg", "totals": {"kcal": -10}},
        {"name": "Neg", "items": [{"food": "x", "kcal": 100, "fat_g": -1}]},
        {"name": "Typo", "items": [{"food": "x", "kcal": 100, "protein": 5}]},
        {"name": "Later", "totals": {"kcal": 100}, "eaten_at": "2099-01-01T12:00:00"},
        {"name": "Type", "totals": {"kcal": 100}, "meal_type": "brunch"},
    ],
)
def test_invalid_meals_are_rejected(client: TestClient, body: dict[str, Any]) -> None:
    resp = client.post("/api/nutrition/meals", json=body, headers=CSRF)
    assert resp.status_code == 422, resp.text


def test_mismatch_warning_in_api(client: TestClient) -> None:
    body = {
        "name": "Odd bar",
        "eaten_at": f"{API_END.isoformat()}T16:00:00",
        "totals": {"kcal": 100, "protein_g": 20, "carbs_g": 30, "fat_g": 10},
    }
    meal = client.post("/api/nutrition/meals", json=body, headers=CSRF).json()
    try:
        assert [w["code"] for w in meal["warnings"]] == ["macro_kcal_mismatch"]
        assert meal["meal_type"] == "snack"
    finally:
        client.delete(f"/api/nutrition/meals/{meal['meal_id']}", headers=CSRF)
