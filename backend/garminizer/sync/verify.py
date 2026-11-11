"""Reconcile the database with Garmin (`garminizer verify`) and probe datasets (`probe`).

Output contains counts, relative differences and pass/fail only: no names, ids or coordinates.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.garmin.client import (
    GarminAuthError,
    GarminClient,
    GarminError,
    GarminNotFoundError,
    GarminRateLimitError,
)
from garminizer.sync.datasets import DAILY, FetchContext, Unit
from garminizer.sync.parsers.common import dig, num
from garminizer.sync.store import is_empty

TOLERANCE = 0.01
SAMPLE_ACTIVITIES = 3
STABLE_DAY_LAG = 2


@dataclass(frozen=True)
class Check:
    name: str
    db_value: float | None
    garmin_value: float | None
    show_values: bool
    ok: bool
    note: str = ""

    @property
    def rel_diff(self) -> float | None:
        if self.db_value is None or self.garmin_value is None:
            return None
        if self.garmin_value == 0:
            return 0.0 if self.db_value == 0 else 1.0
        return abs(self.db_value - self.garmin_value) / abs(self.garmin_value)


@dataclass(frozen=True)
class VerifyReport:
    checks: list[Check]

    @property
    def ok(self) -> bool:
        return bool(self.checks) and all(c.ok for c in self.checks)


def _compare(name: str, db: float | None, garmin: float | None, *, show: bool, tol: float) -> Check:
    if db is None or garmin is None:
        return Check(name, db, garmin, show, ok=False, note="missing value")
    rel = Check(name, db, garmin, show, ok=True).rel_diff or 0.0
    return Check(name, db, garmin, show, ok=rel <= tol)


def verify(
    session: Session,
    client: GarminClient,
    *,
    today: date,
    rng: random.Random | None = None,
    tolerance: float = TOLERANCE,
) -> VerifyReport:
    rng = rng or random.Random()  # noqa: S311 - sampling, not crypto
    checks: list[Check] = []

    db_count = session.scalar(select(func.count()).select_from(m.Activity)) or 0
    try:
        garmin_count = num(client.call("count_activities"))
    except GarminError as exc:
        checks.append(Check("activity count", db_count, None, True, False, type(exc).__name__))
    else:
        checks.append(
            Check("activity count", db_count, garmin_count, True, db_count == garmin_count)
        )

    ids = list(session.scalars(select(m.Activity.activity_id).order_by(m.Activity.activity_id)))
    for n, aid in enumerate(rng.sample(ids, min(SAMPLE_ACTIVITIES, len(ids))), start=1):
        stored = session.get(m.Activity, aid)
        assert stored is not None
        try:
            fresh: Any = client.call("get_activity", str(aid))
        except GarminError as exc:
            checks.append(
                Check(f"activity #{n} summary", None, None, False, False, type(exc).__name__)
            )
            continue
        summary = dig(fresh, "summaryDTO") or {}
        checks.append(
            _compare(
                f"activity #{n} distance",
                stored.distance_m,
                num(summary.get("distance")),
                show=False,
                tol=tolerance,
            )
            if stored.distance_m or num(summary.get("distance"))
            else Check(f"activity #{n} distance", 0.0, 0.0, False, True, "no distance")
        )
        checks.append(
            _compare(
                f"activity #{n} duration",
                stored.duration_s,
                num(summary.get("duration")),
                show=False,
                tol=tolerance,
            )
        )

    day = session.scalar(
        select(func.max(m.DailySummary.day)).where(
            m.DailySummary.steps.is_not(None),
            m.DailySummary.day <= today - timedelta(days=STABLE_DAY_LAG),
        )
    )
    if day is None:
        checks.append(Check("daily steps", None, None, True, False, "no synced day with steps"))
    else:
        stored_steps = session.scalar(select(m.DailySummary.steps).where(m.DailySummary.day == day))
        try:
            fresh_day = client.call("get_user_summary", day.isoformat())
        except GarminError as exc:
            checks.append(Check("daily steps", stored_steps, None, True, False, type(exc).__name__))
        else:
            checks.append(
                _compare(
                    f"daily steps ({(today - day).days} days ago)",
                    float(stored_steps) if stored_steps is not None else None,
                    num(dig(fresh_day, "totalSteps")),
                    show=True,
                    tol=0.0,
                )
            )
    return VerifyReport(checks)


def format_report(report: VerifyReport) -> str:
    def fmt(v: float | None, show: bool) -> str:
        if not show:
            return "-"
        return "n/a" if v is None else f"{v:,.0f}"

    lines = [f"{'check':<28} {'database':>12} {'garmin':>12} {'rel diff':>9}  result"]
    for c in report.checks:
        rel = "n/a" if c.rel_diff is None else f"{c.rel_diff:.2%}"
        note = f"  ({c.note})" if c.note else ""
        lines.append(
            f"{c.name:<28} {fmt(c.db_value, c.show_values):>12} "
            f"{fmt(c.garmin_value, c.show_values):>12} {rel:>9}  "
            f"{'PASS' if c.ok else 'FAIL'}{note}"
        )
    lines.append("verdict: " + ("PASS" if report.ok else "FAIL"))
    return "\n".join(lines)


def probe(client: GarminClient, day: date) -> list[tuple[str, str]]:
    """Call every daily dataset once for `day`: dataset → ok | empty | error <type>."""
    ctx = FetchContext(today=day, identity=client.identity)
    out: list[tuple[str, str]] = []
    for ds in DAILY:
        try:
            payload = ds.fetch(client, Unit(day.isoformat(), day=day), ctx)
        except GarminNotFoundError:
            out.append((ds.name, "empty"))
            continue
        except GarminError as exc:
            out.append((ds.name, f"error {type(exc).__name__}"))
            if isinstance(exc, GarminAuthError | GarminRateLimitError):
                break
            continue
        out.append((ds.name, "empty" if is_empty(payload) else "ok"))
    return out
