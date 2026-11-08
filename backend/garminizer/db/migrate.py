"""Programmatic Alembic: migrations ship inside the package, no alembic.ini needed."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from garminizer.config import get_settings
from garminizer.db.base import SCHEMA

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


def alembic_config(url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Passed via attributes, not the ini option: ConfigParser would choke on '%' in passwords.
    cfg.attributes["url"] = url or get_settings().database_url
    return cfg


def upgrade(url: str | None = None, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str | None = None, revision: str = "base") -> None:
    command.downgrade(alembic_config(url), revision)


def current_revision(url: str | None = None) -> str | None:
    engine = create_engine(url or get_settings().database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            has_schema = conn.execute(
                text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s"),
                {"s": SCHEMA},
            ).first()
            if not has_schema:
                return None
            ctx = MigrationContext.configure(conn, opts={"version_table_schema": SCHEMA})
            return ctx.get_current_revision()
    finally:
        engine.dispose()
