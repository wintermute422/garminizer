"""Row operations produced by the parsers, the parse context and defensive value helpers.

Parsers never raise on missing keys or None values (those become NULL). An unexpected *shape*
(e.g. a list where an object is required) raises ShapeError, whose message names the field but
never contains payload values.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from garminizer.db.base import Base

SMALLINT_MIN, SMALLINT_MAX = -32768, 32767
_MS_THRESHOLD = 100_000_000_000  # epoch values above this are milliseconds
_TZ_SUFFIX = re.compile(r"([+-]\d{2}):?(\d{2})$")


class ShapeError(ValueError):
    """The response does not have the expected structure (message without values)."""


@dataclass(frozen=True)
class Upsert:
    """INSERT ... ON CONFLICT (conflict) DO UPDATE the given columns.

    `prefer_new` columns keep the stored value when the new one is NULL; `keep_old` columns
    only fill a stored NULL (a secondary source that must not override the primary one).
    """

    model: type[Base]
    rows: list[dict[str, Any]]
    conflict: tuple[str, ...]
    prefer_new: frozenset[str] = frozenset()
    keep_old: frozenset[str] = frozenset()
    fill_all: bool = False


@dataclass(frozen=True)
class Replace:
    """DELETE every row matching `where` (column = value), then insert `rows`."""

    model: type[Base]
    where: dict[str, Any]
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class Patch:
    """UPDATE one existing row (never inserts); None values are skipped.

    overwrite=False only fills columns that are NULL in the stored row.
    """

    model: type[Base]
    key: dict[str, Any]
    values: dict[str, Any]
    overwrite: bool = False


RowOp = Upsert | Replace | Patch


@dataclass(frozen=True)
class ParseContext:
    dataset: str
    key: str
    fetched_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def day(self) -> date | None:
        return day_of(self.key)

    @property
    def activity_id(self) -> int | None:
        return int(self.key) if self.key.isdigit() else None

    def require_day(self) -> date:
        d = self.day
        if d is None:
            raise ShapeError(f"{self.dataset}: key is not a date")
        return d

    def require_activity_id(self) -> int:
        aid = self.activity_id
        if aid is None:
            raise ShapeError(f"{self.dataset}: key is not an activity id")
        return aid


Parser = Callable[[Any, ParseContext], list[RowOp]]


# --- value helpers -------------------------------------------------------------------------


def num(value: Any) -> float | None:
    """A finite float, or None (bools, NaN, non-numeric strings and containers → None)."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
    elif isinstance(value, str):
        try:
            f = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    return f if math.isfinite(f) else None


def rnd(value: Any, ndigits: int = 2) -> float | None:
    f = num(value)
    return None if f is None else round(f, ndigits)


def integer(value: Any) -> int | None:
    f = num(value)
    return None if f is None else round(f)


def small(value: Any) -> int | None:
    """An int that fits a SMALLINT column, else None."""
    i = integer(value)
    return i if i is not None and SMALLINT_MIN <= i <= SMALLINT_MAX else None


def positive(value: Any) -> float | None:
    f = num(value)
    return f if f is not None and f > 0 else None


def non_negative_small(value: Any) -> int | None:
    """Garmin uses -1/-2 as "no value" markers in many daily aggregates."""
    i = small(value)
    return i if i is not None and i >= 0 else None


def text(value: Any) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if isinstance(value, int | float) and not isinstance(value, bool):
        return str(value)
    return None


def flag(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def first(data: Mapping[str, Any] | None, *keys: str) -> Any:
    """The first non-None value among the given keys."""
    if not isinstance(data, Mapping):
        return None
    for k in keys:
        v = data.get(k)
        if v is not None:
            return v
    return None


def dig(data: Any, *path: str) -> Any:
    """Nested lookup; None as soon as a level is missing or not an object."""
    cur = data
    for k in path:
        if not isinstance(cur, Mapping):
            return None
        cur = cur.get(k)
    return cur


def obj(value: Any, what: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ShapeError(f"{what}: expected an object")
    return value


def obj_or_empty(value: Any, what: str) -> dict[str, Any]:
    if value is None:
        return {}
    return obj(value, what)


def items(value: Any, what: str) -> list[Any]:
    """A list (None → empty); anything else is a shape error."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ShapeError(f"{what}: expected a list")
    return value


def dicts(value: Any, what: str) -> list[dict[str, Any]]:
    return [v for v in items(value, what) if isinstance(v, dict)]


def ts_utc(value: Any) -> datetime | None:
    """Garmin GMT timestamps (epoch s/ms, 'YYYY-MM-DD HH:MM:SS', ISO with .0/Z/+0000) → UTC."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        f = float(value)
        if not math.isfinite(f) or f <= 0:
            return None
        seconds = f / 1000.0 if abs(f) >= _MS_THRESHOLD else f
        try:
            return datetime.fromtimestamp(seconds, UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    if s.isdigit():
        return ts_utc(int(s))
    s = s.replace(" ", "T", 1)
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    m = _TZ_SUFFIX.search(s)
    if m and ":" not in s[m.start() :]:
        s = s[: m.start()] + f"{m.group(1)}:{m.group(2)}"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def ts_local(value: Any) -> datetime | None:
    """A local wall-clock timestamp (naive). Epoch values are read as wall-clock seconds."""
    if isinstance(value, str):
        s = value.strip().replace(" ", "T", 1)
        try:
            parsed = datetime.fromisoformat(s.rstrip("Zz"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=None)
    utc = ts_utc(value)
    return utc.replace(tzinfo=None) if utc else None


def day_of(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    if isinstance(value, int | float) and not isinstance(value, bool):
        dt = ts_utc(value)
        return dt.date() if dt else None
    return None


def index_of(descriptors: Any, name: str, *, key_field: str, index_field: str) -> int | None:
    """Position of `name` in Garmin's `...ValueDescriptors` lists."""
    for d in dicts(descriptors, "value descriptors"):
        if d.get(key_field) == name and isinstance(d.get(index_field), int):
            return int(d[index_field])
    return None


def series(
    values: Any,
    descriptors: Any,
    value_name: str,
    *,
    key_field: str = "key",
    index_field: str = "index",
    default_index: int = 1,
) -> list[tuple[datetime, float]]:
    """[[epoch_ms, value, ...], ...] → [(utc, value)] using the descriptor list when present."""
    ts_i = index_of(descriptors, "timestamp", key_field=key_field, index_field=index_field)
    v_i = index_of(descriptors, value_name, key_field=key_field, index_field=index_field)
    ts_i = 0 if ts_i is None else ts_i
    v_i = default_index if v_i is None else v_i
    out: dict[datetime, float] = {}
    for row in items(values, f"{value_name} values"):
        if not isinstance(row, list | tuple) or len(row) <= max(ts_i, v_i):
            continue
        t = ts_utc(row[ts_i])
        v = num(row[v_i])
        if t is not None and v is not None:
            out[t] = v
    return sorted(out.items())


def dedupe(rows: Iterable[dict[str, Any]], key: Sequence[str]) -> list[dict[str, Any]]:
    """Keep the last row per key (ON CONFLICT cannot touch a row twice in one statement)."""
    out: dict[tuple[Any, ...], dict[str, Any]] = {}
    for r in rows:
        out[tuple(r[k] for k in key)] = r
    return list(out.values())


def has_values(row: Mapping[str, Any], *, ignore: Iterable[str] = ()) -> bool:
    skip = set(ignore)
    return any(v is not None for k, v in row.items() if k not in skip)


def f_to_c(value: Any) -> float | None:
    f = num(value)
    return None if f is None else round((f - 32.0) * 5.0 / 9.0, 1)


def mph_to_mps(value: Any) -> float | None:
    f = num(value)
    return None if f is None else round(f * 0.44704, 2)


def grams_to_kg(value: Any, *, threshold: float = 500.0) -> float | None:
    """Garmin sends body weights in grams; values below the threshold are taken as kg."""
    f = num(value)
    if f is None or f <= 0:
        return None
    return round(f / 1000.0, 2) if f > threshold else round(f, 2)


def month_bounds(day: date) -> tuple[date, date]:
    start = day.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1)
