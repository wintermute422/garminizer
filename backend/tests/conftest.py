"""Shared fixtures: throwaway test databases in the dev Postgres (scripts/devdb.sh up)."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import URL
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer.db import migrate

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://garminizer:garminizer-dev@127.0.0.1:55432/garminizer_test",
)


def create_fresh_database(name_suffix: str = "") -> str:
    """(Re)create an empty database named *_test[_suffix]; refuses any other name."""
    base = make_url(TEST_DATABASE_URL)
    name = f"{base.database}{name_suffix}"
    if not name.endswith("_test") and "_test_" not in name:
        raise RuntimeError(f"refusing to recreate non-test database {name!r}")
    admin_url: URL = base.set(database="postgres")
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{name}"'))
    except OperationalError as exc:  # pragma: no cover - environment problem
        raise RuntimeError(
            "Test database not reachable. Start it with `bash scripts/devdb.sh up` "
            "or set TEST_DATABASE_URL."
        ) from exc
    finally:
        admin.dispose()
    return base.set(database=name).render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def db_url() -> str:
    """A migrated, empty test database shared by the whole session."""
    url = create_fresh_database()
    migrate.upgrade(url)
    return url


@pytest.fixture
def db(db_url: str) -> Iterator[Session]:
    """A session whose changes are rolled back after the test."""
    engine = create_engine(db_url, poolclass=NullPool)
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()
