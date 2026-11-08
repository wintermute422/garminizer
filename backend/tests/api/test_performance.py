"""S4: /api/performance endpoints, cross-checked against the base tables of the demo DB."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END

SERIES = ("vo2max", "race_predictions", "endurance", "hill", "fitness_age")


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, query: str, **params: Any) -> Any:
    return s.execute(text(query), params).scalar()


def latest(s: Session, table: str, column: str, end: date) -> Any:
    return scalar(
        s,
        f"SELECT {column} FROM garmin.{table} WHERE day <= :end AND {column} IS NOT NULL "
        "ORDER BY day DESC LIMIT 1",
        end=end,
    )


def test_performance_series(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/performance")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {*SERIES, "latest"}
    start = API_END - timedelta(days=364)
    for name in SERIES:
        assert body[name], name
        days = [date.fromisoformat(p["day"]) for p in body[name]]
        assert days == sorted(set(days)), name
        assert start <= days[0] and days[-1] <= API_END, name
    assert set(body["vo2max"][0]) == {"day", "running", "cycling"}
    assert set(body["race_predictions"][0]) == {
        "day",
        "time_5k_s",
        "time_10k_s",
        "time_half_s",
        "time_marathon_s",
    }
    assert set(body["endurance"][0]) == {"day", "score", "classification"}
    assert set(body["hill"][0]) == {"day", "score", "endurance", "strength"}
    assert set(body["fitness_age"][0]) == {"day", "value"}
    n_vo2 = scalar(
        sql,
        "SELECT count(*) FROM garmin.max_metric WHERE day BETWEEN :a AND :b "
        "AND (vo2max_running IS NOT NULL OR vo2max_cycling IS NOT NULL)",
        a=start,
        b=API_END,
    )
    assert len(body["vo2max"]) == n_vo2
    cycling = [p for p in body["vo2max"] if p["cycling"] is not None]
    assert len(cycling) == scalar(
        sql,
        "SELECT count(vo2max_cycling) FROM garmin.max_metric WHERE day BETWEEN :a AND :b",
        a=start,
        b=API_END,
    )
    first = body["race_predictions"][0]
    marathon = scalar(
        sql,
        "SELECT time_marathon_s FROM garmin.race_prediction WHERE day = :d",
        d=date.fromisoformat(first["day"]),
    )
    assert first["time_marathon_s"] == pytest.approx(marathon)


@pytest.mark.parametrize("end", [API_END, date(2026, 4, 30)])
def test_performance_latest_values(client: TestClient, sql: Session, end: date) -> None:
    body = client.get("/api/performance", params={"end": end.isoformat()}).json()
    assert all(date.fromisoformat(p["day"]) <= end for name in SERIES for p in body[name])
    got = body["latest"]
    expected = {
        "vo2max_running": latest(sql, "max_metric", "vo2max_running", end),
        "vo2max_cycling": latest(sql, "max_metric", "vo2max_cycling", end),
        "fitness_age": latest(sql, "max_metric", "fitness_age", end),
        "time_5k_s": latest(sql, "race_prediction", "time_5k_s", end),
        "time_10k_s": latest(sql, "race_prediction", "time_10k_s", end),
        "time_half_s": latest(sql, "race_prediction", "time_half_s", end),
        "time_marathon_s": latest(sql, "race_prediction", "time_marathon_s", end),
        "endurance_score": latest(sql, "endurance_score", "score", end),
        "hill_score": latest(sql, "hill_score", "score", end),
    }
    assert set(got) == {*expected, "endurance_class"}
    for key, value in expected.items():
        assert value is not None, key
        assert got[key] == pytest.approx(value), key
    assert got["endurance_class"] == latest(sql, "endurance_score", "classification", end)
    # The latest values are the last points of the series (every day has data in the demo).
    assert got["vo2max_running"] == pytest.approx(body["vo2max"][-1]["running"])
    assert got["time_5k_s"] == pytest.approx(body["race_predictions"][-1]["time_5k_s"])


def test_efficiency_defaults_to_runs(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/performance/efficiency")
    assert resp.status_code == 200
    body = resp.json()
    n = scalar(
        sql,
        "SELECT count(*) FROM garmin.activity WHERE sport_group = 'run' "
        "AND efficiency_factor IS NOT NULL",
    )
    assert n > 10
    assert len(body) == n
    assert set(body[0]) == {
        "activity_id",
        "day",
        "name",
        "sport_group",
        "efficiency_factor",
        "aerobic_decoupling_pct",
        "avg_hr",
        "avg_speed_mps",
        "avg_power_w",
        "distance_m",
        "duration_s",
    }
    assert {p["sport_group"] for p in body} == {"run"}
    assert all(p["efficiency_factor"] is not None for p in body)
    days = [p["day"] for p in body]
    assert days == sorted(days)
    ef = scalar(
        sql,
        "SELECT efficiency_factor FROM garmin.activity WHERE activity_id = :i",
        i=body[-1]["activity_id"],
    )
    assert body[-1]["efficiency_factor"] == pytest.approx(ef)


def test_efficiency_other_sport_and_range(client: TestClient, sql: Session) -> None:
    rides = client.get("/api/performance/efficiency", params={"sport": "ride"}).json()
    assert rides
    assert {p["sport_group"] for p in rides} == {"ride"}
    params = {"start": "2026-05-01", "end": "2026-05-31"}
    may = client.get("/api/performance/efficiency", params=params).json()
    assert all(params["start"] <= p["day"] <= params["end"] for p in may)
    assert len(may) == scalar(
        sql,
        "SELECT count(*) FROM garmin.activity WHERE sport_group = 'run' "
        "AND efficiency_factor IS NOT NULL "
        "AND start_time_local >= '2026-05-01' AND start_time_local < '2026-06-01'",
    )
    assert client.get("/api/performance/efficiency", params={"sport": "x"}).status_code == 422
