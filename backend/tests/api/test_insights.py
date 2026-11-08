"""/api/insights: metrics, correlations, scatter, weekday averages and cards."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from tests.api.conftest import API_END

V_DAILY_KEYS = {
    "steps",
    "resting_hr",
    "avg_stress",
    "body_battery_high",
    "body_battery_at_wake",
    "sleep_s",
    "sleep_deep_s",
    "sleep_rem_s",
    "sleep_score",
    "hrv_ms",
    "readiness",
    "load",
    "ctl",
    "atl",
    "tsb",
    "vo2max_running",
    "weight_kg",
    "active_kcal",
    "vigorous_intensity_min",
    "intake_kcal",
    "protein_g",
    "energy_balance_kcal",
}


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in s.execute(text(query), params)]


def test_metrics_are_v_daily_columns(client: TestClient, sql: Session) -> None:
    metrics = client.get("/api/insights/metrics").json()
    keys = [m["key"] for m in metrics]
    assert set(keys) == V_DAILY_KEYS
    assert len(keys) == len(set(keys))
    assert all(set(m) == {"key", "label", "unit", "higher_is_better"} for m in metrics)
    by_key = {m["key"]: m for m in metrics}
    assert by_key["resting_hr"]["higher_is_better"] is False
    assert by_key["hrv_ms"]["higher_is_better"] is True
    assert by_key["load"]["higher_is_better"] is None
    sql.execute(text(f"SELECT {', '.join(keys)} FROM garmin.v_daily LIMIT 1"))


def test_correlation_matrix_without_lag(client: TestClient, sql: Session) -> None:
    body = client.get("/api/insights/correlations").json()
    keys, r, n = body["metrics"], body["r"], body["n"]
    size = len(keys)
    assert body["lag"] == 0
    assert len(r) == len(n) == size == len(V_DAILY_KEYS)
    assert all(len(row) == size for row in r)
    for i in range(size):
        assert r[i][i] is not None, keys[i]
        assert r[i][i] == pytest.approx(1.0)
        for j in range(size):
            assert r[i][j] == r[j][i]
            assert n[i][j] == n[j][i]
            if r[i][j] is not None:
                assert -1.0 <= r[i][j] <= 1.0
    counts = _rows(
        sql,
        f"SELECT {', '.join(f'count({k}) AS {k}' for k in keys)} FROM garmin.v_daily",
    )[0]
    assert [n[i][i] for i in range(size)] == [counts[k] for k in keys]


def test_correlation_matrix_leaves_out_sparse_metrics(client: TestClient) -> None:
    last = client.get("/api/meta").json()["last_day"]
    start = (date.fromisoformat(last) - timedelta(days=9)).isoformat()
    body = client.get("/api/insights/correlations", params={"start": start, "end": last}).json()
    assert body["metrics"] == []  # 10 days < MIN_PAIRS for every metric
    assert body["r"] == body["n"] == []


def test_correlation_with_lag_matches_numpy(client: TestClient, sql: Session) -> None:
    body = client.get("/api/insights/correlations", params={"lag": 1}).json()
    keys = body["metrics"]
    i, j = keys.index("load"), keys.index("hrv_ms")
    pairs = _rows(
        sql,
        "SELECT a.load AS x, b.hrv_ms AS y FROM garmin.v_daily a "
        "JOIN garmin.v_daily b ON b.day = a.day + 1 "
        "WHERE a.load IS NOT NULL AND b.hrv_ms IS NOT NULL",
    )
    x = np.array([p["x"] for p in pairs], dtype=float)
    y = np.array([p["y"] for p in pairs], dtype=float)
    assert body["n"][i][j] == len(pairs)
    assert body["r"][i][j] == pytest.approx(float(np.corrcoef(x, y)[0, 1]), abs=1e-9)
    assert client.get("/api/insights/correlations", params={"lag": 8}).status_code == 422


def test_scatter_matches_numpy(client: TestClient) -> None:
    body = client.get("/api/insights/scatter").json()
    assert (body["x"], body["y"], body["lag"]) == ("sleep_score", "readiness", 0)
    pts = body["points"]
    assert body["n"] == len(pts) > 14
    x = np.array([p["x"] for p in pts])
    y = np.array([p["y"] for p in pts])
    assert body["r"] == pytest.approx(float(np.corrcoef(x, y)[0, 1]), abs=1e-9)
    slope, intercept = np.polyfit(x, y, 1)
    assert body["slope"] == pytest.approx(float(slope))
    assert body["intercept"] == pytest.approx(float(intercept))


def test_scatter_lag_pairs_the_next_day(client: TestClient, sql: Session) -> None:
    body = client.get("/api/insights/scatter", params={"x": "load", "y": "hrv_ms", "lag": 1}).json()
    pts = body["points"]
    assert pts
    db = {
        r["day"]: r for r in _rows(sql, "SELECT day, load, hrv_ms FROM garmin.v_daily ORDER BY day")
    }
    for p in pts[:20]:
        d = date.fromisoformat(p["day"])
        assert p["x"] == pytest.approx(db[d]["load"], abs=1e-3)
        assert p["y"] == pytest.approx(db[d + timedelta(days=1)]["hrv_ms"], abs=1e-3)
    assert date.fromisoformat(pts[-1]["day"]) < API_END


@pytest.mark.parametrize("params", [{"x": "bogus"}, {"y": "day"}, {"x": "hrv_status"}])
def test_scatter_rejects_unknown_metrics(client: TestClient, params: dict[str, str]) -> None:
    assert client.get("/api/insights/scatter", params=params).status_code == 422


def test_weekday_averages(client: TestClient, sql: Session) -> None:
    body = client.get("/api/insights/weekday").json()
    assert [w["weekday"] for w in body] == list(range(7))
    expected = _rows(
        sql,
        "SELECT extract(isodow FROM day)::int - 1 AS wd, avg(steps)::float8 AS steps, "
        "avg(sleep_s)::float8 AS sleep_s FROM garmin.v_daily GROUP BY 1",
    )
    for e in expected:
        assert body[e["wd"]]["steps"] == pytest.approx(e["steps"])
        assert body[e["wd"]]["sleep_s"] == pytest.approx(e["sleep_s"])


def test_cards(client: TestClient, sql: Session) -> None:
    cards = client.get("/api/insights/cards").json()
    kinds = {c["id"] for c in cards}
    assert len(kinds) == len(cards) >= 5
    for c in cards:
        assert c["trend"] in {"up", "down", "flat"}
        assert c["sentiment"] in {"good", "bad", "neutral"}
        assert c["title"]
        assert c["text"].endswith(".")
        assert "nan" not in c["text"].lower()
    by_id = {c["id"]: c for c in cards}
    assert {"resting_hr_change", "consistency", "streak", "fitness_change"} <= kinds

    rhr_now = _rows(
        sql,
        "SELECT avg(resting_hr)::float8 AS v FROM garmin.daily_summary WHERE day > :d",
        d=API_END - timedelta(days=30),
    )[0]["v"]
    rhr_before = _rows(
        sql,
        "SELECT avg(resting_hr)::float8 AS v FROM garmin.daily_summary WHERE day BETWEEN :a AND :b",
        a=API_END - timedelta(days=89),
        b=API_END - timedelta(days=30),
    )[0]["v"]
    rhr = by_id["resting_hr_change"]
    assert rhr["value"] == pytest.approx(rhr_now, abs=0.05)
    assert rhr["delta"] == pytest.approx(rhr_now - rhr_before, abs=0.1)
    assert "bpm" in rhr["text"]

    weeks = _rows(
        sql,
        "SELECT count(DISTINCT date_trunc('week', start_time_local)) AS active, "
        "(date_trunc('week', max(start_time_local))::date "
        " - date_trunc('week', min(start_time_local))::date) / 7 + 1 AS total "
        "FROM garmin.activity",
    )[0]
    assert by_id["consistency"]["value"] == pytest.approx(
        weeks["active"] / weeks["total"] * 100, abs=0.05
    )


def test_cards_with_short_range(client: TestClient) -> None:
    resp = client.get(
        "/api/insights/cards", params={"start": API_END.isoformat(), "end": API_END.isoformat()}
    )
    assert resp.status_code == 200
    kinds = {c["id"] for c in resp.json()}
    assert "consistency" not in kinds  # needs at least 4 weeks
    assert "resting_hr_change" in kinds  # always looks back 90 days from the end
