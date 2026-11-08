"""API test fixtures: one demo-seeded database for all API tests, plus clients."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.api.app import create_app
from garminizer.config import Settings
from garminizer.db import migrate
from garminizer.demo.seed import seed_demo
from tests.conftest import create_fresh_database

API_END = date(2026, 6, 30)
API_DAYS = 150
CSRF = {"X-Requested-With": "garminizer"}


@pytest.fixture(scope="session")
def api_db_url() -> str:
    url = create_fresh_database("_api")
    migrate.upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    with Session(engine) as s:
        seed_demo(s, end=API_END, days=API_DAYS, seed=21)
        s.commit()
    engine.dispose()
    return url


@pytest.fixture(scope="session")
def client(api_db_url: str) -> Iterator[TestClient]:
    """Unauthenticated local mode (no APP_PASSWORD, loopback)."""
    settings = Settings(database_url=api_db_url, app_host="127.0.0.1", _env_file=None)
    with TestClient(create_app(settings, web_dist=None)) as c:
        yield c


@pytest.fixture(scope="session")
def locked_client(api_db_url: str) -> Iterator[TestClient]:
    """LAN mode with a password (as when APP_HOST=0.0.0.0)."""
    settings = Settings(
        database_url=api_db_url,
        app_host="0.0.0.0",
        app_password="demo-password",
        _env_file=None,
    )
    with TestClient(create_app(settings, web_dist=None)) as c:
        yield c


@pytest.fixture(scope="session")
def some_activity_id(client: TestClient) -> int:
    items = client.get("/api/activities", params={"sport": "run", "limit": 1}).json()["items"]
    return int(items[0]["activity_id"])
