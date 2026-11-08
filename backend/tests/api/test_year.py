"""/api/year: per-year summaries and the year in review, cross-checked with SQL."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END

YEAR = API_END.year
Y0, Y1 = date(YEAR, 1, 1), date(YEAR + 1, 1, 1)
IN_YEAR = "start_time_local >= :y0 AND start_time_local < :y1"


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in s.execute(text(query), params)]


def _one(s: Session, query: str) -> dict[str, Any]:
    return _rows(s, query, y0=Y0, y1=Y1)[0]


@pytest.fixture(scope="module")
def review(client: TestClient) -> dict[str, Any]:
    resp = client.get(f"/api/year/{YEAR}")
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def test_year_list(client: TestClient, sql: Session) -> None:
    years = client.get("/api/year").json()
    assert [y["year"] for y in years] == sorted({y["year"] for y in years}, reverse=True)
    this = next(y for y in years if y["year"] == YEAR)
    e = _one(
        sql,
        "SELECT count(*) AS n, sum(distance_m) AS dist, sum(duration_s) AS dur "
        f"FROM garmin.activity WHERE {IN_YEAR}",
    )
    assert this["activities"] == e["n"] > 0
    assert this["distance_m"] == pytest.approx(e["dist"], abs=0.1)
    assert this["duration_s"] == pytest.approx(e["dur"], abs=0.1)


def test_totals_match_sql(review: dict[str, Any], sql: Session) -> None:
    e = _one(
        sql,
        "SELECT count(*) AS activities, sum(distance_m) AS distance_m, "
        "sum(duration_s) AS duration_s, sum(moving_s) AS moving_s, "
        "sum(elevation_gain_m::float8) AS elevation_gain_m, "
        "sum(calories::float8) AS calories, sum(training_load::float8) AS training_load, "
        "count(DISTINCT start_time_local::date) AS active_days "
        f"FROM garmin.activity WHERE {IN_YEAR}",
    )
    t = review["totals"]
    assert t["activities"] == e["activities"]
    assert t["active_days"] == e["active_days"]
    for key in ("distance_m", "duration_s", "moving_s", "elevation_gain_m", "calories"):
        assert t[key] == pytest.approx(e[key], abs=0.2), key
    assert t["training_load"] == pytest.approx(e["training_load"], rel=1e-5)
    assert sum(s["activities"] for s in review["by_sport"]) == t["activities"]
    assert sum(s["distance_m"] for s in review["by_sport"]) == pytest.approx(t["distance_m"], abs=1)
    assert len(review["days"]) == t["active_days"]
    assert sum(d["duration_s"] for d in review["days"]) == pytest.approx(t["duration_s"], abs=1)


def test_monthly_and_best_month(review: dict[str, Any]) -> None:
    monthly = review["monthly"]
    assert [m["month"] for m in monthly] == list(range(1, 13))
    assert sum(m["activities"] for m in monthly) == review["totals"]["activities"]
    best = max(monthly, key=lambda m: m["distance_m"])
    assert review["best_month"] == {"month": best["month"], "distance_m": best["distance_m"]}
    assert review["longest_streak"] >= 1


def test_highlights(review: dict[str, Any], sql: Session) -> None:
    e = _one(
        sql,
        "SELECT max(distance_m) AS d, max(duration_s) AS t, max(elevation_gain_m) AS e, "
        f"max(training_load) AS l FROM garmin.activity WHERE {IN_YEAR}",
    )
    h = review["highlights"]
    assert h["longest_distance"]["distance_m"] == pytest.approx(e["d"])
    assert h["longest_duration"]["duration_s"] == pytest.approx(e["t"])
    assert h["most_elevation"]["elevation_gain_m"] == pytest.approx(e["e"])
    assert h["hardest_load"]["training_load"] == pytest.approx(e["l"])


def test_best_efforts_are_fastest_per_distance(review: dict[str, Any], sql: Session) -> None:
    e = _rows(
        sql,
        "SELECT b.distance_m, min(b.seconds) AS seconds FROM garmin.activity_best_distance b "
        f"JOIN garmin.activity a USING (activity_id) WHERE {IN_YEAR} GROUP BY 1",
        y0=Y0,
        y1=Y1,
    )
    got = {b["distance_m"]: b for b in review["best_efforts"]}
    assert e
    assert set(got) == {r["distance_m"] for r in e}
    for r in e:
        assert got[r["distance_m"]]["seconds"] == pytest.approx(r["seconds"], abs=0.05)


def test_health_and_tiles(review: dict[str, Any], sql: Session) -> None:
    sleep = _one(
        sql,
        "SELECT avg(duration_s)::float8 AS d, avg(score)::float8 AS s FROM garmin.sleep "
        "WHERE day >= :y0 AND day < :y1",
    )
    assert review["sleep"]["avg_duration_s"] == pytest.approx(sleep["d"], abs=0.05)
    assert review["sleep"]["avg_score"] == pytest.approx(sleep["s"], abs=0.05)
    steps = _one(
        sql, "SELECT sum(steps) AS t FROM garmin.daily_summary WHERE day >= :y0 AND day < :y1"
    )
    assert review["steps"]["total"] == steps["t"]
    vo2 = _rows(
        sql,
        "SELECT vo2max_running AS v FROM garmin.max_metric WHERE day >= :y0 AND day < :y1 "
        "AND vo2max_running IS NOT NULL ORDER BY day",
        y0=Y0,
        y1=Y1,
    )
    assert review["vo2max"] == {
        "first": pytest.approx(vo2[0]["v"], abs=0.05),
        "last": pytest.approx(vo2[-1]["v"], abs=0.05),
    }
    assert review["resting_hr"]["first_30d_avg"] is not None
    assert review["resting_hr"]["last_30d_avg"] is not None
    tiles = _one(
        sql,
        "SELECT count(*) AS n FROM (SELECT min(a.start_time_local) AS f "
        "FROM garmin.activity_tile t JOIN garmin.activity a USING (activity_id) "
        "WHERE t.zoom = 14 GROUP BY t.x, t.y) s WHERE f >= :y0 AND f < :y1",
    )
    assert review["new_tiles"] == tiles["n"] > 0


def test_unknown_years(client: TestClient) -> None:
    assert client.get("/api/year/1999").status_code == 404
    assert client.get("/api/year/1800").status_code == 422
