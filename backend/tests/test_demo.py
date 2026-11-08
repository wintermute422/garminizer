"""S2: the demo generator fills every data table, is deterministic and never touches real data."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from garminizer import models as m
from garminizer.db import SCHEMA, Base, migrate
from garminizer.demo.seed import RealDataError, seed_demo
from tests.conftest import create_fresh_database

END = date(2026, 6, 30)
# Filled later by the sync/analytics pipeline, not by the generator itself.
NOT_SEEDED = {
    "raw_payload",
    "app_setting",
    "activity_file",
    "activity_split",
    "activity_zone",
    "sync_cursor",
    "sync_error",
}


@pytest.fixture(scope="module")
def demo_url() -> str:
    url = create_fresh_database("_demo")
    migrate.upgrade(url)
    return url


@pytest.fixture
def session(demo_url: str) -> Iterator[Session]:
    engine = create_engine(demo_url, poolclass=NullPool)
    with Session(engine) as s:
        yield s
        s.rollback()
    engine.dispose()


def _fingerprint(s: Session) -> tuple[object, ...]:
    return (
        s.scalar(select(func.count()).select_from(m.Activity)),
        s.scalar(select(func.round(func.sum(m.Activity.distance_m)))),
        s.scalar(select(func.count()).select_from(m.ActivitySample)),
        s.scalar(select(func.sum(m.DailySummary.steps))),
        s.scalar(select(func.sum(m.Sleep.score))),
        s.scalar(select(func.sum(m.HrSample.bpm))),
    )


def test_every_data_table_is_filled(session: Session) -> None:
    report = seed_demo(session, end=END, days=60, seed=7)
    session.commit()
    assert report.activities > 30
    empty = [
        t.name
        for t in Base.metadata.sorted_tables
        if t.name not in NOT_SEEDED
        and not session.execute(
            text(f'SELECT EXISTS (SELECT 1 FROM "{SCHEMA}"."{t.name}")')
        ).scalar()
    ]
    assert empty == []
    athlete = session.scalar(select(m.Athlete))
    assert athlete is not None
    assert athlete.is_demo


def test_same_seed_same_data_other_seed_other_data(session: Session) -> None:
    seed_demo(session, end=END, days=30, seed=11)
    first = _fingerprint(session)
    seed_demo(session, end=END, days=30, seed=11)
    assert _fingerprint(session) == first
    seed_demo(session, end=END, days=30, seed=12)
    assert _fingerprint(session) != first


def test_values_are_physiologically_plausible(session: Session) -> None:
    seed_demo(session, end=END, days=60, seed=3)
    low, high = session.execute(
        select(func.min(m.DailySummary.resting_hr), func.max(m.DailySummary.resting_hr))
    ).one()
    assert low is not None
    assert high is not None
    assert 38 <= low <= high <= 70
    deep_share = session.scalar(
        select(func.sum(m.Sleep.deep_s) * 1.0 / func.sum(m.Sleep.duration_s))
    )
    assert deep_share is not None
    assert 0.12 < float(deep_share) < 0.28
    max_hr = session.scalar(select(func.max(m.ActivitySample.hr)))
    assert max_hr is not None
    assert max_hr <= 192


def test_refuses_database_with_real_data(session: Session) -> None:
    seed_demo(session, end=END, days=10, seed=1)
    session.execute(text(f'UPDATE "{SCHEMA}".athlete SET is_demo = false'))
    before = session.scalar(select(func.count()).select_from(m.Activity))
    with pytest.raises(RealDataError):
        seed_demo(session, end=END, days=10, seed=1)
    assert session.scalar(select(func.count()).select_from(m.Activity)) == before
