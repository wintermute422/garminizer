"""Alembic environment: everything lives in the `garmin` schema."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from alembic import context
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import garminizer.models  # noqa: F401 - registers all tables on Base.metadata
from garminizer.db.base import SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def include_name(name: str | None, type_: str, parent_names: Mapping[Any, Any]) -> bool:
    if type_ == "schema":
        return name == SCHEMA
    return True


def run_migrations_online() -> None:
    url = config.attributes["url"]
    engine = create_engine(url, poolclass=NullPool)
    with engine.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
        connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=SCHEMA,
            include_schemas=True,
            include_name=include_name,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run against a database.")
run_migrations_online()
