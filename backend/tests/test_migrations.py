"""A2: migrations build the schema from empty, match the models, and round-trip cleanly."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from sqlalchemy.pool import NullPool

import garminizer.models  # noqa: F401 - registers every table
from garminizer.db import SCHEMA, Base, migrate
from tests.conftest import create_fresh_database


def _tables(url: str) -> set[str]:
    engine = create_engine(url, poolclass=NullPool)
    try:
        return set(inspect(engine).get_table_names(schema=SCHEMA)) - {"alembic_version"}
    finally:
        engine.dispose()


def test_upgrade_downgrade_upgrade_roundtrip() -> None:
    url = create_fresh_database("_migrations")
    expected = {t.name for t in Base.metadata.sorted_tables}

    migrate.upgrade(url)
    assert _tables(url) == expected
    assert migrate.current_revision(url) is not None

    migrate.downgrade(url, "base")
    assert _tables(url) == set()
    assert migrate.current_revision(url) is None

    migrate.upgrade(url)
    assert _tables(url) == expected


def test_models_match_migrations(db_url: str) -> None:
    """Autogenerate against the migrated DB must find nothing to change."""
    engine = create_engine(db_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={
                    "include_schemas": True,
                    "include_name": lambda name, type_, _parents: (
                        name == SCHEMA if type_ == "schema" else True
                    ),
                    "compare_type": True,
                    "version_table_schema": SCHEMA,
                },
            )
            diff = compare_metadata(ctx, Base.metadata)
    finally:
        engine.dispose()
    assert diff == []


def test_every_table_has_a_comment(db_url: str) -> None:
    """The database documents itself (table comments are shown by any SQL client)."""
    engine = create_engine(db_url, poolclass=NullPool)
    try:
        insp = inspect(engine)
        missing = [
            t
            for t in insp.get_table_names(schema=SCHEMA)
            if t != "alembic_version" and not insp.get_table_comment(t, schema=SCHEMA)["text"]
        ]
    finally:
        engine.dispose()
    assert missing == []
