"""Database backups with pg_dump/pg_restore (custom format), rotation and verification.

The container image ships the PostgreSQL 17 client tools. Backups land in settings.backups_dir
(./data/backups on the host) and are git-ignored.
"""

from __future__ import annotations

import contextlib
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.pool import NullPool

from garminizer.config import Settings, get_settings
from garminizer.db.base import SCHEMA

PREFIX = "garminizer-"
SUFFIX = ".dump"


class BackupError(RuntimeError):
    """pg_dump/pg_restore missing or failed."""


@dataclass(frozen=True)
class BackupFile:
    path: Path
    size_bytes: int
    created_at: datetime


def _libpq_url(database_url: str) -> str:
    """postgresql+psycopg://… → postgresql://… (what pg_dump understands)."""
    url = make_url(database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


def _tool(name: str) -> str:
    found = shutil.which(name)
    if not found:
        raise BackupError(
            f"{name} not found. Run backups inside the Docker stack "
            "(docker compose exec worker garminizer backup) or install the PostgreSQL 17 client."
        )
    return found


def list_backups(settings: Settings | None = None) -> list[BackupFile]:
    settings = settings or get_settings()
    folder = settings.backups_dir
    if not folder.is_dir():
        return []
    files = sorted(folder.glob(f"{PREFIX}*{SUFFIX}"), reverse=True)
    return [
        BackupFile(f, f.stat().st_size, datetime.fromtimestamp(f.stat().st_mtime, UTC))
        for f in files
    ]


def create_backup(settings: Settings | None = None, *, keep: int | None = None) -> BackupFile:
    """Dump the whole database, then delete the oldest backups beyond `keep`."""
    settings = settings or get_settings()
    folder = settings.backups_dir
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    target = folder / f"{PREFIX}{stamp}{SUFFIX}"
    proc = subprocess.run(
        [
            _tool("pg_dump"),
            "--format=custom",
            "--no-owner",
            "--file",
            str(target),
            "--dbname",
            _libpq_url(settings.database_url),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        target.unlink(missing_ok=True)
        raise BackupError(f"pg_dump failed: {proc.stderr.strip()[:500]}")
    with contextlib.suppress(OSError):  # not supported on every filesystem
        target.chmod(0o600)
    for old in list_backups(settings)[keep or settings.backup_keep :]:
        old.path.unlink(missing_ok=True)
    return BackupFile(target, target.stat().st_size, datetime.now(UTC))


def restore_backup(path: Path, settings: Settings | None = None) -> None:
    """Restore a dump into the configured database (replaces existing objects)."""
    settings = settings or get_settings()
    if not path.is_file():
        raise BackupError(f"backup file not found: {path}")
    proc = subprocess.run(
        [
            _tool("pg_restore"),
            "--clean",
            "--if-exists",
            "--no-owner",
            "--single-transaction",
            "--dbname",
            _libpq_url(settings.database_url),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise BackupError(f"pg_restore failed: {proc.stderr.strip()[:500]}")


def row_counts(database_url: str) -> dict[str, int]:
    """Exact row count per table in the garmin schema (used to verify a restore)."""
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            tables = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = :s AND table_type = 'BASE TABLE' ORDER BY 1"
                ),
                {"s": SCHEMA},
            ).scalars()
            counts: dict[str, int] = {}
            for t in list(tables):
                sql = f'SELECT count(*) FROM "{SCHEMA}"."{t}"'  # noqa: S608 - catalog names
                counts[t] = int(conn.execute(text(sql)).scalar_one())
            return counts
    finally:
        engine.dispose()
