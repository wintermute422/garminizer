"""A2: migrations build the schema from empty, match the models, and round-trip cleanly."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
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


def test_0004_clears_zero_body_composition_readings() -> None:
    """Rows stored before the parser fix: 0 readings become NULL, real readings stay."""
    url = create_fresh_database("_migrations_0004")
    migrate.upgrade(url, "0003")
    engine = create_engine(url, poolclass=NullPool)
    cols = (
        "bmi, body_fat_pct, body_water_pct, muscle_mass_kg, bone_mass_kg, visceral_fat, "
        "metabolic_age"
    )
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {SCHEMA}.body_composition (measured_at, weight_kg, {cols}) "
                    "VALUES ('2024-05-01T05:00Z', 72.4, 0, 0, 0, 0, 0, 0, 0), "
                    "('2024-05-02T05:00Z', 72.1, 22.7, 15.1, 58.0, 34.4, 3.3, 6, 30), "
                    "('2024-05-03T05:00Z', 72.0, 22.6, 0, NULL, 34.3, 0, 6, NULL)"
                )
            )
        migrate.upgrade(url)
        with engine.connect() as conn:
            got = conn.execute(
                text(
                    f"SELECT weight_kg, {cols} FROM {SCHEMA}.body_composition ORDER BY measured_at"
                )
            ).all()
    finally:
        engine.dispose()
    approx = [tuple(None if v is None else round(v, 1) for v in r) for r in got]
    assert approx == [
        (72.4, None, None, None, None, None, None, None),
        (72.1, 22.7, 15.1, 58.0, 34.4, 3.3, 6.0, 30.0),
        (72.0, 22.6, None, None, 34.3, None, 6.0, None),
    ]


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
