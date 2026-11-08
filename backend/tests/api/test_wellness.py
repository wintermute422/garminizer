"""S4 wellness endpoints: daily list, intraday day view, hourly heatmap, readiness."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, q: str, **params: Any) -> Any:
    return s.execute(text(q), params).scalar_one()


def tz_of(s: Session) -> str:
    return str(scalar(s, "SELECT time_zone FROM garmin.athlete"))


def ts(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_daily_joins_hrv_and_readiness(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/wellness/daily")
    assert resp.status_code == 200
    days = resp.json()
    start = API_END - timedelta(days=364)
    expected = scalar(
        sql,
        "SELECT count(*) FROM garmin.daily_summary WHERE day BETWEEN :a AND :b",
        a=start,
        b=API_END,
    )
    assert len(days) == expected > 100
    assert [d["day"] for d in days] == sorted(d["day"] for d in days)
    row = next(d for d in days if d["day"] == "2026-05-10")
    db = sql.execute(
        text(
            "SELECT d.steps, d.resting_hr, h.last_night_avg_ms, h.status, r.score, r.level "
            "FROM garmin.daily_summary d LEFT JOIN garmin.hrv_daily h USING (day) "
            "LEFT JOIN garmin.training_readiness r USING (day) WHERE day = '2026-05-10'"
        )
    ).one()
    assert row["steps"] == db.steps
    assert row["resting_hr"] == db.resting_hr
    assert row["hrv_last_night_avg_ms"] == pytest.approx(db.last_night_avg_ms)
    assert row["hrv_status"] == db.status
    assert row["readiness_score"] == db.score
    assert row["readiness_level"] == db.level
    for key in ("total_kcal", "body_battery_high", "sleeping_s", "hrv_baseline_balanced_low_ms"):
        assert key in row


def test_daily_respects_range(client: TestClient) -> None:
    days = client.get("/api/wellness/daily?start=2026-06-01&end=2026-06-07").json()
    assert [d["day"] for d in days] == [f"2026-06-0{i}" for i in range(1, 8)]


def test_intraday_default_day_is_a_full_local_day(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/wellness/intraday")
    assert resp.status_code == 200
    body = resp.json()
    tz = tz_of(sql)
    assert body["day"] == API_END.isoformat()
    assert body["time_zone"] == tz
    t0 = scalar(sql, "SELECT CAST(:d AS timestamp) AT TIME ZONE :tz", d=API_END, tz=tz)
    t1 = t0 + timedelta(days=1)
    hr = body["hr"]
    assert 690 <= len(hr) <= 750
    n_db = scalar(
        sql, "SELECT count(*) FROM garmin.hr_sample WHERE ts >= :a AND ts < :b", a=t0, b=t1
    )
    assert len(hr) == n_db
    stamps = [ts(p["ts"]) for p in hr]
    assert all(s.utcoffset() == timedelta(0) for s in stamps)
    assert t0 <= stamps[0] and stamps[-1] < t1
    first_bpm = scalar(
        sql, "SELECT bpm FROM garmin.hr_sample WHERE ts >= :a ORDER BY ts LIMIT 1", a=t0
    )
    assert hr[0]["value"] == first_bpm
    assert all(p["value"] is None or p["value"] >= 0 for p in body["stress"])
    assert body["body_battery"] and body["respiration"] and body["spo2"]
    steps_db = scalar(
        sql,
        "SELECT sum(steps) FROM garmin.steps_interval WHERE start_utc >= :a AND start_utc < :b",
        a=t0,
        b=t1,
    )
    assert sum(s["steps"] for s in body["steps"]) == steps_db
    sleep = sql.execute(
        text("SELECT start_utc, end_utc FROM garmin.sleep WHERE day = :d"), {"d": API_END}
    ).one()
    assert ts(body["sleep"]["start"]) == sleep.start_utc
    assert ts(body["sleep"]["end"]) == sleep.end_utc


def test_intraday_marks_negative_stress_as_null(client: TestClient, sql: Session) -> None:
    day = scalar(
        sql,
        "SELECT (ts AT TIME ZONE (SELECT time_zone FROM garmin.athlete))::date "
        "FROM garmin.stress_sample WHERE level < 0 ORDER BY ts DESC LIMIT 1",
    )
    body = client.get(f"/api/wellness/intraday?day={day}").json()
    assert any(p["value"] is None for p in body["stress"])
    assert all(p["value"] is None or p["value"] >= 0 for p in body["stress"])


def test_intraday_lists_activities_of_the_day(client: TestClient, sql: Session) -> None:
    row = sql.execute(
        text(
            "SELECT activity_id, start_time_local::date AS day FROM garmin.activity "
            "WHERE start_time_local::date < :end ORDER BY start_time_utc DESC LIMIT 1"
        ),
        {"end": API_END},
    ).one()
    body = client.get(f"/api/wellness/intraday?day={row.day}").json()
    ids = [a["activity_id"] for a in body["activities"]]
    assert row.activity_id in ids
    act = next(a for a in body["activities"] if a["activity_id"] == row.activity_id)
    assert ts(act["end"]) > ts(act["start"])


def test_intraday_dst_day_has_23_hours(client: TestClient, sql: Session) -> None:
    body = client.get("/api/wellness/intraday?day=2026-03-29").json()
    tz = tz_of(sql)
    t0 = scalar(sql, "SELECT CAST('2026-03-29' AS timestamp) AT TIME ZONE :tz", tz=tz)
    t1 = scalar(sql, "SELECT CAST('2026-03-30' AS timestamp) AT TIME ZONE :tz", tz=tz)
    assert t1 - t0 == timedelta(hours=23)
    n_db = scalar(
        sql, "SELECT count(*) FROM garmin.hr_sample WHERE ts >= :a AND ts < :b", a=t0, b=t1
    )
    assert len(body["hr"]) == n_db == 690


def test_intraday_without_data_is_empty(client: TestClient) -> None:
    body = client.get("/api/wellness/intraday?day=2020-01-01").json()
    assert body["hr"] == [] and body["steps"] == [] and body["sleep"] is None


def test_heatmap_hr_cell_matches_sql_mean(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/wellness/heatmap")
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "hr"
    assert body["hours"] == list(range(24))
    assert len(body["values"]) == len(body["days"]) >= 140
    assert all(len(v) == 24 for v in body["values"])
    assert body["days"][-1] == API_END.isoformat()
    first_db = scalar(sql, "SELECT min(day) FROM garmin.daily_summary")
    assert body["days"][0] == first_db.isoformat()
    i = body["days"].index("2026-06-15")
    expected = scalar(
        sql,
        "SELECT avg(bpm)::float8 FROM garmin.hr_sample "
        "WHERE (ts AT TIME ZONE :tz) >= '2026-06-15 14:00' "
        "AND (ts AT TIME ZONE :tz) < '2026-06-15 15:00'",
        tz=tz_of(sql),
    )
    assert body["values"][i][14] == pytest.approx(expected, abs=0.05)


def test_heatmap_steps_sum_and_stress_without_negatives(client: TestClient, sql: Session) -> None:
    tz = tz_of(sql)
    steps = client.get("/api/wellness/heatmap?metric=steps&start=2026-06-01&end=2026-06-30").json()
    assert steps["days"][0] == "2026-06-01" and len(steps["days"]) == 30
    expected_steps = scalar(
        sql,
        "SELECT sum(steps)::float8 FROM garmin.steps_interval "
        "WHERE (start_utc AT TIME ZONE :tz) >= '2026-06-10 08:00' "
        "AND (start_utc AT TIME ZONE :tz) < '2026-06-10 09:00'",
        tz=tz,
    )
    assert steps["values"][9][8] == pytest.approx(expected_steps)
    stress = client.get(
        "/api/wellness/heatmap?metric=stress&start=2026-06-01&end=2026-06-30"
    ).json()
    expected_stress = scalar(
        sql,
        "SELECT avg(level)::float8 FROM garmin.stress_sample WHERE level >= 0 "
        "AND (ts AT TIME ZONE :tz) >= '2026-06-10 10:00' "
        "AND (ts AT TIME ZONE :tz) < '2026-06-10 11:00'",
        tz=tz,
    )
    assert stress["values"][9][10] == pytest.approx(expected_stress, abs=0.05)
    flat = [v for day in stress["values"] for v in day if v is not None]
    assert min(flat) >= 0


@pytest.mark.parametrize("metric", ["body_battery", "respiration"])
def test_heatmap_other_metrics(client: TestClient, metric: str) -> None:
    body = client.get(f"/api/wellness/heatmap?metric={metric}").json()
    assert body["metric"] == metric
    assert any(v is not None for v in body["values"][-1])


def test_heatmap_rejects_unknown_metric(client: TestClient) -> None:
    assert client.get("/api/wellness/heatmap?metric=mood").status_code == 422


def test_readiness_rows(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/wellness/readiness?start=2026-06-01&end=2026-06-30")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == scalar(
        sql,
        "SELECT count(*) FROM garmin.training_readiness "
        "WHERE day BETWEEN '2026-06-01' AND '2026-06-30'",
    )
    row = data[0]
    assert row["day"] == "2026-06-01"
    assert row["score"] == scalar(
        sql, "SELECT score FROM garmin.training_readiness WHERE day = '2026-06-01'"
    )
    assert {"level", "hrv_factor", "recovery_time_min", "feedback"} <= set(row)


def test_intraday_window_is_utc(client: TestClient, sql: Session) -> None:
    body = client.get("/api/wellness/intraday?day=2026-06-20").json()
    first = ts(body["hr"][0]["ts"])
    # Europe/Berlin is UTC+2 in June: local midnight is 22:00 UTC the day before.
    assert tz_of(sql) == "Europe/Berlin"
    assert first >= datetime(2026, 6, 19, 22, 0, tzinfo=UTC)
    assert first < datetime(2026, 6, 19, 22, 2, tzinfo=UTC)
    assert date.fromisoformat(body["day"]) == date(2026, 6, 20)
