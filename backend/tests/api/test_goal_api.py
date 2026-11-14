"""/api/goal on the demo database (which has a demo weight goal), plus the write endpoints.

Write tests restore the seeded goal so the shared API database stays as it was.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.api.conftest import API_END, CSRF

DEMO_START = API_END - timedelta(days=41)


@pytest.fixture
def restore_goal(client: TestClient) -> Iterator[dict[str, Any]]:
    seeded = client.get("/api/goal").json()["settings"]
    yield seeded
    assert client.put("/api/goal/settings", json=seeded, headers=CSRF).status_code == 200


def test_view_has_the_demo_goal(client: TestClient) -> None:
    v = client.get("/api/goal").json()
    assert v["configured"] is True
    s = v["settings"]
    assert s["start_day"] == DEMO_START.isoformat() and s["rate_kg_per_week"] == 0.25
    assert v["target_daily_balance_kcal"] == round(-0.25 * 7700 / 7)
    days = v["days"]
    assert days[0]["day"] == DEMO_START.isoformat()
    with_trend = [d for d in days if d["trend_kg"] is not None]
    assert len(with_trend) >= 20  # demo weigh-ins on most days
    for d in with_trend:
        assert d["delta_kg"] == pytest.approx(d["trend_kg"] - d["target_kg"], abs=0.002)
    logged = [d for d in days if d["intake_kcal"] is not None and d["burn_kcal"] is not None]
    assert logged, "demo meals inside the goal period"
    for d in logged:
        assert d["balance_kcal"] == pytest.approx(d["intake_kcal"] - d["burn_kcal"], abs=1)
    trained = [d for d in days if d["activities"]]
    assert trained and all(
        a["active_kcal"] <= a["calories"] for d in trained for a in d["activities"]
    )
    assert v["anchors"][0] == {
        "day": DEMO_START.isoformat(),
        "weight_kg": s["start_weight_kg"],
        "kind": "start",
    }
    assert len(v["checkpoints"]) == 14
    assert v["body_fat"] and v["body_fat_regression"] is not None
    assert v["status"]["as_of"] == with_trend[-1]["day"]
    assert v["status"]["trend_kg"] == with_trend[-1]["trend_kg"]
    assert v["bmr_today"]["source"] == "formulas"


def test_balance_of_a_demo_day(client: TestClient) -> None:
    b = client.get("/api/goal/balance", params={"day": API_END.isoformat()}).json()
    assert b["goal_configured"] is True and b["is_today"] is False and b["as_of"] is None
    assert b["burn_kcal"] == pytest.approx(b["baseline_kcal"] + b["training_kcal"], abs=1)
    assert b["week"]["end"] == API_END.isoformat()
    assert client.get("/api/goal/balance", params={"day": "nope"}).status_code == 422


def test_settings_validation_and_checkpoints(
    client: TestClient, restore_goal: dict[str, Any]
) -> None:
    bad = {**restore_goal, "end_day": restore_goal["start_day"]}
    assert client.put("/api/goal/settings", json=bad, headers=CSRF).status_code == 422
    unknown = {**restore_goal, "colour": "blue"}
    assert client.put("/api/goal/settings", json=unknown, headers=CSRF).status_code == 422
    first = client.get("/api/goal").json()["checkpoints"][0]["day"]
    r = client.put(f"/api/goal/checkpoints/{first}", json={"accepted": True}, headers=CSRF)
    assert r.status_code == 200 and r.json()["accepted_checkpoints"] == [first]
    status = client.get("/api/goal").json()["checkpoints"][0]["status"]
    assert status in {"accepted", "reached"}  # reached wins over accepted
    monday = (DEMO_START + timedelta(days=7)).isoformat()
    r = client.put(f"/api/goal/checkpoints/{monday}", json={"accepted": True}, headers=CSRF)
    assert r.status_code == 422 and "not a checkpoint" in r.json()["detail"]


def test_writes_need_the_csrf_header(client: TestClient, restore_goal: dict[str, Any]) -> None:
    assert client.put("/api/goal/settings", json=restore_goal).status_code == 403


def test_delete_and_unconfigured_view(client: TestClient, restore_goal: dict[str, Any]) -> None:
    assert client.delete("/api/goal/settings", headers=CSRF).status_code == 204
    v = client.get("/api/goal").json()
    assert v["configured"] is False and v["days"] == [] and v["status"] is None
    assert client.delete("/api/goal/settings", headers=CSRF).status_code == 404
    b = client.get("/api/goal/balance").json()
    assert b["goal_configured"] is False and b["target_balance_kcal"] is None
