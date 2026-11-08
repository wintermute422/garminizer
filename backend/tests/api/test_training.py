"""S4: /api/training endpoints, cross-checked against the base tables of the demo DB."""

from __future__ import annotations

import math
from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END

# Monday 2026-03-02 .. Sunday 2026-06-28: whole ISO weeks inside the demo data.
WEEK_START, WEEK_END = date(2026, 3, 2), date(2026, 6, 28)
WEEKS = {"start": WEEK_START.isoformat(), "end": WEEK_END.isoformat()}
MONTHS = {"start": "2026-02-01", "end": API_END.isoformat()}


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def scalar(s: Session, query: str, **params: Any) -> Any:
    return s.execute(text(query), params).scalar()


def activity_sum(s: Session, column: str, start: date, end: date, sport: str | None = None) -> Any:
    where = "start_time_local >= :start AND start_time_local < :end"
    if sport:
        where += " AND sport_group = :sport"
    return scalar(
        s,
        f"SELECT coalesce(sum({column}), 0) FROM garmin.activity WHERE {where}",
        start=start,
        end=end + timedelta(days=1),
        sport=sport,
    )


def test_load_matches_daily_load_and_pmc_recurrence(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/training/load")
    assert resp.status_code == 200
    body = resp.json()
    default_start = API_END - timedelta(days=364)
    n = scalar(
        sql,
        "SELECT count(*) FROM garmin.daily_load WHERE day BETWEEN :a AND :b",
        a=default_start,
        b=API_END,
    )
    assert n > 100
    assert len(body) == n
    assert set(body[0]) == {
        "day",
        "load",
        "trimp",
        "activities",
        "ctl",
        "atl",
        "tsb",
        "acwr",
        "monotony",
        "strain",
    }
    days = [date.fromisoformat(p["day"]) for p in body]
    assert days == sorted(set(days))
    assert days[-1] == API_END
    last_ctl = scalar(sql, "SELECT ctl FROM garmin.daily_load WHERE day = :d", d=API_END)
    assert body[-1]["ctl"] == pytest.approx(last_ctl)
    total = scalar(
        sql,
        "SELECT sum(load) FROM garmin.daily_load WHERE day BETWEEN :a AND :b",
        a=default_start,
        b=API_END,
    )
    assert sum(p["load"] for p in body) == pytest.approx(total, rel=1e-4)
    # CTL/ATL are 42/7-day EWMAs of the daily load, TSB is yesterday's CTL - ATL.
    k_ctl, k_atl = 1 - math.exp(-1 / 42), 1 - math.exp(-1 / 7)
    for i in range(1, len(body)):
        prev, cur = body[i - 1], body[i]
        assert cur["ctl"] == pytest.approx(
            prev["ctl"] + (cur["load"] - prev["ctl"]) * k_ctl, abs=0.05
        )
        assert cur["atl"] == pytest.approx(
            prev["atl"] + (cur["load"] - prev["atl"]) * k_atl, abs=0.05
        )
        assert cur["tsb"] == pytest.approx(prev["ctl"] - prev["atl"], abs=0.05)


def test_load_respects_range(client: TestClient) -> None:
    body = client.get("/api/training/load", params=WEEKS).json()
    assert len(body) == (WEEK_END - WEEK_START).days + 1
    assert body[0]["day"] == WEEK_START.isoformat()
    assert body[-1]["day"] == WEEK_END.isoformat()


def test_status_rows(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/training/status", params=MONTHS)
    assert resp.status_code == 200
    body = resp.json()
    n = scalar(
        sql,
        "SELECT count(*) FROM garmin.training_status WHERE day BETWEEN :a AND :b",
        a=date(2026, 2, 1),
        b=API_END,
    )
    assert n > 0
    assert len(body) == n
    assert {"day", "status", "acute_load", "chronic_load", "acwr", "load_anaerobic"} <= set(body[0])
    assert len(body[0]) == 18
    last = body[-1]
    status = scalar(
        sql,
        "SELECT status FROM garmin.training_status WHERE day = :d",
        d=date.fromisoformat(last["day"]),
    )
    assert last["status"] == status


@pytest.mark.parametrize(("period", "params"), [("week", WEEKS), ("month", MONTHS)])
def test_volume_totals_match_activities(
    client: TestClient, sql: Session, period: str, params: dict[str, str]
) -> None:
    resp = client.get("/api/training/volume", params={**params, "period": period})
    assert resp.status_code == 200
    body = resp.json()
    assert body
    start, end = date.fromisoformat(params["start"]), date.fromisoformat(params["end"])
    for p in body:
        d = date.fromisoformat(p["period_start"])
        assert start <= d <= end
        assert (d.weekday() == 0) if period == "week" else (d.day == 1)
    assert sum(p["activities"] for p in body) == scalar(
        sql,
        "SELECT count(*) FROM garmin.activity "
        "WHERE start_time_local >= :a AND start_time_local < :b",
        a=start,
        b=end + timedelta(days=1),
    )
    for column in ("distance_m", "duration_s", "elevation_gain_m"):
        got = sum(p[column] or 0 for p in body)
        assert got == pytest.approx(activity_sum(sql, column, start, end), rel=1e-4), column


def test_volume_sport_filter_and_partial_first_week(client: TestClient, sql: Session) -> None:
    body = client.get("/api/training/volume", params={**WEEKS, "sport": "run"}).json()
    assert body
    assert {p["sport_group"] for p in body} == {"run"}
    run_distance = activity_sum(sql, "distance_m", WEEK_START, WEEK_END, "run")
    assert sum(p["distance_m"] or 0 for p in body) == pytest.approx(run_distance, rel=1e-4)
    # A range starting on a Wednesday still returns that whole week.
    mid = client.get(
        "/api/training/volume", params={"start": "2026-03-04", "end": WEEKS["end"]}
    ).json()
    assert mid[0]["period_start"] == WEEK_START.isoformat()


def test_intensity_sums_hr_zones(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/training/intensity", params=WEEKS)
    assert resp.status_code == 200
    body = resp.json()
    assert body
    for p in body:
        assert date.fromisoformat(p["period_start"]).weekday() == 0
        zones = sum(p[f"zone_{z}_s"] for z in range(1, 6))
        assert p["total_s"] == pytest.approx(zones)
    expected = scalar(
        sql,
        """
        SELECT sum(z.seconds) FROM garmin.activity_zone z JOIN garmin.activity a USING (activity_id)
        WHERE z.kind = 'hr' AND z.zone BETWEEN 1 AND 5
          AND a.start_time_local >= :a AND a.start_time_local < :b
        """,
        a=WEEK_START,
        b=WEEK_END + timedelta(days=1),
    )
    assert expected > 0
    assert sum(p["total_s"] for p in body) == pytest.approx(expected, rel=1e-6)
    monthly = client.get(
        "/api/training/intensity", params={**MONTHS, "period": "month", "sport": "ride"}
    ).json()
    assert all(date.fromisoformat(p["period_start"]).day == 1 for p in monthly)
    ride_z2 = scalar(
        sql,
        """
        SELECT coalesce(sum(z.seconds), 0) FROM garmin.activity_zone z
        JOIN garmin.activity a USING (activity_id)
        WHERE z.kind = 'hr' AND z.zone = 2 AND a.sport_group = 'ride'
        """,
    )
    assert sum(p["zone_2_s"] for p in monthly) == pytest.approx(ride_z2, rel=1e-6)


def test_effects_activities_and_labels(client: TestClient, sql: Session) -> None:
    resp = client.get("/api/training/effects", params=MONTHS)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"activities", "labels"}
    window = {"a": date(2026, 2, 1), "b": API_END + timedelta(days=1)}
    in_range = "start_time_local >= :a AND start_time_local < :b"
    n = scalar(
        sql,
        f"SELECT count(*) FROM garmin.activity WHERE {in_range} "
        "AND (aerobic_te IS NOT NULL OR anaerobic_te IS NOT NULL)",
        **window,
    )
    assert n > 0
    assert len(body["activities"]) == n
    first = body["activities"][0]
    assert set(first) == {
        "activity_id",
        "day",
        "name",
        "sport_group",
        "aerobic_te",
        "anaerobic_te",
        "training_effect_label",
        "training_load",
    }
    te = scalar(
        sql, "SELECT aerobic_te FROM garmin.activity WHERE activity_id = :i", i=first["activity_id"]
    )
    assert first["aerobic_te"] == pytest.approx(te)
    expected = {
        r[0]: r[1]
        for r in sql.execute(
            text(
                f"SELECT training_effect_label, count(*) FROM garmin.activity WHERE {in_range} "
                "AND (aerobic_te IS NOT NULL OR anaerobic_te IS NOT NULL) "
                "AND training_effect_label IS NOT NULL GROUP BY 1"
            ),
            window,
        )
    }
    assert expected
    assert {lab["label"]: lab["activities"] for lab in body["labels"]} == expected
    counts = [lab["activities"] for lab in body["labels"]]
    assert counts == sorted(counts, reverse=True)
    runs = client.get("/api/training/effects", params={**MONTHS, "sport": "run"}).json()
    assert runs["activities"]
    assert {a["sport_group"] for a in runs["activities"]} == {"run"}
