"""Raw payload storage (verbatim, sha256 change detection) and the row-operation writer."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Table, delete, func, insert, literal, null, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.db.bulk import copy_rows, upsert_rows
from garminizer.sync.parsers.common import Patch, Replace, RowOp, Upsert, dedupe

# Large intraday series go through COPY (db.bulk); everything else through INSERT statements.
BULK_MODELS: frozenset[type[Any]] = frozenset(
    {
        m.HrSample,
        m.StressSample,
        m.BodyBatterySample,
        m.RespirationSample,
        m.Spo2Sample,
        m.StepsInterval,
        m.ActivitySample,
    }
)
MAX_PARAMS = 30_000


@dataclass(frozen=True)
class RawState:
    changed: bool
    parsed: bool


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_of(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def is_empty(payload: Any) -> bool:
    return payload is None or payload in ({}, [])


def store_raw(session: Session, dataset: str, key: str, endpoint: str, payload: Any) -> RawState:
    """Upsert one response. Unchanged content keeps parsed_at; changed content resets it."""
    digest = sha256_of(payload)
    now = datetime.now(UTC)
    t = m.RawPayload
    current = session.execute(
        select(t.sha256, t.parsed_at).where(t.dataset == dataset, t.key == key)
    ).first()
    body: Any = null() if payload is None else payload
    if current is None:
        session.execute(
            insert(t).values(
                dataset=dataset,
                key=key,
                endpoint=endpoint,
                fetched_at=now,
                sha256=digest,
                payload=body,
            )
        )
        return RawState(changed=True, parsed=False)
    where = (t.dataset == dataset, t.key == key)
    if current.sha256 == digest:
        session.execute(update(t).where(*where).values(fetched_at=now, endpoint=endpoint))
        return RawState(changed=False, parsed=current.parsed_at is not None)
    session.execute(
        update(t)
        .where(*where)
        .values(
            fetched_at=now,
            endpoint=endpoint,
            sha256=digest,
            payload=body,
            parsed_at=None,
            parse_error=None,
        )
    )
    return RawState(changed=True, parsed=False)


def mark_parsed(session: Session, dataset: str, key: str, error: str | None = None) -> None:
    t = m.RawPayload
    values: dict[str, Any] = (
        {"parsed_at": datetime.now(UTC), "parse_error": None}
        if error is None
        else {"parsed_at": None, "parse_error": error[:500]}
    )
    session.execute(update(t).where(t.dataset == dataset, t.key == key).values(**values))


def apply(session: Session, ops: Sequence[RowOp]) -> int:
    """Write parser output; returns the number of rows written/updated."""
    session.flush()
    written = 0
    for op in ops:
        if isinstance(op, Upsert):
            written += _upsert(session, op)
        elif isinstance(op, Replace):
            written += _replace(session, op)
        else:
            written += _patch(session, op)
    return written


def _table(model: type[Any]) -> Table:
    table = model.__table__
    assert isinstance(table, Table)
    return table


def _normalize(rows: Sequence[dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    cols = list(dict.fromkeys(k for r in rows for k in r))
    return cols, [{c: r.get(c) for c in cols} for r in rows]


def _chunks(rows: list[dict[str, Any]], width: int) -> Iterator[list[dict[str, Any]]]:
    size = max(1, MAX_PARAMS // max(width, 1))
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _upsert(session: Session, op: Upsert) -> int:
    if not op.rows:
        return 0
    cols, rows = _normalize(op.rows)
    rows = dedupe(rows, op.conflict)
    simple = not (op.prefer_new or op.keep_old or op.fill_all)
    if op.model in BULK_MODELS and simple:
        return upsert_rows(
            session, op.model, cols, [tuple(r[c] for c in cols) for r in rows], op.conflict
        )
    table = _table(op.model)
    update_cols = [c for c in cols if c not in op.conflict]
    for chunk in _chunks(rows, len(cols)):
        stmt = pg_insert(table).values(chunk)
        if not update_cols:
            session.execute(stmt.on_conflict_do_nothing(index_elements=list(op.conflict)))
            continue
        set_: dict[str, Any] = {}
        for c in update_cols:
            new, old = stmt.excluded[c], table.c[c]
            if op.fill_all or c in op.keep_old:
                set_[c] = func.coalesce(old, new)
            elif c in op.prefer_new:
                set_[c] = func.coalesce(new, old)
            else:
                set_[c] = new
        session.execute(stmt.on_conflict_do_update(index_elements=list(op.conflict), set_=set_))
    return len(rows)


def _replace(session: Session, op: Replace) -> int:
    table = _table(op.model)
    session.execute(delete(table).where(*(table.c[k] == v for k, v in op.where.items())))
    if not op.rows:
        return 0
    cols, rows = _normalize(op.rows)
    if op.model in BULK_MODELS:
        return copy_rows(session, op.model, cols, [tuple(r[c] for c in cols) for r in rows])
    for chunk in _chunks(rows, len(cols)):
        session.execute(insert(table).values(chunk))
    return len(rows)


def _patch(session: Session, op: Patch) -> int:
    values = {k: v for k, v in op.values.items() if v is not None}
    if not values:
        return 0
    table = _table(op.model)
    set_: dict[str, Any] = {
        c: v if op.overwrite else func.coalesce(table.c[c], literal(v, type_=table.c[c].type))
        for c, v in values.items()
    }
    result = session.execute(
        update(table).where(*(table.c[k] == v for k, v in op.key.items())).values(**set_)
    )
    return int(getattr(result, "rowcount", 0) or 0)
