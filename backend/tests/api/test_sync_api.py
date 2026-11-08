"""Sync API: status/coverage on the demo DB, demo refusal, connect + MFA + run on a real DB."""

from __future__ import annotations

import time
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from garminizer.api.app import create_app
from garminizer.config import Settings
from garminizer.db import migrate
from tests.api.conftest import CSRF
from tests.conftest import create_fresh_database
from tests.garmin_fake import FAKE_EMAIL, FAKE_PASSWORD, MFA_CODE, factory_for


def _app_client(url: str, data_dir: Path, **state: Any) -> Generator[TestClient, None, None]:
    settings = Settings(
        database_url=url,
        app_host="127.0.0.1",
        data_dir=data_dir,
        sync_request_delay_s=0,
        _env_file=None,
    )
    app = create_app(settings, web_dist=None)
    for key, value in state.items():
        setattr(app.state, key, value)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def demo_client(api_db_url: str, tmp_path: Path) -> Iterator[TestClient]:
    yield from _app_client(api_db_url, tmp_path / "data", garmin_factory=factory_for())


@pytest.fixture(scope="module")
def real_db_url() -> str:
    url = create_fresh_database("_syncapi")
    migrate.upgrade(url)
    return url


@pytest.fixture
def real_client(real_db_url: str, tmp_path: Path) -> Iterator[TestClient]:
    yield from _app_client(real_db_url, tmp_path / "data", garmin_factory=factory_for())


def test_status_on_the_demo_db(demo_client: TestClient) -> None:
    resp = demo_client.get("/api/sync/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_demo"] is True
    assert body["connected"] is False
    assert body["running"] is False
    assert body["mfa_pending"] is False
    assert isinstance(body["last_runs"], list) and len(body["last_runs"]) <= 10
    assert isinstance(body["cursors"], list)
    assert isinstance(body["recent_errors"], list)
    assert body["first_day"] is not None and body["last_day"] is not None


def test_coverage_on_the_demo_db(demo_client: TestClient) -> None:
    resp = demo_client.get("/api/sync/coverage")
    assert resp.status_code == 200
    body = resp.json()
    assert "sleep" in body["datasets"] and "user_summary" in body["datasets"]
    assert body["months"] == []


def test_demo_db_refuses_connect_and_run(demo_client: TestClient) -> None:
    resp = demo_client.post(
        "/api/sync/connect", json={"email": FAKE_EMAIL, "password": FAKE_PASSWORD}, headers=CSRF
    )
    assert resp.status_code == 409
    assert "demo" in resp.json()["detail"]
    assert (
        demo_client.post("/api/sync/run", json={"kind": "incremental"}, headers=CSRF).status_code
        == 409
    )
    assert (
        demo_client.post("/api/sync/mfa", json={"code": MFA_CODE}, headers=CSRF).status_code == 409
    )


def test_posts_need_the_csrf_header(demo_client: TestClient) -> None:
    assert demo_client.post("/api/sync/run", json={"kind": "incremental"}).status_code == 403
    assert demo_client.post("/api/sync/disconnect").status_code == 403


def test_run_refuses_when_not_connected(real_client: TestClient) -> None:
    assert real_client.get("/api/sync/status").json()["connected"] is False
    resp = real_client.post("/api/sync/run", json={"kind": "incremental"}, headers=CSRF)
    assert resp.status_code == 409
    assert resp.json()["detail"] == "not connected to Garmin"


def test_connect_rejects_bad_credentials(real_client: TestClient) -> None:
    resp = real_client.post(
        "/api/sync/connect", json={"email": FAKE_EMAIL, "password": "nope"}, headers=CSRF
    )
    assert resp.status_code == 400
    assert "nope" not in resp.text
    assert real_client.get("/api/sync/status").json()["connected"] is False


def test_connect_mfa_disconnect(real_db_url: str, tmp_path: Path) -> None:
    clients = _app_client(
        real_db_url, tmp_path / "data", garmin_factory=factory_for(mfa_required=True)
    )
    client = next(clients)
    try:
        assert (
            client.post("/api/sync/mfa", json={"code": MFA_CODE}, headers=CSRF).status_code == 409
        )
        resp = client.post(
            "/api/sync/connect", json={"email": FAKE_EMAIL, "password": FAKE_PASSWORD}, headers=CSRF
        )
        assert resp.json() == {"status": "needs_mfa"}
        assert client.get("/api/sync/status").json()["mfa_pending"] is True
        assert (
            client.post("/api/sync/mfa", json={"code": "000000"}, headers=CSRF).status_code == 400
        )
        resp = client.post("/api/sync/mfa", json={"code": MFA_CODE}, headers=CSRF)
        assert resp.json() == {"status": "ok"}
        status = client.get("/api/sync/status").json()
        assert (status["connected"], status["mfa_pending"]) == (True, False)
        assert not list((tmp_path / "data").rglob("*mfa*"))
        assert client.post("/api/sync/disconnect", headers=CSRF).json() == {"connected": False}
        assert client.get("/api/sync/status").json()["connected"] is False
    finally:
        clients.close()


def test_connect_and_run_an_incremental_sync(real_client: TestClient) -> None:
    resp = real_client.post(
        "/api/sync/connect", json={"email": FAKE_EMAIL, "password": FAKE_PASSWORD}, headers=CSRF
    )
    assert resp.json() == {"status": "ok"}
    resp = real_client.post("/api/sync/run", json={"kind": "incremental"}, headers=CSRF)
    assert resp.status_code == 202
    assert resp.json() == {"status": "started", "kind": "incremental"}
    deadline = time.monotonic() + 60
    status: dict[str, Any] = {}
    while time.monotonic() < deadline:
        status = real_client.get("/api/sync/status").json()
        runs = status["last_runs"]
        if not status["running"] and runs and runs[0]["status"] != "running":
            break
        time.sleep(0.2)
    assert status["last_runs"][0]["kind"] == "incremental"
    assert status["last_runs"][0]["status"] == "ok", status["last_runs"][0]
    assert status["last_runs"][0]["requests"] > 0
    assert {c["dataset"] for c in status["cursors"]} >= {"sleep", "activity", "user_summary"}
    coverage = real_client.get("/api/sync/coverage").json()
    assert any(
        row["dataset"] == "sleep" and row["days_with_data"] > 0 for row in coverage["months"]
    )
    meta = real_client.get("/api/meta").json()
    assert meta["athlete"]["is_demo"] is False
