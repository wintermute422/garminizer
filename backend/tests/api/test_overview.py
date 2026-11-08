"""/api/overview: one day's snapshot, cross-checked against the base tables."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.analytics.stats import streaks
from tests.api.conftest import API_END

TOP_LEVEL = {
    "day",
    "readiness",
    "sleep",
    "hrv",
    "resting_hr",
    "body_battery",
    "stress",
    "steps",
    "intensity_minutes",
    "training_status",
    "fitness",
    "vo2max",
    "race_predictions",
    "week",
    "recent_activities",
    "streak",
}


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in s.execute(text(query), params)]


@pytest.fixture(scope="module")
def overview(client: TestClient) -> dict[str, Any]:
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    return body


def test_shape_and_default_day(overview: dict[str, Any]) -> None:
    assert set(overview) == TOP_LEVEL
    assert overview["day"] == API_END.isoformat()
    for key in ("readiness", "sleep", "hrv", "training_status", "race_predictions"):
        assert overview[key] is not None, key
    assert len(overview["recent_activities"]) == 6
    assert overview["intensity_minutes"]["goal"] == 150
    assert set(overview["fitness"]) == {"ctl", "atl", "tsb", "ctl_delta_28d"}


def test_daily_values_match_tables(overview: dict[str, Any], sql: Session) -> None:
    day = API_END
    d = _rows(sql, "SELECT * FROM garmin.daily_summary WHERE day = :d", d=day)[0]
    assert overview["resting_hr"]["value"] == d["resting_hr"]
    assert overview["steps"] == {
        "value": d["steps"],
        "goal": d["step_goal"],
        "avg_7d": pytest.approx(
            _rows(
                sql,
                "SELECT avg(steps)::float8 AS v FROM garmin.daily_summary "
                "WHERE day BETWEEN :a AND :b",
                a=day - timedelta(days=6),
                b=day,
            )[0]["v"],
            abs=0.1,
        ),
    }
    rhr_30 = _rows(
        sql,
        "SELECT avg(resting_hr)::float8 AS v FROM garmin.daily_summary WHERE day BETWEEN :a AND :b",
        a=day - timedelta(days=29),
        b=day,
    )[0]["v"]
    assert overview["resting_hr"]["avg_30d"] == pytest.approx(rhr_30, abs=0.1)
    assert overview["stress"] == {"avg": d["avg_stress"], "max": d["max_stress"]}
    monday = day - timedelta(days=day.weekday())
    im = _rows(
        sql,
        "SELECT sum(moderate_intensity_min + 2 * vigorous_intensity_min) AS v "
        "FROM garmin.daily_summary WHERE day BETWEEN :a AND :b",
        a=monday,
        b=day,
    )[0]["v"]
    assert overview["intensity_minutes"]["week_total"] == im
    sleep = _rows(sql, "SELECT duration_s, score FROM garmin.sleep WHERE day = :d", d=day)[0]
    assert overview["sleep"]["duration_s"] == sleep["duration_s"]
    assert overview["sleep"]["score"] == sleep["score"]
    load = _rows(sql, "SELECT ctl FROM garmin.daily_load WHERE day = :d", d=day)[0]
    assert overview["fitness"]["ctl"] == pytest.approx(load["ctl"], abs=1e-3)


def test_body_battery_series_covers_the_local_day(overview: dict[str, Any]) -> None:
    tz = ZoneInfo("Europe/Berlin")  # the demo athlete's zone
    start = datetime.combine(API_END, datetime.min.time(), tz)
    end = start + timedelta(days=1)
    bb = overview["body_battery"]
    series = bb["series"]
    assert len(series) > 100
    stamps = [datetime.fromisoformat(p["ts"]) for p in series]
    assert all(start <= t < end for t in stamps)
    assert stamps == sorted(stamps)
    assert bb["latest"] == series[-1]["value"]


def test_week_totals_match_activities(overview: dict[str, Any], sql: Session) -> None:
    monday = API_END - timedelta(days=API_END.weekday())
    for key, a, b in (
        ("this_week", monday, API_END + timedelta(days=1)),
        ("last_week", monday - timedelta(days=7), monday),
    ):
        expected = _rows(
            sql,
            "SELECT sport_group, count(*) AS n, coalesce(sum(distance_m), 0) AS dist, "
            "sum(duration_s) AS dur FROM garmin.activity "
            "WHERE start_time_local >= :a AND start_time_local < :b GROUP BY 1",
            a=a,
            b=b,
        )
        got = {w["sport_group"]: w for w in overview["week"][key]}
        assert set(got) == {e["sport_group"] for e in expected}, key
        for e in expected:
            g = got[e["sport_group"]]
            assert g["activities"] == e["n"]
            assert (g["distance_m"] or 0) == pytest.approx(e["dist"], abs=0.1)
            assert g["duration_s"] == pytest.approx(e["dur"], abs=0.1)
    assert sum(w["activities"] for w in overview["week"]["this_week"]) > 0


def test_recent_activities_and_streak(overview: dict[str, Any], sql: Session) -> None:
    newest = _rows(
        sql, "SELECT activity_id FROM garmin.activity ORDER BY start_time_utc DESC LIMIT 6"
    )
    assert [a["activity_id"] for a in overview["recent_activities"]] == [
        r["activity_id"] for r in newest
    ]
    days = _rows(sql, "SELECT DISTINCT start_time_local::date AS d FROM garmin.activity")
    current, longest, _ = streaks([r["d"] for r in days], today=API_END)
    assert overview["streak"] == {"current": current, "longest": longest}
    assert longest >= current >= 1


def test_vo2max_delta(overview: dict[str, Any], sql: Session) -> None:
    def latest(on: date) -> float:
        r = _rows(
            sql,
            "SELECT vo2max_running AS v FROM garmin.max_metric WHERE day <= :d "
            "AND vo2max_running IS NOT NULL ORDER BY day DESC LIMIT 1",
            d=on,
        )
        return float(r[0]["v"])

    now, before = latest(API_END), latest(API_END - timedelta(days=30))
    assert overview["vo2max"]["running"] == pytest.approx(now)
    assert overview["vo2max"]["delta_30d"] == pytest.approx(now - before, abs=0.01)


def test_past_day(client: TestClient) -> None:
    day = date(2026, 5, 15)
    body = client.get("/api/overview", params={"day": day.isoformat()}).json()
    assert body["day"] == day.isoformat()
    assert body["recent_activities"]
    assert all(a["start_time_local"][:10] <= day.isoformat() for a in body["recent_activities"])


def test_day_without_data(client: TestClient) -> None:
    resp = client.get("/api/overview", params={"day": "2020-01-01"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["readiness"] is None
    assert body["sleep"] is None
    assert body["recent_activities"] == []
    assert body["body_battery"]["series"] == []
    assert body["streak"] == {"current": 0, "longest": 0}
    assert body["intensity_minutes"]["week_total"] == 0
