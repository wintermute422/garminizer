"""Garmin connection and sync: status, coverage, connect (+ MFA), disconnect, start a run.

The e-mail/password go straight to the Garmin library and are dropped after the login; only
the library's tokens are kept (settings.token_dir, 0600). A pending MFA login lives in this
process's memory only. Runs start in a background thread and are serialized by the engine's
cross-process lock.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.api.deps import SessionDep, data_bounds, rows
from garminizer.api.schemas import Model
from garminizer.config import Settings
from garminizer.garmin import auth
from garminizer.garmin.client import GarminAuthError, GarminError, GarminRateLimitError
from garminizer.sync import engine
from garminizer.sync.datasets import DAILY

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sync", tags=["sync"])
_JOB_LOCK = threading.Lock()
_PENDING_ATTR = "sync_pending_mfa"


class SyncRunOut(Model):
    id: int
    kind: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    requests: int
    items_written: int
    message: str | None


class SyncCursorOut(Model):
    dataset: str
    oldest_day: date | None
    newest_day: date | None
    complete: bool
    updated_at: datetime


class SyncErrorOut(Model):
    id: int
    run_id: int | None
    dataset: str
    key: str | None
    error: str
    occurred_at: datetime


class SyncStatus(Model):
    connected: bool = Field(description="Garmin tokens are present and look valid")
    is_demo: bool
    running: bool
    mfa_pending: bool
    last_runs: list[SyncRunOut]
    cursors: list[SyncCursorOut]
    recent_errors: list[SyncErrorOut]
    first_day: date | None
    last_day: date | None


class SyncCoverageMonth(Model):
    dataset: str
    month: str = Field(description="YYYY-MM")
    days: int = Field(description="Days fetched from Garmin")
    days_with_data: int = Field(description="Days whose response was not empty")


class SyncCoverage(Model):
    datasets: list[str]
    months: list[SyncCoverageMonth]


class SyncConnectRequest(BaseModel):
    email: Annotated[str, Field(min_length=3, max_length=320)]
    password: Annotated[SecretStr, Field(min_length=1, max_length=512)]


class SyncMfaRequest(BaseModel):
    code: Annotated[str, Field(min_length=1, max_length=32)]


class SyncRunRequest(BaseModel):
    kind: Literal["incremental", "backfill"] = "incremental"


class SyncConnectResult(Model):
    status: Literal["ok", "needs_mfa"]


class SyncRunAccepted(Model):
    status: Literal["started"]
    kind: Literal["incremental", "backfill"]


class SyncDisconnectResult(Model):
    connected: bool


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def _factory(request: Request) -> auth.GarminFactory | None:
    return getattr(request.app.state, "garmin_factory", None)


def _pending(request: Request) -> auth.PendingMfa | None:
    pending: auth.PendingMfa | None = getattr(request.app.state, _PENDING_ATTR, None)
    if pending is not None and pending.expired():
        setattr(request.app.state, _PENDING_ATTR, None)
        return None
    return pending


def _refuse_demo(session: Session) -> None:
    if engine.is_demo(session):
        raise HTTPException(status_code=409, detail=engine.DEMO_MESSAGE)


def _garmin_http_error(exc: GarminError) -> HTTPException:
    if isinstance(exc, GarminAuthError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, GarminRateLimitError):
        return HTTPException(status_code=429, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/status", response_model=SyncStatus)
def status(session: SessionDep, request: Request) -> SyncStatus:
    """Connection state, recent runs, per-dataset progress and recent (redacted) errors."""
    first, last = data_bounds(session)
    return SyncStatus(
        connected=auth.has_tokens(_settings(request)),
        is_demo=engine.is_demo(session),
        running=engine.is_running(session),
        mfa_pending=_pending(request) is not None,
        last_runs=[
            SyncRunOut.model_validate(r)
            for r in session.scalars(select(m.SyncRun).order_by(m.SyncRun.id.desc()).limit(10))
        ],
        cursors=[
            SyncCursorOut.model_validate(c)
            for c in session.scalars(select(m.SyncCursor).order_by(m.SyncCursor.dataset))
        ],
        recent_errors=[
            SyncErrorOut.model_validate(e)
            for e in session.scalars(select(m.SyncError).order_by(m.SyncError.id.desc()).limit(20))
        ],
        first_day=first,
        last_day=last,
    )


@router.get("/coverage", response_model=SyncCoverage)
def coverage(session: SessionDep) -> SyncCoverage:
    """Per daily dataset and month: days fetched and days with a non-empty response."""
    names = [d.name for d in DAILY]
    data = rows(
        session,
        """
        SELECT dataset, substr(key, 1, 7) AS month, count(*) AS days,
               count(*) FILTER (
                 WHERE payload IS NOT NULL AND jsonb_typeof(payload) <> 'null'
                   AND payload <> '{}'::jsonb AND payload <> '[]'::jsonb
               ) AS days_with_data
        FROM garmin.raw_payload
        WHERE dataset = ANY(:names) AND key ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
        GROUP BY 1, 2 ORDER BY 1, 2
        """,
        names=names,
    )
    return SyncCoverage(datasets=names, months=[SyncCoverageMonth(**r) for r in data])


@router.post("/connect", response_model=SyncConnectResult)
def connect(body: SyncConnectRequest, session: SessionDep, request: Request) -> SyncConnectResult:
    """Log in to Garmin; answers needs_mfa when Garmin sends a code (then POST /mfa)."""
    _refuse_demo(session)
    setattr(request.app.state, _PENDING_ATTR, None)
    try:
        result = auth.login(
            body.email,
            body.password.get_secret_value(),
            settings=_settings(request),
            factory=_factory(request),
        )
    except GarminError as exc:
        raise _garmin_http_error(exc) from None
    if result.status == "needs_mfa":
        setattr(request.app.state, _PENDING_ATTR, result.state)
    else:
        _start_job("incremental", request)
    return SyncConnectResult(status=result.status)


@router.post("/mfa", response_model=SyncConnectResult)
def mfa(body: SyncMfaRequest, session: SessionDep, request: Request) -> SyncConnectResult:
    """Finish the pending login with the MFA code Garmin sent."""
    _refuse_demo(session)
    pending = _pending(request)
    if pending is None:
        raise HTTPException(status_code=409, detail="no Garmin login is waiting for an MFA code")
    try:
        auth.complete_mfa(pending, body.code, settings=_settings(request))
    except GarminError as exc:
        raise _garmin_http_error(exc) from None
    setattr(request.app.state, _PENDING_ATTR, None)
    _start_job("incremental", request)
    return SyncConnectResult(status="ok")


@router.post("/disconnect", response_model=SyncDisconnectResult)
def disconnect(request: Request) -> SyncDisconnectResult:
    """Delete the local Garmin tokens (does not touch the Garmin account)."""
    setattr(request.app.state, _PENDING_ATTR, None)
    auth.disconnect(_settings(request))
    return SyncDisconnectResult(connected=auth.has_tokens(_settings(request)))


def _job(
    kind: Literal["incremental", "backfill"],
    settings: Settings,
    session_factory: Any,
    factory: auth.GarminFactory | None,
) -> None:
    try:
        client = auth.resume(settings, factory)
        if kind == "incremental":
            engine.incremental(session_factory, client, settings=settings)
        else:
            engine.backfill(session_factory, client, settings=settings)
    except GarminError as exc:
        engine.record_failed_run(session_factory, kind, str(exc))
    except engine.SyncBusyError as exc:
        log.info("sync not started: %s", exc)
    except Exception as exc:  # keep the background thread from dying silently
        log.error("sync %s failed: %s", kind, type(exc).__name__)
    finally:
        _JOB_LOCK.release()


def _start_job(kind: Literal["incremental", "backfill"], request: Request) -> bool:
    """Run a sync in a background thread; False when one is already running here."""
    if not _JOB_LOCK.acquire(blocking=False):
        return False
    try:
        threading.Thread(
            target=_job,
            args=(kind, _settings(request), request.app.state.session_factory, _factory(request)),
            name=f"garminizer-{kind}",
            daemon=True,
        ).start()
    except BaseException:
        _JOB_LOCK.release()
        raise
    return True


@router.post("/run", response_model=SyncRunAccepted, status_code=202)
def run(body: SyncRunRequest, session: SessionDep, request: Request) -> SyncRunAccepted:
    """Start an incremental sync or a backfill in the background (see GET /status)."""
    _refuse_demo(session)
    if not auth.has_tokens(_settings(request)):
        raise HTTPException(status_code=409, detail="not connected to Garmin")
    if engine.is_running(session) or not _start_job(body.kind, request):
        raise HTTPException(status_code=409, detail="a sync is already running")
    return SyncRunAccepted(status="started", kind=body.kind)
