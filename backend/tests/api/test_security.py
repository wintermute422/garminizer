"""A7 (security part): password mode, CSRF header, refusal to expose without a password."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from garminizer.api.app import create_app
from garminizer.config import ConfigError, Settings
from tests.api.conftest import CSRF


def test_local_mode_needs_no_login(client: TestClient) -> None:
    assert client.get("/api/auth/status").json() == {"required": False, "authenticated": True}
    assert client.get("/api/meta").status_code == 200


def test_off_loopback_without_password_refuses_to_start() -> None:
    settings = Settings(app_host="0.0.0.0", _env_file=None)
    with pytest.raises(ConfigError, match="APP_PASSWORD"):
        create_app(settings, web_dist=None)


def test_password_mode_flow(locked_client: TestClient) -> None:
    c = locked_client
    c.cookies.clear()
    assert c.get("/api/health").status_code == 200  # public
    assert c.get("/api/meta").status_code == 401
    assert c.post("/api/auth/login", json={"password": "x"}).status_code == 403  # no CSRF header
    assert c.post("/api/auth/login", json={"password": "wrong"}, headers=CSRF).status_code == 401
    ok = c.post("/api/auth/login", json={"password": "demo-password"}, headers=CSRF)
    assert ok.status_code == 200
    assert "garminizer_session" in ok.headers.get("set-cookie", "")
    assert "httponly" in ok.headers["set-cookie"].lower()
    assert "samesite=strict" in ok.headers["set-cookie"].lower()
    assert c.get("/api/meta").status_code == 200
    c.post("/api/auth/logout", headers=CSRF)
    c.cookies.clear()
    assert c.get("/api/meta").status_code == 401


def test_login_is_rate_limited(locked_client: TestClient) -> None:
    codes = [
        locked_client.post("/api/auth/login", json={"password": "nope"}, headers=CSRF).status_code
        for _ in range(8)
    ]
    assert 429 in codes


def test_forged_cookie_is_rejected(locked_client: TestClient) -> None:
    locked_client.cookies.clear()
    locked_client.cookies.set("garminizer_session", "abc.def.ghi")
    assert locked_client.get("/api/meta").status_code == 401
    locked_client.cookies.clear()
