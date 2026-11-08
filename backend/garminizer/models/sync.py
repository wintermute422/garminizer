"""Sync bookkeeping: runs, per-dataset cursors and errors."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Big, TsTz


class SyncRun(Base):
    __tablename__ = "sync_run"
    __table_args__ = {"comment": "One row per sync/backfill/reparse run."}

    id: Mapped[Big] = mapped_column(primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(comment="incremental | backfill | reparse | demo")
    started_at: Mapped[TsTz] = mapped_column(server_default=func.now())
    finished_at: Mapped[TsTz | None]
    status: Mapped[str] = mapped_column(server_default="running", comment="running | ok | error")
    requests: Mapped[int] = mapped_column(server_default="0")
    items_written: Mapped[int] = mapped_column(server_default="0")
    message: Mapped[str | None]


class SyncCursor(Base):
    __tablename__ = "sync_cursor"
    __table_args__ = {"comment": "How far each dataset has been synced (resume point)."}

    dataset: Mapped[str] = mapped_column(primary_key=True)
    oldest_day: Mapped[date | None] = mapped_column(comment="Backfill has reached this day")
    newest_day: Mapped[date | None] = mapped_column(comment="Incremental sync reached this day")
    complete: Mapped[bool] = mapped_column(
        server_default="false", comment="Backfill reached the first day with data"
    )
    state: Mapped[dict[str, Any] | None] = mapped_column(comment="Dataset-specific resume state")
    updated_at: Mapped[TsTz] = mapped_column(server_default=func.now())


class SyncError(Base):
    __tablename__ = "sync_error"
    __table_args__ = {"comment": "Errors during sync (kept for diagnosis, values redacted)."}

    id: Mapped[Big] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[Big | None] = mapped_column(ForeignKey("sync_run.id", ondelete="SET NULL"))
    dataset: Mapped[str]
    key: Mapped[str | None]
    error: Mapped[str]
    occurred_at: Mapped[TsTz] = mapped_column(server_default=func.now())
