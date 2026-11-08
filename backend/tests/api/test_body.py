"""S4 body endpoint: weigh-ins, 7-day trend, blood pressure, latest values, 30-day change."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.api.routers.body import BodyTrendPoint, change_30d


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, q: str, **params: Any) -> Any:
    return s.execute(text(q), params).scalar_one()


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


TZ = "(SELECT time_zone FROM garmin.athlete)"


def sql_trend(s: Session) -> dict[str, tuple[float, float]]:
    """Independent trend: SQL window over daily means, 7 calendar days trailing."""
    result = s.execute(
        text(
            f"""
            WITH d AS (
              SELECT (measured_at AT TIME ZONE {TZ})::date AS day,
                     avg(weight_kg) AS w, avg(body_fat_pct) AS f
              FROM garmin.body_composition GROUP BY 1)
            SELECT day,
                   avg(w) OVER win AS w, avg(f) OVER win AS f
            FROM d WINDOW win AS (ORDER BY day RANGE BETWEEN '6 days' PRECEDING AND CURRENT ROW)
            """
        )
    ).all()
    return {r.day.isoformat(): (float(r.w), float(r.f)) for r in result}


def test_body_overview(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/body")
    assert resp.status_code == 200
    body = resp.json()
    n = scalar(sql, "SELECT count(*) FROM garmin.body_composition")
    assert len(body["weigh_ins"]) == n > 50
    assert len(body["blood_pressure"]) == scalar(sql, "SELECT count(*) FROM garmin.blood_pressure")
    assert {"bmi", "muscle_mass_kg", "visceral_fat", "source"} <= set(body["weigh_ins"][0])
    assert {"systolic", "diastolic", "pulse", "category"} <= set(body["blood_pressure"][0])
    last = sql.execute(
        text("SELECT * FROM garmin.body_composition ORDER BY measured_at DESC LIMIT 1")
    ).one()
    assert body["latest"]["weight_kg"] == pytest.approx(last.weight_kg)
    assert body["latest"]["body_fat_pct"] == pytest.approx(last.body_fat_pct)
    assert ts(body["latest"]["measured_at"]) == last.measured_at
    assert body["goal"] is None


def test_trend_is_trailing_7_day_mean(client: TestClient, sql: Session) -> None:
    body = client.get("/api/body").json()
    expected = sql_trend(sql)
    days = scalar(
        sql,
        f"SELECT count(DISTINCT (measured_at AT TIME ZONE {TZ})::date) "
        "FROM garmin.body_composition",
    )
    assert len(body["trend"]) == days == len(expected)
    for p in body["trend"]:
        w, f = expected[p["day"]]
        assert p["weight_kg"] == pytest.approx(w, abs=0.006)
        assert p["body_fat_pct"] == pytest.approx(f, abs=0.006)


def test_trend_window_reaches_before_range_start(client: TestClient, sql: Session) -> None:
    body = client.get("/api/body?start=2026-06-01&end=2026-06-30").json()
    assert body["weigh_ins"]
    assert all(
        "2026-05-31T22:00" <= w["measured_at"] < "2026-06-30T22:00" for w in body["weigh_ins"]
    )
    first = body["trend"][0]
    assert first["day"] >= "2026-06-01"
    assert first["weight_kg"] == pytest.approx(sql_trend(sql)[first["day"]][0], abs=0.006)


def test_change_30d(client: TestClient) -> None:
    body = client.get("/api/body").json()
    trend = body["trend"]
    last = date.fromisoformat(trend[-1]["day"])
    target = last - timedelta(days=30)
    ref = min(trend, key=lambda p: abs((date.fromisoformat(p["day"]) - target).days))
    assert abs((date.fromisoformat(ref["day"]) - target).days) <= 7
    assert body["change_30d_kg"] == pytest.approx(
        trend[-1]["weight_kg"] - ref["weight_kg"], abs=0.01
    )


def test_change_30d_needs_enough_history() -> None:
    p = [
        BodyTrendPoint(day=date(2026, 1, d), weight_kg=70.0 + d, body_fat_pct=None) for d in (1, 5)
    ]
    assert change_30d(p) is None
    assert change_30d([]) is None
    q = [
        BodyTrendPoint(day=date(2026, 1, 1), weight_kg=72.0, body_fat_pct=None),
        BodyTrendPoint(day=date(2026, 1, 31), weight_kg=71.0, body_fat_pct=None),
    ]
    assert change_30d(q) == -1.0


def test_empty_range(client: TestClient) -> None:
    body = client.get("/api/body?start=2020-01-01&end=2020-01-31").json()
    assert body == {
        "weigh_ins": [],
        "trend": [],
        "blood_pressure": [],
        "latest": None,
        "change_30d_kg": None,
        "goal": None,
    }
