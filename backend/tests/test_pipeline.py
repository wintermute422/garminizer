"""S3b: the analytics pipeline on stored data is idempotent and internally consistent."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import numpy as np
import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer import models as m
from garminizer.analytics import load, pipeline
from garminizer.db import SCHEMA, migrate
from garminizer.demo.seed import seed_demo
from tests.conftest import create_fresh_database

END = date(2026, 5, 31)
DERIVED = (
    m.ActivityBestEffort,
    m.ActivityBestDistance,
    m.ActivityTrack,
    m.ActivityTile,
    m.ActivitySplit,
    m.ActivityZone,
    m.DailyLoad,
)


@pytest.fixture(scope="module")
def session() -> Iterator[Session]:
    url = create_fresh_database("_pipeline")
    migrate.upgrade(url)
    engine = create_engine(url, poolclass=NullPool)
    with Session(engine) as s:
        seed_demo(s, end=END, days=45, seed=5)
        s.commit()
        yield s
    engine.dispose()


def _counts(s: Session) -> dict[str, int]:
    return {
        t.__tablename__: int(s.scalar(select(func.count()).select_from(t)) or 0) for t in DERIVED
    }


def test_rerun_is_idempotent(session: Session) -> None:
    before = _counts(session)
    assert all(n > 0 for n in before.values()), before
    pipeline.run(session, force=True, today=END)
    assert _counts(session) == before
    pending = pipeline.run(session, today=END)
    assert pending.activities == 0  # nothing left at an older analytics version


def test_zone_time_matches_duration(session: Session) -> None:
    rows = session.execute(
        select(m.Activity.duration_s, func.sum(m.ActivityZone.seconds))
        .join(m.ActivityZone, m.ActivityZone.activity_id == m.Activity.activity_id)
        .where(m.ActivityZone.kind == "hr")
        .group_by(m.Activity.activity_id)
    ).all()
    assert rows
    for duration, zone_total in rows:
        assert zone_total == pytest.approx(duration, rel=0.02)


def test_daily_load_is_continuous_and_matches_pmc(session: Session) -> None:
    rows = session.execute(select(m.DailyLoad).order_by(m.DailyLoad.day)).scalars().all()
    days = [r.day for r in rows]
    assert (days[-1] - days[0]).days + 1 == len(days)
    loads = np.array([r.load for r in rows])
    ctl, atl, _ = load.pmc(loads)
    assert [r.ctl for r in rows] == pytest.approx(ctl.tolist(), abs=0.01)
    assert [r.atl for r in rows] == pytest.approx(atl.tolist(), abs=0.01)
    total = session.scalar(select(func.sum(m.Activity.training_load)))
    assert float(loads.sum()) == pytest.approx(float(total or 0), abs=1.0)


def test_best_distance_never_faster_than_world_class_or_slower_than_activity(
    session: Session,
) -> None:
    rows = session.execute(
        select(
            m.ActivityBestDistance.distance_m, m.ActivityBestDistance.seconds, m.Activity.duration_s
        ).join(m.Activity, m.Activity.activity_id == m.ActivityBestDistance.activity_id)
    ).all()
    assert rows
    for dist, secs, duration in rows:
        assert secs <= (duration or 0) + 1
        assert dist / secs < 6.5  # faster than ~2:34 min/km would be a bug, not a PR


def test_views_agree_with_base_tables(session: Session) -> None:
    weekly = session.execute(text(f"SELECT sum(distance_m) FROM {SCHEMA}.weekly_volume")).scalar()
    total = session.scalar(select(func.sum(m.Activity.distance_m)))
    assert float(weekly or 0) == pytest.approx(float(total or 0))
    n_daily = session.execute(text(f"SELECT count(*) FROM {SCHEMA}.v_daily")).scalar()
    assert n_daily == session.scalar(select(func.count()).select_from(m.DailySummary))
    tiles = session.execute(text(f"SELECT count(*) FROM {SCHEMA}.explorer_tile")).scalar()
    distinct = session.execute(
        text(f"SELECT count(*) FROM (SELECT DISTINCT zoom, x, y FROM {SCHEMA}.activity_tile) t")
    ).scalar()
    assert tiles == distinct
