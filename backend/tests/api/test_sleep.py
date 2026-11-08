"""S4 sleep endpoints: nightly list, one night in detail, range statistics."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END

RANGE = "start=2026-03-01&end=2026-06-30"


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


def test_nightly_list(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/sleep")
    assert resp.status_code == 200
    nights = resp.json()
    start = API_END - timedelta(days=364)
    assert len(nights) == scalar(
        sql, "SELECT count(*) FROM garmin.sleep WHERE day BETWEEN :a AND :b", a=start, b=API_END
    )
    assert nights[-1]["day"] == API_END.isoformat()
    for key in ("score", "deep_s", "sleep_need_min", "feedback", "hrv_status", "bed_local"):
        assert key in nights[0]
    hrv = scalar(sql, "SELECT status FROM garmin.hrv_daily WHERE day = :d", d=API_END)
    assert nights[-1]["hrv_status"] == hrv


def test_bed_and_wake_minutes_after_previous_noon(client: TestClient, sql: Session) -> None:
    night = next(n for n in client.get("/api/sleep").json() if n["day"] == "2026-06-15")
    tz = ZoneInfo(scalar(sql, "SELECT time_zone FROM garmin.athlete"))
    row = sql.execute(
        text("SELECT start_utc, end_utc FROM garmin.sleep WHERE day = '2026-06-15'")
    ).one()
    bed = row.start_utc.astimezone(tz).replace(tzinfo=None)
    wake = row.end_utc.astimezone(tz).replace(tzinfo=None)
    noon = datetime(2026, 6, 14, 12, 0)
    assert datetime.fromisoformat(night["bed_local"]) == bed
    assert datetime.fromisoformat(night["wake_local"]) == wake
    assert night["bedtime_min"] == pytest.approx((bed - noon).total_seconds() / 60)
    assert night["waketime_min"] == pytest.approx((wake - noon).total_seconds() / 60)
    # Plausible: in bed between 20:00 and 02:00, up between 04:00 and 11:00.
    assert 480 <= night["bedtime_min"] <= 840
    assert 960 <= night["waketime_min"] <= 1380
    assert ts(night["start_utc"]) == row.start_utc


def test_night_detail(client: TestClient, sql: Session) -> None:
    resp = client.get(f"/api/sleep/{API_END.isoformat()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["night"]["day"] == API_END.isoformat()
    n_stages = scalar(sql, "SELECT count(*) FROM garmin.sleep_stage WHERE day = :d", d=API_END)
    assert len(body["stages"]) == n_stages > 0
    assert {s["stage"] for s in body["stages"]} <= {"deep", "light", "rem", "awake"}
    start, end = ts(body["night"]["start_utc"]), ts(body["night"]["end_utc"])
    n_hr = scalar(
        sql,
        "SELECT count(*) FROM garmin.hr_sample s JOIN garmin.sleep n ON n.day = :d "
        "WHERE s.ts BETWEEN n.start_utc AND n.end_utc",
        d=API_END,
    )
    assert len(body["hr"]) == n_hr > 100
    for key in ("hr", "spo2", "respiration", "body_battery"):
        assert body[key], key
        assert all(start <= ts(p["ts"]) <= end for p in body[key])


def test_night_detail_404_without_sleep(client: TestClient) -> None:
    assert client.get("/api/sleep/2020-01-01").status_code == 404


def test_stats(client: TestClient, sql: Session) -> None:
    resp = client.get(f"/api/sleep/stats?{RANGE}")
    assert resp.status_code == 200
    st = resp.json()
    where = "day BETWEEN '2026-03-01' AND '2026-06-30'"
    db = sql.execute(
        text(
            "SELECT count(*) AS n, avg(duration_s)::float8 AS dur, avg(score)::float8 AS score, "
            "avg(deep_s)::float8 AS deep, "
            "count(*) FILTER (WHERE extract(isodow FROM day) IN (6, 7)) AS weekend "
            f"FROM garmin.sleep WHERE {where}"
        )
    ).one()
    assert st["nights"] == db.n == 122
    assert st["avg_duration_s"] == pytest.approx(db.dur, abs=0.06)
    assert st["avg_score"] == pytest.approx(db.score, abs=0.06)
    assert st["avg_deep_s"] == pytest.approx(db.deep, abs=0.06)
    assert st["weekend"]["nights"] == db.weekend
    assert st["weekday"]["nights"] + st["weekend"]["nights"] == db.n
    debt = scalar(
        sql,
        "SELECT sum(greatest(0, sleep_need_min * 60 - duration_s))::float8 FROM "
        f"(SELECT * FROM garmin.sleep WHERE {where} ORDER BY day DESC LIMIT 7) x",
    )
    assert st["sleep_debt_7d_s"] == pytest.approx(debt)
    dist: dict[str, int] = dict(
        sql.execute(
            text(f"SELECT score_quality, count(*) FROM garmin.sleep WHERE {where} GROUP BY 1")
        ).all()
    )
    assert {d["quality"]: d["nights"] for d in st["score_distribution"]} == dist
    sd = scalar(
        sql,
        "SELECT stddev_samp(extract(epoch FROM (start_utc AT TIME ZONE "
        "(SELECT time_zone FROM garmin.athlete)) - ((day - 1) + time '12:00')) / 60)::float8 "
        f"FROM garmin.sleep WHERE {where}",
    )
    assert st["bedtime_sd_min"] == pytest.approx(sd, abs=0.06)
    assert st["weekday"]["avg_bedtime_min"] is not None
    assert st["waketime_sd_min"] is not None


def test_stats_empty_range(client: TestClient) -> None:
    st = client.get("/api/sleep/stats?start=2020-01-01&end=2020-01-31").json()
    assert st["nights"] == 0
    assert st["avg_duration_s"] is None
    assert st["sleep_debt_7d_s"] is None
    assert st["score_distribution"] == []
