"""Starting a sync: the one entry point for the worker, the API and the CLI.

``start(kind, deps)`` checks the preconditions (demo database, saved tokens, a finished
backfill), resumes the Garmin session, runs the engine and returns an ``Outcome``. Every
caller only maps the outcome to its own world: a log line (worker), an HTTP status (API) or
an exit code (CLI). A failed token resume is always recorded as a failed run (once per
distinct message), so the Sync page shows why nothing happened.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Literal

from sqlalchemy import select

from garminizer import models as m
from garminizer.config import Settings
from garminizer.garmin import auth
from garminizer.garmin.client import GarminError
from garminizer.sync import engine
from garminizer.sync.engine import RunSummary, SessionFactory

log = logging.getLogger(__name__)

Kind = Literal["incremental", "quick", "backfill"]


@dataclass(frozen=True)
class SyncDeps:
    """What a sync needs; built once where the process starts (worker, API app, CLI)."""

    session_factory: SessionFactory
    settings: Settings
    garmin_factory: auth.GarminFactory | None = None


@dataclass(frozen=True)
class Ran:
    summary: RunSummary


@dataclass(frozen=True)
class Skipped:
    """Nothing to do: ``demo``, ``not_connected`` or ``complete`` (backfill already done)."""

    reason: Literal["demo", "not_connected", "complete"]
    message: str


@dataclass(frozen=True)
class Busy:
    message: str


@dataclass(frozen=True)
class Failed:
    """The run could not start (e.g. rejected tokens); recorded in sync_run."""

    message: str


Outcome = Ran | Skipped | Busy | Failed

NOT_CONNECTED = "not connected to Garmin (no saved tokens)"


def start(
    kind: Kind,
    deps: SyncDeps,
    *,
    budget_s: float | None = None,
    until: date | None = None,
    today: date | None = None,
    skip_if_complete: bool = False,
) -> Outcome:
    """Run one incremental sync, one quick sync (activities + weigh-ins) or one (budgeted)
    backfill chunk.

    ``skip_if_complete`` (the worker's backfill job): do nothing once every dataset is
    backfilled; a manual backfill still refreshes recent days and missing details.
    """
    with deps.session_factory() as s:
        if engine.is_demo(s):
            return Skipped("demo", engine.DEMO_MESSAGE)
        if kind == "backfill" and skip_if_complete and engine.all_complete(s):
            return Skipped("complete", "backfill complete")
    if not auth.has_tokens(deps.settings):
        return Skipped("not_connected", NOT_CONNECTED)
    try:
        client = auth.resume(deps.settings, deps.garmin_factory)
    except GarminError as exc:
        record_failed_start(deps.session_factory, kind, str(exc))
        return Failed(str(exc))
    try:
        if kind == "incremental":
            summary = engine.incremental(
                deps.session_factory, client, today, settings=deps.settings
            )
        elif kind == "quick":
            summary = engine.quick(deps.session_factory, client, today, settings=deps.settings)
        else:
            summary = engine.backfill(
                deps.session_factory,
                client,
                until,
                budget_s,
                today=today,
                settings=deps.settings,
            )
    except engine.SyncBusyError as exc:
        return Busy(str(exc))
    except engine.DemoDatabaseError as exc:  # became a demo database since the check above
        return Skipped("demo", str(exc))
    return Ran(summary)


def record_failed_start(session_factory: SessionFactory, kind: str, message: str) -> None:
    """A failed run row, unless the latest run of this kind already failed the same way.

    The worker retries every few minutes; one row per distinct failure keeps /status readable.
    """
    with session_factory() as s:
        last = s.execute(
            select(m.SyncRun.status, m.SyncRun.message)
            .where(m.SyncRun.kind == kind)
            .order_by(m.SyncRun.id.desc())
            .limit(1)
        ).first()
    if last is not None and last.status == "error" and last.message == message[:500]:
        return
    engine.record_failed_run(session_factory, kind, message)


def describe_outcome(kind: Kind, outcome: Outcome) -> str:
    """One log line for an outcome (no personal data: messages are engine/auth texts)."""
    match outcome:
        case Ran(summary):
            return (
                f"{kind}: {summary.status}, {summary.requests} requests, "
                f"{summary.items_written} rows, {summary.errors} errors"
                + (f" - {summary.message}" if summary.message else "")
            )
        case Skipped(_, message) | Busy(message):
            return f"{kind} skipped: {message}"
        case Failed(message):
            return f"{kind} failed: {message}"
