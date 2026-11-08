"""/api/gear: distances and usage come from the linked activities."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

ITEM_KEYS = {
    "uuid",
    "gear_type",
    "display_name",
    "make",
    "model",
    "status",
    "date_begin",
    "date_end",
    "max_distance_m",
    "distance_m",
    "activities",
    "last_used",
    "wear_pct",
    "usage",
}


@pytest.fixture(scope="module")
def sql(api_db_url: str) -> Iterator[Session]:
    engine = create_engine(api_db_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _rows(s: Session, query: str, **params: Any) -> list[dict[str, Any]]:
    return [dict(r._mapping) for r in s.execute(text(query), params)]


def test_gear_list_matches_linked_activities(client: TestClient, sql: Session) -> None:
    items = client.get("/api/gear").json()
    expected = {
        r["uuid"]: r
        for r in _rows(
            sql,
            """
            SELECT g.uuid, g.max_distance_m, count(a.activity_id) AS n,
                   coalesce(sum(a.distance_m), 0) AS dist,
                   max(a.start_time_local)::date AS last_used
            FROM garmin.gear g
            LEFT JOIN garmin.activity_gear ag ON ag.gear_uuid = g.uuid
            LEFT JOIN garmin.activity a ON a.activity_id = ag.activity_id
            GROUP BY g.uuid
            """,
        )
    }
    assert {i["uuid"] for i in items} == set(expected)
    assert any(i["activities"] > 0 for i in items)
    for item in items:
        assert set(item) == ITEM_KEYS
        e = expected[item["uuid"]]
        assert item["activities"] == e["n"]
        assert item["distance_m"] == pytest.approx(e["dist"], abs=0.1)
        assert item["last_used"] == (e["last_used"].isoformat() if e["last_used"] else None)
        assert sum(u["distance_m"] for u in item["usage"]) == pytest.approx(e["dist"], abs=1.0)
        months = [u["month"] for u in item["usage"]]
        assert months == sorted(months)
        assert all(m.endswith("-01") for m in months)
        if e["max_distance_m"]:
            assert item["wear_pct"] == pytest.approx(e["dist"] / e["max_distance_m"] * 100, abs=0.1)
        else:
            assert item["wear_pct"] is None
    statuses = [i["status"] for i in items]
    assert statuses == sorted(statuses, key=lambda s: s != "active")


def test_gear_detail(client: TestClient, sql: Session) -> None:
    body = client.get("/api/gear/demo-shoe-a").json()
    assert set(body) == {"item", "activities"}
    assert body["item"]["uuid"] == "demo-shoe-a"
    ids = {
        r["activity_id"]
        for r in _rows(
            sql,
            "SELECT activity_id FROM garmin.activity_gear WHERE gear_uuid = 'demo-shoe-a'",
        )
    }
    assert ids
    assert {a["activity_id"] for a in body["activities"]} == ids
    assert body["item"]["activities"] == len(body["activities"])
    starts = [a["start_time_utc"] for a in body["activities"]]
    assert starts == sorted(starts, reverse=True)
    assert body["item"]["distance_m"] == pytest.approx(
        sum(a["distance_m"] or 0 for a in body["activities"]), abs=0.1
    )


def test_unused_gear_and_unknown_gear(client: TestClient, sql: Session) -> None:
    unused = _rows(
        sql,
        "SELECT g.uuid FROM garmin.gear g WHERE NOT EXISTS "
        "(SELECT 1 FROM garmin.activity_gear ag WHERE ag.gear_uuid = g.uuid) ORDER BY 1 LIMIT 1",
    )
    assert unused, "the demo has gear without activities in its first 150 days"
    resp = client.get(f"/api/gear/{unused[0]['uuid']}")
    assert resp.status_code == 200
    assert resp.json()["activities"] == []
    assert resp.json()["item"]["distance_m"] == 0
    assert resp.json()["item"]["last_used"] is None
    assert client.get("/api/gear/no-such-gear").status_code == 404
