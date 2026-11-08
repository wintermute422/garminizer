"""S4 calendar endpoints: active days with streaks and the weekday x hour punchcard."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.analytics.stats import streaks
from garminizer.api.routers.calendar import weeks_in_row
from tests.api.conftest import API_END

IN_RANGE = "start_time_local >= :a AND start_time_local < :b"


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, q: str, **params: Any) -> Any:
    return s.execute(text(q), params).scalar_one()


def default_bounds() -> dict[str, date]:
    return {"a": API_END - timedelta(days=364), "b": API_END + timedelta(days=1)}


def test_calendar_days_match_activities(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/calendar")
    assert resp.status_code == 200
    body = resp.json()
    bounds = default_bounds()
    total = scalar(sql, f"SELECT count(*) FROM garmin.activity WHERE {IN_RANGE}", **bounds)
    active = scalar(
        sql,
        f"SELECT count(DISTINCT start_time_local::date) FROM garmin.activity WHERE {IN_RANGE}",
        **bounds,
    )
    assert body["totals"] == {"active_days": active, "activities": total}
    assert len(body["days"]) == active
    assert sum(d["activities"] for d in body["days"]) == total
    for d in body["days"][-5:]:
        db = sql.execute(
            text(
                "SELECT count(*) AS n, coalesce(sum(duration_s), 0) AS dur, "
                "coalesce(sum(distance_m), 0) AS dist, coalesce(sum(training_load), 0) AS load, "
                "array_agg(DISTINCT sport_group) AS groups "
                "FROM garmin.activity WHERE start_time_local::date = :d"
            ),
            {"d": date.fromisoformat(d["day"])},
        ).one()
        assert d["activities"] == db.n
        assert d["duration_s"] == pytest.approx(db.dur)
        assert d["distance_m"] == pytest.approx(db.dist)
        assert d["training_load"] == pytest.approx(db.load, rel=1e-5)
        assert d["sport_groups"] == sorted(db.groups)


def test_calendar_streaks(client: TestClient, sql: Session) -> None:
    body = client.get("/api/calendar").json()
    days = [
        r[0]
        for r in sql.execute(
            text(f"SELECT DISTINCT start_time_local::date FROM garmin.activity WHERE {IN_RANGE}"),
            default_bounds(),
        ).all()
    ]
    current, longest, longest_start = streaks(days, today=API_END)
    assert body["streak"] == {
        "current": current,
        "longest": longest,
        "longest_start": longest_start.isoformat() if longest_start else None,
    }
    assert longest >= 2
    weeks = {d - timedelta(days=d.weekday()) for d in days}
    expected_weeks = 0
    ref = API_END - timedelta(days=API_END.weekday())
    if ref not in weeks:
        ref -= timedelta(days=7)
    while ref in weeks:
        expected_weeks += 1
        ref -= timedelta(days=7)
    assert body["active_weeks_in_row"] == expected_weeks >= 4


def test_weeks_in_row() -> None:
    mon = date(2026, 6, 1)
    assert weeks_in_row([], mon) == 0
    # Activity in the two previous weeks, none yet in the current one: the run still counts.
    previous = [mon - timedelta(days=3), mon - timedelta(days=10)]
    assert weeks_in_row(previous, mon + timedelta(days=2)) == 2
    # A gap week ends the run.
    assert weeks_in_row([mon, mon - timedelta(days=14)], mon + timedelta(days=6)) == 1


def test_calendar_empty_range(client: TestClient) -> None:
    body = client.get("/api/calendar?start=2020-01-01&end=2020-01-31").json()
    assert body["days"] == []
    assert body["totals"] == {"active_days": 0, "activities": 0}
    assert body["streak"] == {"current": 0, "longest": 0, "longest_start": None}
    assert body["active_weeks_in_row"] == 0


def test_punchcard_totals(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/calendar/punchcard")
    assert resp.status_code == 200
    cells = resp.json()
    bounds = default_bounds()
    total = scalar(sql, f"SELECT count(*) FROM garmin.activity WHERE {IN_RANGE}", **bounds)
    assert sum(c["activities"] for c in cells) == total
    assert all(0 <= c["weekday"] <= 6 and 0 <= c["hour"] <= 23 for c in cells)
    top = max(cells, key=lambda c: c["activities"])
    db = sql.execute(
        text(
            "SELECT count(*) AS n, coalesce(sum(duration_s), 0) AS dur FROM garmin.activity "
            f"WHERE {IN_RANGE} AND extract(isodow FROM start_time_local) = :wd "
            "AND extract(hour FROM start_time_local) = :h"
        ),
        {**bounds, "wd": top["weekday"] + 1, "h": top["hour"]},
    ).one()
    assert top["activities"] == db.n
    assert top["duration_s"] == pytest.approx(db.dur)


def test_punchcard_sport_filter(client: TestClient, sql: Session) -> None:
    cells = client.get("/api/calendar/punchcard?sport=run").json()
    runs = scalar(
        sql,
        f"SELECT count(*) FROM garmin.activity WHERE {IN_RANGE} AND sport_group = 'run'",
        **default_bounds(),
    )
    assert sum(c["activities"] for c in cells) == runs > 0
    assert client.get("/api/calendar/punchcard?sport=quidditch").status_code == 422
