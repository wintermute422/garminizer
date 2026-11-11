"""Sync engine: incremental sync, resumable backfill, reparse, run bookkeeping and locking.

Raw first: every response is stored verbatim in raw_payload (sha256 change detection) and then
parsed into the typed tables; `reparse` rebuilds the typed tables from raw_payload alone.
Each unit of work (one dataset-day, one month, one per-activity request, one activity-list
page) is committed on its own, together with its sync_cursor update, so a crash or a time
budget loses at most one unit and the next run resumes where the last one stopped.

Only one run at a time, across processes: a Postgres advisory lock (held on a dedicated
autocommit connection for the run) plus a thread lock for runs inside one process.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Connection, Engine, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.analytics import pipeline
from garminizer.athlete import athlete_clock
from garminizer.config import Settings, get_settings
from garminizer.garmin import auth
from garminizer.garmin.client import (
    GarminClient,
    GarminError,
    GarminNotFoundError,
    GarminRequestError,
)
from garminizer.sync import fit, private_values, store
from garminizer.sync.datasets import (
    ACTIVITY,
    ACTIVITY_PAGE_SIZE,
    DAILY,
    DATASETS,
    DETAIL,
    PARSE_ORDER,
    RANGE,
    STATIC,
    Dataset,
    FetchContext,
    Unit,
)
from garminizer.sync.parsers.common import ParseContext, ShapeError, day_of, month_bounds
from garminizer.sync.parsers.profile import first_account_day_candidates

log = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]
ADVISORY_LOCK_KEY = 1_196_575_066  # "GRMZ"; < 2**31 so pg_locks shows it as objid
OVERLAP_DAYS = 2
DEFAULT_HISTORY_DAYS = 365
EARLIEST_PLAUSIBLE_DAY = date(2000, 1, 1)
_THREAD_LOCK = threading.Lock()


class DemoDatabaseError(RuntimeError):
    """The target database holds the synthetic demo athlete."""


class SyncBusyError(RuntimeError):
    """Another sync/backfill/reparse run holds the lock."""


DEMO_MESSAGE = (
    "This database contains the synthetic demo athlete; refusing to mix real Garmin data into "
    "it. Use a separate database (DATABASE_URL) or reset the demo database first."
)


@dataclass(frozen=True)
class RunSummary:
    run_id: int
    kind: str
    status: str
    requests: int
    items_written: int
    errors: int
    message: str | None
    done: bool = False


@dataclass
class _Run:
    session_factory: SessionFactory
    client: GarminClient
    settings: Settings
    run_id: int
    kind: str
    today: date
    deadline: float | None
    start_requests: int
    items: int = 0
    errors: int = 0
    activity_ids: set[int] = field(default_factory=set)
    budget_hit: bool = False

    @property
    def requests(self) -> int:
        return self.client.request_count - self.start_requests

    def out_of_time(self) -> bool:
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.budget_hit = True
        return self.budget_hit

    def ctx(self) -> FetchContext:
        return FetchContext(today=self.today, identity=self.client.identity)


# --- guards, lock, helpers ------------------------------------------------------------------


def is_demo(session: Session) -> bool:
    return bool(session.scalar(select(m.Athlete.is_demo).where(m.Athlete.id == 1)))


def ensure_not_demo(session: Session) -> None:
    if is_demo(session):
        raise DemoDatabaseError(DEMO_MESSAGE)


def is_running(session: Session) -> bool:
    """True while any process holds the sync lock on this database."""
    if _THREAD_LOCK.locked():
        return True
    return bool(
        session.scalar(
            text(
                "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
                "AND database = (SELECT oid FROM pg_database WHERE datname = current_database()) "
                "AND classid::bigint = 0 AND objid::bigint = :k AND objsubid = 1)"
            ),
            {"k": ADVISORY_LOCK_KEY},
        )
    )


@contextmanager
def run_lock(bind: Engine | Connection) -> Iterator[None]:
    """Hold the process-wide and database-wide sync lock, or raise SyncBusyError."""
    if not _THREAD_LOCK.acquire(blocking=False):
        raise SyncBusyError("a Garmin sync is already running in this process")
    own = isinstance(bind, Engine)
    locked = False
    lock_conn: Connection | None = None
    try:
        lock_conn = (
            bind.connect().execution_options(isolation_level="AUTOCOMMIT")
            if isinstance(bind, Engine)
            else bind
        )
        locked = bool(
            lock_conn.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": ADVISORY_LOCK_KEY}
            ).scalar()
        )
        if not locked:
            raise SyncBusyError("a Garmin sync is already running (another process holds the lock)")
        yield
    finally:
        try:
            if locked and lock_conn is not None:
                lock_conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": ADVISORY_LOCK_KEY})
        finally:
            if own and lock_conn is not None:
                lock_conn.close()
            _THREAD_LOCK.release()


def _bind_of(session_factory: SessionFactory) -> Engine | Connection:
    with session_factory() as s:
        bind = s.get_bind()
    assert isinstance(bind, Engine | Connection)
    return bind


def describe(exc: BaseException) -> str:
    """An error message without payload or SQL parameter values."""
    if isinstance(exc, ShapeError | GarminError):
        return str(exc)[:300]
    if isinstance(exc, KeyError):
        return f"missing field {str(exc.args[0])[:60]!r}" if exc.args else "missing field"
    if isinstance(exc, DBAPIError):
        code = getattr(exc.orig, "sqlstate", None)
        return f"database error {type(exc.orig).__name__} (sqlstate {code})"
    if isinstance(exc, SQLAlchemyError):
        return f"database error {type(exc).__name__}"
    return f"parser error {type(exc).__name__}"


def _record_error(
    session: Session, run: _Run | None, dataset: str, key: str | None, msg: str
) -> None:
    session.execute(
        insert(m.SyncError).values(
            run_id=run.run_id if run else None, dataset=dataset, key=key, error=msg[:500]
        )
    )
    if run is not None:
        run.errors += 1
    log.warning("sync %s/%s: %s", dataset, key, msg)


def _cursor(session: Session, name: str) -> m.SyncCursor:
    cur = session.get(m.SyncCursor, name)
    if cur is None:
        cur = m.SyncCursor(dataset=name, complete=False)
        session.add(cur)
    return cur


def _touch(
    session: Session,
    name: str,
    *,
    oldest: date | None = None,
    newest: date | None = None,
    complete: bool | None = None,
    state: dict[str, Any] | None = None,
) -> None:
    cur = _cursor(session, name)
    if oldest is not None:
        cur.oldest_day = min(cur.oldest_day, oldest) if cur.oldest_day else oldest
    if newest is not None:
        cur.newest_day = max(cur.newest_day, newest) if cur.newest_day else newest
    if complete is not None:
        cur.complete = complete
    if state is not None:
        cur.state = state
    cur.updated_at = datetime.now(UTC)


def _cursors(session: Session) -> dict[str, m.SyncCursor]:
    return {c.dataset: c for c in session.scalars(select(m.SyncCursor))}


# --- parsing --------------------------------------------------------------------------------


def parse_payload(
    session: Session, ds: Dataset, key: str, payload: Any, run: _Run | None = None
) -> int:
    """Parse one raw payload into the typed tables (savepoint: a failure leaves no rows)."""
    try:
        with session.begin_nested():
            if ds.binary:
                aid = ParseContext(ds.name, key).require_activity_id()
                written = fit.ingest_samples(session, aid)
            else:
                written = store.apply(session, ds.parser(payload, ParseContext(ds.name, key)))
    except Exception as exc:
        msg = describe(exc)
        store.mark_parsed(session, ds.name, key, msg)
        _record_error(session, run, ds.name, key, msg)
        return 0
    store.mark_parsed(session, ds.name, key)
    if run is not None:
        run.items += written
    return written


def _ingest(session: Session, run: _Run, ds: Dataset, key: str, payload: Any) -> bool:
    """Store the raw payload, parse it when new/changed/unparsed. Returns True if changed."""
    state = store.store_raw(session, ds.name, key, ds.method or "login", payload)
    if state.changed or not state.parsed:
        parse_payload(session, ds, key, payload, run)
    return state.changed


def _fetch(run: _Run, ds: Dataset, unit: Unit) -> tuple[bool, Any, str | None]:
    """(ok, payload, error). 404 = no data; other request errors are terminal for the unit."""
    assert ds.method is not None
    args, kwargs = ds.args(unit, run.ctx())
    try:
        return True, run.client.call(ds.method, *args, **kwargs), None
    except GarminNotFoundError:
        return True, None, None
    except GarminRequestError as exc:
        return False, None, str(exc)


def _placeholder(session: Session, ds: Dataset, key: str, error: str) -> None:
    """Remember a failed request (no raw row yet) so the unit is not retried forever."""
    exists = session.scalar(
        select(func.count())
        .select_from(m.RawPayload)
        .where(m.RawPayload.dataset == ds.name, m.RawPayload.key == key)
    )
    if not exists:
        store.store_raw(session, ds.name, key, ds.method or "login", None)
        store.mark_parsed(session, ds.name, key, error)


def _process_unit(
    run: _Run, ds: Dataset, unit: Unit, on_commit: Callable[[Session], None] | None = None
) -> bool:
    """Fetch, store and parse one unit; commits together with its cursor update."""
    if ds.binary:
        return _process_file(run, ds, unit, on_commit)
    ok, payload, error = _fetch(run, ds, unit)
    with run.session_factory() as s:
        changed = False
        if ok:
            changed = _ingest(s, run, ds, unit.key, payload)
        else:
            _record_error(s, run, ds.name, unit.key, error or "request failed")
            _placeholder(s, ds, unit.key, error or "request failed")
        if on_commit is not None:
            on_commit(s)
        s.commit()
    return changed


def _process_file(
    run: _Run, ds: Dataset, unit: Unit, on_commit: Callable[[Session], None] | None
) -> bool:
    assert unit.activity_id is not None
    ok, content, error = _fetch(run, ds, unit)
    with run.session_factory() as s:
        changed = False
        if not ok:
            _record_error(s, run, ds.name, unit.key, error or "download failed")
            _placeholder(s, ds, unit.key, error or "download failed")
        else:
            meta: dict[str, Any] | None = None
            if isinstance(content, bytes | bytearray) and content:
                data = bytes(content)
                digest = fit.store_file(s, unit.activity_id, data)
                meta = {
                    "sha256": digest,
                    "size_bytes": len(data),
                    "has_fit": fit.extract_fit(data) is not None,
                }
            changed = _ingest(s, run, ds, unit.key, meta)
        if on_commit is not None:
            on_commit(s)
        s.commit()
    return changed


# --- static datasets --------------------------------------------------------------------------


def _identity_payload(client: GarminClient) -> dict[str, Any]:
    i = client.identity
    return {"displayName": i.display_name, "fullName": i.full_name, "profileId": i.profile_id}


def _sync_static(run: _Run, *, only_missing: bool) -> bool:
    cursors = _with_session(run, _cursors)
    for ds in STATIC:
        if only_missing and (cur := cursors.get(ds.name)) is not None and cur.complete:
            continue
        if run.out_of_time():
            return False
        if ds.method is None:
            with run.session_factory() as s:
                _ingest(s, run, ds, "self", _identity_payload(run.client))
                _touch(s, ds.name, oldest=run.today, newest=run.today, complete=True)
                s.commit()
            continue
        if ds.requires_profile_id and run.client.identity.profile_id is None:
            with run.session_factory() as s:
                _record_error(s, run, ds.name, None, "skipped: Garmin profile id unknown")
                s.commit()
            continue
        keys = _with_session(run, ds.keys) if ds.keys else ["self"]
        for key in keys:
            if run.out_of_time():
                return False
            _process_unit(run, ds, Unit(key))

        def mark(s: Session, name: str = ds.name) -> None:
            _touch(s, name, oldest=run.today, newest=run.today, complete=True)

        _with_session(run, mark, commit=True)
    return True


def _with_session(run: _Run, fn: Callable[[Session], Any], *, commit: bool = False) -> Any:
    with run.session_factory() as s:
        result = fn(s)
        if commit:
            s.commit()
        return result


# --- activities -------------------------------------------------------------------------------


def _activity_day(item: dict[str, Any], today: date) -> date:
    return day_of(item.get("startTimeLocal")) or day_of(item.get("startTimeGMT")) or today


def _activity_page(run: _Run, start: int) -> list[dict[str, Any]]:
    try:
        page = run.client.call("get_activities", start, ACTIVITY_PAGE_SIZE)
    except GarminNotFoundError:
        return []
    if isinstance(page, dict):
        page = page.get("activityList") or []
    if not isinstance(page, list):
        raise GarminRequestError("get_activities: unexpected response shape")
    return [a for a in page if isinstance(a, dict)]


def _ingest_page(run: _Run, items: list[dict[str, Any]]) -> list[tuple[int, date, bool]]:
    """Store/parse list items; returns (activity id, local start day, changed)."""
    out: list[tuple[int, date, bool]] = []
    with run.session_factory() as s:
        for item in items:
            aid = item.get("activityId")
            if not isinstance(aid, int) or isinstance(aid, bool) or aid <= 0:
                _record_error(s, run, ACTIVITY.name, None, "activity list item without activityId")
                continue
            day = _activity_day(item, run.today)
            changed = _ingest(s, run, ACTIVITY, str(aid), item)
            if changed:
                run.activity_ids.add(aid)
            out.append((aid, day, changed))
        if out:
            days = [d for _, d, _ in out]
            _touch(s, ACTIVITY.name, oldest=min(days), newest=max(days))
        s.commit()
    return out


def _detail_status(session: Session, ids: list[int]) -> dict[int, set[str]]:
    """Per activity: which detail datasets already have a raw payload."""
    if not ids:
        return {}
    rows = session.execute(
        select(m.RawPayload.key, m.RawPayload.dataset).where(
            m.RawPayload.dataset.in_([d.name for d in DETAIL]),
            m.RawPayload.key.in_([str(i) for i in ids]),
        )
    ).all()
    out: dict[int, set[str]] = {i: set() for i in ids}
    for key, dataset in rows:
        out[int(key)].add(dataset)
    return out


def _fetch_details(run: _Run, aid: int, *, skip: set[str] | None = None) -> bool:
    """All per-activity requests for one activity (those in `skip` excepted)."""
    exists = _with_session(run, lambda s: s.get(m.Activity, aid) is not None)
    if not exists:
        return True
    for ds in DETAIL:
        if skip and ds.name in skip:
            continue
        if run.out_of_time():
            return False
        _process_unit(run, ds, Unit(str(aid), activity_id=aid))
    run.activity_ids.add(aid)
    return True


def _sync_activities_incremental(run: _Run) -> bool:
    newest_before = _with_session(
        run, lambda s: s.scalar(select(func.max(m.Activity.start_time_local)))
    )
    cutoff = (newest_before.date() if newest_before else run.today) - timedelta(days=OVERLAP_DAYS)
    seen: list[tuple[int, date, bool]] = []
    start = 0
    while True:
        if run.out_of_time():
            return False
        items = _activity_page(run, start)
        if not items:
            break
        page = _ingest_page(run, items)
        seen += page
        older = [changed for _, day, changed in page if day < cutoff]
        if any(not c for c in older) or (newest_before is None and older):
            break
        if len(items) < ACTIVITY_PAGE_SIZE:
            break
        start += len(items)
    status = _with_session(run, lambda s: _detail_status(s, [a for a, _, _ in seen]))
    complete = {d.name for d in DETAIL}
    for aid, day, changed in seen:
        had_details = status.get(aid, set()) >= complete
        recent = day >= cutoff
        if (changed and (recent or had_details)) or (recent and not had_details):
            skip = None if changed else status.get(aid)
            if not _fetch_details(run, aid, skip=skip):
                return False
    return True


def _sweep_details(run: _Run) -> bool:
    """Fetch the missing detail requests of every stored activity."""
    ids = _with_session(
        run,
        lambda s: list(
            s.scalars(select(m.Activity.activity_id).order_by(m.Activity.start_time_utc.desc()))
        ),
    )
    status = _with_session(run, lambda s: _detail_status(s, ids))
    complete = {d.name for d in DETAIL}
    for aid in ids:
        have = status.get(aid, set())
        if have >= complete:
            continue
        if not _fetch_details(run, aid, skip=have):
            return False
    return True


def _backfill_activities(run: _Run) -> bool:
    cur = _with_session(run, lambda s: s.get(m.SyncCursor, ACTIVITY.name))
    if cur is not None and cur.complete:
        return _sweep_details(run)
    next_start = int((cur.state or {}).get("next_start", 0)) if cur is not None else 0
    while True:
        if run.out_of_time():
            return False
        items = _activity_page(run, next_start)
        page = _ingest_page(run, items) if items else []
        ids = [aid for aid, _, _ in page]

        def details(s: Session, page_ids: list[int] = ids) -> dict[int, set[str]]:
            return _detail_status(s, page_ids)

        status = _with_session(run, details)
        for aid in ids:
            if not _fetch_details(run, aid, skip=status.get(aid)):
                return False
        next_start += len(items)
        exhausted = len(items) < ACTIVITY_PAGE_SIZE

        def save(s: Session, n: int = next_start) -> None:
            _touch(s, ACTIVITY.name, state={"next_start": n})

        _with_session(run, save, commit=True)
        if exhausted:
            if not _sweep_details(run):
                return False
            _with_session(run, lambda s: _touch(s, ACTIVITY.name, complete=True), commit=True)
            return True


# --- daily and range datasets ---------------------------------------------------------------


def _daily_unit(run: _Run, ds: Dataset, day: date) -> None:
    def cursor(s: Session) -> None:
        _touch(s, ds.name, oldest=day, newest=day)

    _process_unit(run, ds, Unit(day.isoformat(), day=day), cursor)


def _month_unit(run: _Run, ds: Dataset, month_start: date) -> None:
    start, end = month_bounds(month_start)
    end = min(end, run.today)

    def cursor(s: Session) -> None:
        _touch(s, ds.name, oldest=start, newest=end)

    _process_unit(run, ds, Unit(start.strftime("%Y-%m"), start=start, end=end), cursor)


def _months(first: date, last: date) -> list[date]:
    out, cur = [], first.replace(day=1)
    while cur <= last:
        out.append(cur)
        cur = month_bounds(cur)[1] + timedelta(days=1)
    return out


def _sync_daily_incremental(run: _Run) -> bool:
    cursors = _with_session(run, _cursors)
    default = run.today - timedelta(days=OVERLAP_DAYS)
    starts = {
        ds.name: min(run.today, cur.newest_day - timedelta(days=OVERLAP_DAYS))
        if (cur := cursors.get(ds.name)) is not None and cur.newest_day
        else default
        for ds in DAILY
    }
    day = min(starts.values())
    while day <= run.today:
        for ds in DAILY:
            if day < starts[ds.name]:
                continue
            if run.out_of_time():
                return False
            _daily_unit(run, ds, day)
        day += timedelta(days=1)
    return True


def _sync_ranges_incremental(run: _Run) -> bool:
    cursors = _with_session(run, _cursors)
    for ds in RANGE:
        cur = cursors.get(ds.name)
        start = (cur.newest_day if cur and cur.newest_day else run.today) - timedelta(
            days=OVERLAP_DAYS
        )
        for month in _months(min(start, run.today), run.today):
            if run.out_of_time():
                return False
            _month_unit(run, ds, month)
    return True


def _sync_recent_days(run: _Run) -> bool:
    """The last OVERLAP_DAYS of every daily/range dataset, skipping days already stored.

    Starts after each dataset's newest day, so a resumed run (or a later backfill chunk on the
    same day) asks Garmin for nothing twice.
    """
    cursors = _with_session(run, _cursors)
    floor = run.today - timedelta(days=OVERLAP_DAYS)

    def start(name: str) -> date:
        cur = cursors.get(name)
        newest: date | None = cur.newest_day if cur is not None else None
        return floor if newest is None else max(floor, newest + timedelta(days=1))

    for ds in RANGE:
        first = start(ds.name)
        for month in _months(first, run.today) if first <= run.today else []:
            if run.out_of_time():
                return False
            _month_unit(run, ds, month)
    starts = {ds.name: start(ds.name) for ds in DAILY}
    day = min(starts.values())
    while day <= run.today:
        for ds in DAILY:
            if day < starts[ds.name]:
                continue
            if run.out_of_time():
                return False
            _daily_unit(run, ds, day)
        day += timedelta(days=1)
    return True


def account_first_day(session: Session, today: date) -> date:
    """Earliest of the profile creation date (when Garmin sends one) and the first activity."""
    raw = {
        r.dataset: r.payload
        for r in session.execute(
            select(m.RawPayload.dataset, m.RawPayload.payload).where(
                m.RawPayload.dataset.in_(["profile_base", "user_settings"])
            )
        )
    }
    candidates = [
        day_of(v)
        for v in first_account_day_candidates(raw.get("profile_base"), raw.get("user_settings"))
    ]
    first_activity = session.scalar(select(func.min(m.Activity.start_time_local)))
    if first_activity is not None:
        candidates.append(first_activity.date())
    valid = [d for d in candidates if d is not None and EARLIEST_PLAUSIBLE_DAY <= d <= today]
    return min(valid) if valid else today - timedelta(days=DEFAULT_HISTORY_DAYS)


def _backfill_daily(run: _Run, floor: date, can_complete: bool) -> bool:
    cursors = _with_session(run, _cursors)
    pending: dict[str, date] = {}
    for ds in DAILY:
        cur = cursors.get(ds.name)
        if cur is not None and cur.complete:
            continue
        pending[ds.name] = (
            cur.oldest_day - timedelta(days=1) if cur is not None and cur.oldest_day else run.today
        )
    while pending:
        day = max(pending.values())
        if day < floor:
            if can_complete:

                def done(s: Session, names: tuple[str, ...] = tuple(pending)) -> None:
                    for name in names:
                        _touch(s, name, complete=True)

                _with_session(run, done, commit=True)
            return True
        for ds in DAILY:
            if pending.get(ds.name) != day:
                continue
            if run.out_of_time():
                return False
            _daily_unit(run, ds, day)
            pending[ds.name] = day - timedelta(days=1)
    return True


def _backfill_ranges(run: _Run, floor: date, can_complete: bool) -> bool:
    cursors = _with_session(run, _cursors)
    for ds in RANGE:
        cur = cursors.get(ds.name)
        if cur is not None and cur.complete:
            continue
        month = (
            (cur.oldest_day.replace(day=1) - timedelta(days=1)).replace(day=1)
            if cur is not None and cur.oldest_day
            else run.today.replace(day=1)
        )
        while month_bounds(month)[1] >= floor:
            if run.out_of_time():
                return False
            _month_unit(run, ds, month)
            month = (month - timedelta(days=1)).replace(day=1)
        if can_complete:

            def finished(s: Session, name: str = ds.name) -> None:
                _touch(s, name, complete=True)

            _with_session(run, finished, commit=True)
    return True


def _all_complete(session: Session) -> bool:
    cursors = _cursors(session)
    names = [d.name for d in (*STATIC, ACTIVITY, *DAILY, *RANGE)]
    return all((c := cursors.get(n)) is not None and c.complete for n in names)


# --- runs -------------------------------------------------------------------------------------


def _start_run(session_factory: SessionFactory, kind: str) -> int:
    with session_factory() as s:
        s.execute(
            update(m.SyncRun)
            .where(m.SyncRun.status == "running")
            .values(
                status="error",
                finished_at=datetime.now(UTC),
                message="interrupted (the process ended before the run finished)",
            )
        )
        run_id = s.execute(
            insert(m.SyncRun).values(kind=kind, status="running").returning(m.SyncRun.id)
        ).scalar_one()
        s.commit()
    return int(run_id)


def _finish_run(run: _Run, status: str, message: str | None) -> None:
    with run.session_factory() as s:
        s.execute(
            update(m.SyncRun)
            .where(m.SyncRun.id == run.run_id)
            .values(
                status=status,
                finished_at=datetime.now(UTC),
                requests=run.requests,
                items_written=run.items,
                message=message[:500] if message else None,
            )
        )
        s.commit()


def _analytics(run: _Run) -> None:
    """Derived tables for new/changed activities (and any still pending), then daily load."""
    with run.session_factory() as s:
        try:
            pending = set(
                s.scalars(
                    select(m.Activity.activity_id).where(
                        m.Activity.analytics_version < pipeline.ANALYTICS_VERSION
                    )
                )
            )
            ids = sorted(pending | run.activity_ids)
            if not ids and run.items == 0:
                return
            pipeline.run(s, activity_ids=ids, today=run.today)
            s.commit()
        except Exception as exc:
            s.rollback()
            _record_error(s, run, "analytics", None, describe(exc))
            s.commit()


def _update_private_values(run: _Run) -> None:
    """Refresh data/private_values.txt (profile identity + home area) for the secret scan."""
    try:
        with run.session_factory() as s:
            if s.get(m.Athlete, 1) is not None:
                private_values.update(s, run.settings.data_dir)
    except OSError as exc:
        log.warning("could not write private values (%s)", type(exc).__name__)


def _execute(
    kind: str,
    session_factory: SessionFactory,
    client: GarminClient,
    *,
    today: date | None,
    settings: Settings | None,
    budget_s: float | None,
    body: Callable[[_Run], tuple[str | None, bool]],
) -> RunSummary:
    settings = settings or get_settings()
    with session_factory() as s:
        ensure_not_demo(s)
        today = today or athlete_clock(s, settings.tz).today()
    with run_lock(_bind_of(session_factory)):
        run = _Run(
            session_factory=session_factory,
            client=client,
            settings=settings,
            run_id=_start_run(session_factory, kind),
            kind=kind,
            today=today,
            deadline=time.monotonic() + budget_s if budget_s is not None else None,
            start_requests=client.request_count,
        )
        status, message, done = "ok", None, False
        try:
            message, done = body(run)
        except GarminError as exc:
            status, message = "error", str(exc)
        except BaseException as exc:
            _finish_run(run, "error", f"aborted ({type(exc).__name__})")
            raise
        _analytics(run)
        _update_private_values(run)
        if run.budget_hit and status == "ok":
            message = message or "time budget reached; the next backfill continues from here"
        _finish_run(run, status, message)
    log.info(
        "sync %s %s: %d requests, %d rows, %d errors",
        kind,
        status,
        run.requests,
        run.items,
        run.errors,
    )
    return RunSummary(
        run_id=run.run_id,
        kind=kind,
        status=status,
        requests=run.requests,
        items_written=run.items,
        errors=run.errors,
        message=message,
        done=done,
    )


def incremental(
    session_factory: SessionFactory,
    client: GarminClient,
    today: date | None = None,
    *,
    settings: Settings | None = None,
) -> RunSummary:
    """Static datasets, new/changed activities and (newest synced day - 2) .. today."""

    def body(run: _Run) -> tuple[str | None, bool]:
        ok = (
            _sync_static(run, only_missing=False)
            and _sync_activities_incremental(run)
            and _sync_ranges_incremental(run)
            and _sync_daily_incremental(run)
        )
        return (None if ok else "time budget reached"), False

    return _execute(
        "incremental",
        session_factory,
        client,
        today=today,
        settings=settings,
        budget_s=None,
        body=body,
    )


def backfill(
    session_factory: SessionFactory,
    client: GarminClient,
    until: date | None = None,
    budget_s: float | None = None,
    *,
    today: date | None = None,
    settings: Settings | None = None,
) -> RunSummary:
    """Walk back from the oldest synced day to the account's first day (or `until`)."""

    def body(run: _Run) -> tuple[str | None, bool]:
        # A first backfill can take hours of activity downloads; fetch the last few days of
        # every daily/range dataset first so the dashboards show today right away.
        if not (
            _sync_static(run, only_missing=True)
            and _sync_recent_days(run)
            and _backfill_activities(run)
        ):
            return "time budget reached", False
        first = _with_session(run, lambda s: account_first_day(s, run.today))
        floor = max(first, until) if until else first
        can_complete = until is None or until <= first
        if not (
            _backfill_ranges(run, floor, can_complete) and _backfill_daily(run, floor, can_complete)
        ):
            return "time budget reached", False
        done = _with_session(run, _all_complete)
        return (f"backfill reached {floor.isoformat()}" if not done else "backfill complete"), done

    return _execute(
        "backfill",
        session_factory,
        client,
        today=today,
        settings=settings,
        budget_s=budget_s,
        body=body,
    )


def reparse(session: Session, *, today: date) -> RunSummary:
    """Rebuild the typed tables from raw_payload (+ stored activity files); no Garmin calls."""
    ensure_not_demo(session)
    bind = session.get_bind()
    assert isinstance(bind, Engine | Connection)
    errors_before = session.scalar(select(func.count()).select_from(m.SyncError)) or 0
    last_error_id = session.scalar(select(func.max(m.SyncError.id))) or 0
    with run_lock(bind):
        run_id = session.execute(
            insert(m.SyncRun).values(kind="reparse", status="running").returning(m.SyncRun.id)
        ).scalar_one()
        index = session.execute(
            select(m.RawPayload.id, m.RawPayload.dataset, m.RawPayload.key)
        ).all()
        ordered = sorted(
            (r for r in index if r.dataset in DATASETS),
            key=lambda r: (PARSE_ORDER[r.dataset], r.key),
        )
        written = 0
        for row in ordered:
            payload = session.scalar(select(m.RawPayload.payload).where(m.RawPayload.id == row.id))
            written += parse_payload(session, DATASETS[row.dataset], row.key, payload)
        try:
            with session.begin_nested():
                pipeline.run(session, force=True, today=today)
        except Exception as exc:
            _record_error(session, None, "analytics", None, describe(exc))
        # this run's errors only (parse + analytics); older unattributed rows stay as they are
        session.execute(
            update(m.SyncError)
            .where(m.SyncError.run_id.is_(None), m.SyncError.id > last_error_id)
            .values(run_id=run_id)
        )
        errors = (
            session.scalar(select(func.count()).select_from(m.SyncError)) or 0
        ) - errors_before
        session.execute(
            update(m.SyncRun)
            .where(m.SyncRun.id == run_id)
            .values(
                status="ok",
                finished_at=datetime.now(UTC),
                items_written=written,
                message=f"reparsed {len(ordered)} payloads",
            )
        )
        session.commit()
    return RunSummary(
        run_id=int(run_id),
        kind="reparse",
        status="ok",
        requests=0,
        items_written=written,
        errors=int(errors),
        message=f"reparsed {len(ordered)} payloads",
    )


def record_failed_run(session_factory: SessionFactory, kind: str, message: str) -> int:
    """A run that could not start (e.g. expired tokens), so the UI can show why."""
    with session_factory() as s:
        run_id = s.execute(
            insert(m.SyncRun)
            .values(
                kind=kind,
                status="error",
                finished_at=datetime.now(UTC),
                message=message[:500],
            )
            .returning(m.SyncRun.id)
        ).scalar_one()
        s.commit()
    return int(run_id)


# --- entry points for the worker (no CLI) ---------------------------------------------------


def _record_failed_start(session_factory: SessionFactory, kind: str, message: str) -> None:
    """record_failed_run, unless the latest run of this kind already failed the same way.

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
    record_failed_run(session_factory, kind, message)


def _prepare(
    settings: Settings, factory: auth.GarminFactory | None, kind: str
) -> tuple[SessionFactory, GarminClient] | None:
    from garminizer.db.session import session_factory as make_factory  # noqa: PLC0415

    what = f"{kind} sync" if kind == "incremental" else kind
    sf = make_factory(settings.database_url)
    with sf() as s:
        if is_demo(s):
            log.info("%s skipped: the database holds the demo athlete", what)
            return None
    if not auth.has_tokens(settings):
        log.info("%s skipped: not connected to Garmin (no saved tokens)", what)
        return None
    try:
        client = auth.resume(settings, factory)
    except GarminError as exc:
        log.warning("%s skipped: %s", what, exc)
        _record_failed_start(sf, kind, str(exc))  # shown on the Sync page, like API-started runs
        return None
    return sf, client


def run_incremental(
    settings: Settings | None = None, *, factory: auth.GarminFactory | None = None
) -> RunSummary | None:
    """One incremental sync; None (logged) when not connected, demo DB or already running."""
    settings = settings or get_settings()
    prepared = _prepare(settings, factory, "incremental")
    if prepared is None:
        return None
    sf, client = prepared
    try:
        return incremental(sf, client, settings=settings)
    except SyncBusyError as exc:
        log.info("incremental sync skipped: %s", exc)
        return None


def run_backfill_chunk(
    settings: Settings | None = None,
    budget_s: float = 900.0,
    *,
    factory: auth.GarminFactory | None = None,
) -> bool:
    """A time-boxed backfill chunk; True once the backfill is complete.

    Returns False (logged) when it could not run: not connected, demo DB, busy, or an error.
    """
    settings = settings or get_settings()
    from garminizer.db.session import session_factory as make_factory  # noqa: PLC0415

    with make_factory(settings.database_url)() as s:
        if not is_demo(s) and _all_complete(s):
            return True
    prepared = _prepare(settings, factory, "backfill")
    if prepared is None:
        return False
    sf, client = prepared
    try:
        summary = backfill(sf, client, budget_s=budget_s, settings=settings)
    except SyncBusyError as exc:
        log.info("backfill skipped: %s", exc)
        return False
    return summary.done


__all__ = [
    "DEMO_MESSAGE",
    "DemoDatabaseError",
    "RunSummary",
    "SyncBusyError",
    "account_first_day",
    "backfill",
    "describe",
    "ensure_not_demo",
    "incremental",
    "is_demo",
    "is_running",
    "parse_payload",
    "record_failed_run",
    "reparse",
    "run_backfill_chunk",
    "run_incremental",
    "run_lock",
]
