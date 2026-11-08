"""Fast bulk writes with PostgreSQL COPY (samples, intraday series).

Table and column names come from SQLAlchemy metadata (never from user input) and are quoted.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from typing import Any

from sqlalchemy import Table
from sqlalchemy.orm import Session


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _clean(value: Any) -> Any:
    """COPY adapts Python types; NaN means "no value" here and becomes NULL."""
    if isinstance(value, float) and math.isnan(value):
        return None
    return value


def _table(target: Any) -> Table:
    """Accept a Table or a mapped ORM class."""
    table = target if isinstance(target, Table) else getattr(target, "__table__", None)
    if not isinstance(table, Table):
        raise TypeError(f"not a table or mapped class: {target!r}")
    return table


def _driver_connection(session: Session) -> Any:
    raw = session.connection().connection.driver_connection
    if raw is None:  # pragma: no cover - only with exotic pools
        raise RuntimeError("no DBAPI connection available for COPY")
    return raw


def copy_rows(
    session: Session, target: Any, columns: Sequence[str], rows: Iterable[Sequence[Any]]
) -> int:
    """COPY rows into a Table / mapped class (no conflict handling). Returns rows written."""
    table = _table(target)
    qualified = f"{_quote(table.schema or 'public')}.{_quote(table.name)}"
    cols = ", ".join(_quote(c) for c in columns)
    written = 0
    with (
        _driver_connection(session).cursor() as cur,
        cur.copy(f"COPY {qualified} ({cols}) FROM STDIN") as copy,
    ):
        for row in rows:
            copy.write_row([_clean(v) for v in row])
            written += 1
    return written


def upsert_rows(
    session: Session,
    target: Any,
    columns: Sequence[str],
    rows: Iterable[Sequence[Any]],
    conflict_columns: Sequence[str],
) -> int:
    """COPY into a temp table, then INSERT ... ON CONFLICT DO UPDATE (idempotent bulk upsert)."""
    table = _table(target)
    qualified = f"{_quote(table.schema or 'public')}.{_quote(table.name)}"
    tmp = _quote(f"tmp_{table.name}")
    cols = ", ".join(_quote(c) for c in columns)
    updates = [c for c in columns if c not in conflict_columns]
    if updates:
        action = "DO UPDATE SET " + ", ".join(
            f"{_quote(c)} = EXCLUDED.{_quote(c)}" for c in updates
        )
    else:
        action = "DO NOTHING"
    conflict = ", ".join(_quote(c) for c in conflict_columns)
    create_tmp = f"CREATE TEMP TABLE IF NOT EXISTS {tmp} (LIKE {qualified}) ON COMMIT DROP"
    merge = (
        f"INSERT INTO {qualified} ({cols}) "  # noqa: S608 - identifiers from metadata, quoted
        f"SELECT DISTINCT ON ({conflict}) {cols} FROM {tmp} "
        f"ON CONFLICT ({conflict}) {action}"
    )
    written = 0
    with _driver_connection(session).cursor() as cur:
        cur.execute(create_tmp)
        cur.execute(f"TRUNCATE {tmp}")
        with cur.copy(f"COPY {tmp} ({cols}) FROM STDIN") as copy:
            for row in rows:
                copy.write_row([_clean(v) for v in row])
                written += 1
        cur.execute(merge)
    return written
