"""A4 (idempotent sync/reparse) and A5 (backoff, crash + resume, demo refusal) for the engine.

Runs against a real (throwaway) Postgres database with the FakeGarmin; never networked.
"""

from __future__ import annotations

import os
from collections import Counter
from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path
from random import Random
from typing import Any

import pytest
from garminconnect import GarminConnectConnectionError
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from garminizer import models as m
from garminizer.config import Settings
from garminizer.db import SCHEMA, Base, migrate
from garminizer.garmin import auth
from garminizer.garmin.client import GarminClient
from garminizer.sync import engine, private_values, verify
from garminizer.sync.datasets import DAILY, DETAIL, RANGE, STATIC
from tests.conftest import create_fresh_database
from tests.garmin_fake import Crash, FakeGarmin, factory_for

TODAY = date(2024, 5, 10)
BOOKKEEPING = {"sync_run", "sync_error", "sync_cursor", "app_setting"}


@pytest.fixture(scope="module")
def sync_url() -> str:
    url = create_fresh_database("_sync")
    migrate.upgrade(url)
    return url


@pytest.fixture
def bind(sync_url: str) -> Iterator[Engine]:
    eng = create_engine(sync_url, poolclass=NullPool)
    with eng.begin() as conn:
        names = ", ".join(f'"{SCHEMA}"."{t.name}"' for t in Base.metadata.sorted_tables)
        conn.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    yield eng
    eng.dispose()


@pytest.fixture
def sf(bind: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind, expire_on_commit=False)


@pytest.fixture
def settings(tmp_path: Path, sync_url: str) -> Settings:
    return Settings(
        database_url=sync_url, data_dir=tmp_path / "data", sync_request_delay_s=0, _env_file=None
    )


def client_for(fake: FakeGarmin, **kwargs: Any) -> GarminClient:
    return GarminClient(fake, delay_s=0, sleep=lambda _s: None, **kwargs)


def counts(sf: sessionmaker[Session]) -> dict[str, int]:
    with sf() as s:
        return {
            t.name: int(s.scalar(select(func.count()).select_from(t)) or 0)
            for t in Base.metadata.sorted_tables
            if t.name not in BOOKKEEPING
        }


def scalar(sf: sessionmaker[Session], sql: str) -> Any:
    with sf() as s:
        return s.scalar(text(sql))


# --- incremental ----------------------------------------------------------------------------


def test_incremental_sync_fills_every_table_and_is_idempotent(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    fake = FakeGarmin(n_activities=3, last_activity_day=TODAY, first_day=TODAY - timedelta(days=30))
    summary = engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    assert (summary.status, summary.errors) == ("ok", 0), summary
    assert summary.requests == len(fake.calls)
    assert summary.items_written > 0

    with sf() as s:
        athlete = s.get(m.Athlete, 1)
        assert athlete is not None and not athlete.is_demo
        assert (athlete.display_name, athlete.profile_id) == ("demo-athlete", 1234567890)
        assert (athlete.time_zone, athlete.max_hr, athlete.weight_kg) == ("Europe/Rome", 188, 72.5)
        run = s.get(m.Activity, 1234567890)
        ride = s.get(m.Activity, 1234567891)
        assert run is not None and ride is not None
        assert run.has_samples and not ride.has_samples  # the ride's original is a GPX
        assert run.avg_temperature_c == 18.5  # filled in from the summary details
        assert run.analytics_version == 1  # analytics pipeline ran
        assert s.get(m.ActivityTrack, 1234567890) is not None
        gear = s.get(m.Gear, "0a1b2c3d4e5f60718293a4b5c6d7e8f9")
        assert gear is not None and gear.total_distance_m == 412345.0
        day = s.get(m.DailySummary, TODAY)
        assert day is not None and day.steps == 12450 and day.avg_spo2 == 95.0
        assert day.hydration_ml == 1800.0
        assert s.scalar(select(func.count()).select_from(m.SyncError)) == 0
        assert s.scalar(select(func.count()).where(m.RawPayload.parse_error.is_not(None))) == 0
        sync_run = s.scalar(select(m.SyncRun))
        assert sync_run is not None and sync_run.status == "ok" and sync_run.finished_at is not None

    first = counts(sf)
    assert first["activity"] == 3
    assert first["activity_sample"] == 400
    assert first["activity_lap"] == 6
    assert first["activity_gear"] == 3
    assert first["daily_summary"] == 3  # today - 2 .. today
    assert first["sleep_stage"] == 18
    assert first["hr_sample"] == 12
    assert first["body_composition"] == 1
    assert [name for name, n in first.items() if n == 0] == []

    again = engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    assert again.status == "ok"
    assert counts(sf) == first
    with sf() as s:
        reparsed = engine.reparse(s, today=TODAY)
    assert reparsed.status == "ok"
    assert counts(sf) == first
    assert scalar(sf, "SELECT count(*) FROM garmin.sync_run") == 3


def test_typed_tables_are_rebuilt_from_raw_payloads(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    fake = FakeGarmin(n_activities=2, last_activity_day=TODAY)
    engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    before = counts(sf)
    with sf() as s:
        s.execute(text("DELETE FROM garmin.daily_summary"))
        s.execute(text("DELETE FROM garmin.sleep"))
        s.execute(text("DELETE FROM garmin.activity_sample"))
        s.execute(text("UPDATE garmin.activity SET has_samples = false"))
        s.commit()
    calls = len(fake.calls)
    with sf() as s:
        engine.reparse(s, today=TODAY)
    assert len(fake.calls) == calls  # no Garmin requests
    assert counts(sf) == before
    assert scalar(sf, "SELECT bool_or(has_samples) FROM garmin.activity") is True


def test_private_values_file(sf: sessionmaker[Session], settings: Settings) -> None:
    fake = FakeGarmin(n_activities=2, last_activity_day=TODAY)
    engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    path = settings.data_dir / private_values.FILE_NAME
    lines = path.read_text(encoding="utf-8").splitlines()
    assert {"demo-athlete", "Demo Athlete", "1234567890"} <= set(lines)
    assert {"45.001", "7.002"} <= set(lines)  # rounded most frequent start
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600
    with sf() as s:  # e-mail (when Garmin sends one) is added too
        s.execute(
            text(
                "UPDATE garmin.raw_payload SET payload = jsonb_set(payload, '{userInfo,email}', "
                ":v) WHERE dataset = 'personal_information'"
            ),
            {"v": '"' + "@".join(("someone", "example.org")) + '"'},
        )
        private_values.update(s, settings.data_dir)
    assert "@".join(("someone", "example.org")) in path.read_text(encoding="utf-8")
    assert "demo-athlete" in path.read_text(encoding="utf-8")


# --- backfill ------------------------------------------------------------------------------


EXPECTED_UNITS = {
    "static": 14 + 1,  # 14 requests + identity
    "activity": 5,
    "detail": 5 * len(DETAIL),
    "daily": 7 * len(DAILY),  # first day = today - 6
    "range": len(RANGE),  # May only
}


def _backfill_fake() -> FakeGarmin:
    return FakeGarmin(
        n_activities=5,
        last_activity_day=TODAY - timedelta(days=1),
        first_day=TODAY - timedelta(days=6),
    )


def _assert_backfill_complete(sf: sessionmaker[Session]) -> None:
    with sf() as s:
        cursors = {c.dataset: c for c in s.scalars(select(m.SyncCursor))}
        names = [d.name for d in (*STATIC, *DAILY, *RANGE)] + ["activity"]
        assert all(cursors[n].complete for n in names), [
            n for n in names if not cursors[n].complete
        ]
        assert cursors["sleep"].oldest_day == TODAY - timedelta(days=6)
        assert s.scalar(select(func.count()).select_from(m.RawPayload)) == sum(
            EXPECTED_UNITS.values()
        )
        days = list(s.scalars(select(m.DailySummary.day).order_by(m.DailySummary.day)))
        assert days == [TODAY - timedelta(days=6 - i) for i in range(7)]
    c = counts(sf)
    assert c["activity"] == 5
    assert c["activity_weather"] == 5


def test_backfill_walks_back_to_the_first_day(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    fake = _backfill_fake()
    summary = engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    assert (summary.status, summary.done, summary.errors) == ("ok", True, 0), summary
    _assert_backfill_complete(sf)
    calls = len(fake.calls)
    again = engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    assert again.done
    assert len(fake.calls) == calls  # a complete backfill requests nothing


@pytest.mark.parametrize("crash_after", [30, 80, 140])
def test_crash_mid_backfill_resumes_without_duplicates(
    sf: sessionmaker[Session], settings: Settings, crash_after: int
) -> None:
    fake = _backfill_fake()
    fake.crash_after = crash_after
    with pytest.raises(Crash):
        engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    with sf() as s:
        crashed = s.scalar(select(m.SyncRun))
        assert crashed is not None and crashed.status == "error"
        assert crashed.message == "aborted (Crash)"
    fake.crash_after = None
    summary = engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    assert (summary.status, summary.done) == ("ok", True), summary
    _assert_backfill_complete(sf)
    per_unit = Counter((name, args) for name, args in fake.calls if name not in {"get_activities"})
    repeated = {k: n for k, n in per_unit.items() if n > 1}
    assert len(repeated) <= 1 and all(n == 2 for n in repeated.values()), repeated


def test_transient_failures_abort_the_run_and_the_next_run_resumes(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    fake = _backfill_fake()
    network = GarminConnectConnectionError("Request failed")
    network.__cause__ = ConnectionResetError()
    fake.fail_with["get_sleep_data"] = [network] * 3
    summary = engine.backfill(sf, client_for(fake, max_retries=2), today=TODAY, settings=settings)
    assert summary.status == "error"
    assert summary.message is not None and "get_sleep_data" in summary.message
    assert not summary.done
    summary = engine.backfill(sf, client_for(fake, max_retries=2), today=TODAY, settings=settings)
    assert (summary.status, summary.done) == ("ok", True)
    _assert_backfill_complete(sf)


def test_rejected_requests_are_recorded_and_skipped(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    fake = FakeGarmin(n_activities=2, last_activity_day=TODAY)
    fake.fail_with["get_hrv_data"] = [GarminConnectConnectionError("API Error 400 - bad request")]
    summary = engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    assert (summary.status, summary.errors) == ("ok", 1)
    with sf() as s:
        err = s.scalar(select(m.SyncError))
        assert err is not None and err.dataset == "hrv" and "400" in err.error
        assert s.scalar(select(func.count()).select_from(m.HrvDaily)) == 2  # the other two days


def test_the_budget_stops_a_backfill_cleanly(sf: sessionmaker[Session], settings: Settings) -> None:
    fake = _backfill_fake()
    summary = engine.backfill(sf, client_for(fake), budget_s=0.0, today=TODAY, settings=settings)
    assert (summary.status, summary.done) == ("ok", False)
    assert summary.message is not None and "budget" in summary.message
    summary = engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    assert summary.done


# --- guards --------------------------------------------------------------------------------


def test_refuses_a_demo_database(sf: sessionmaker[Session], settings: Settings) -> None:
    with sf() as s:
        s.add(m.Athlete(id=1, display_name="Demo Athlete", is_demo=True))
        s.commit()
    fake = FakeGarmin()
    with pytest.raises(engine.DemoDatabaseError, match="separate database"):
        engine.incremental(sf, client_for(fake), TODAY, settings=settings)
    with pytest.raises(engine.DemoDatabaseError):
        engine.backfill(sf, client_for(fake), today=TODAY, settings=settings)
    with sf() as s, pytest.raises(engine.DemoDatabaseError):
        engine.reparse(s)
    assert fake.calls == []
    assert scalar(sf, "SELECT count(*) FROM garmin.sync_run") == 0


def test_only_one_run_at_a_time_across_processes(
    sf: sessionmaker[Session], bind: Engine, settings: Settings
) -> None:
    other = bind.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:  # another "process" holds the advisory lock
        assert other.execute(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": engine.ADVISORY_LOCK_KEY}
        ).scalar()
        with sf() as s:
            assert engine.is_running(s)
        with pytest.raises(engine.SyncBusyError):
            engine.incremental(sf, client_for(FakeGarmin()), TODAY, settings=settings)
        other.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": engine.ADVISORY_LOCK_KEY})
    finally:
        other.close()
    with sf() as s:
        assert not engine.is_running(s)
    with engine.run_lock(bind):
        with sf() as s:
            assert engine.is_running(s)
        with pytest.raises(engine.SyncBusyError):
            engine.incremental(sf, client_for(FakeGarmin()), TODAY, settings=settings)
    with sf() as s:
        assert not engine.is_running(s)


def test_worker_entry_points_are_no_ops_when_not_possible(
    sf: sessionmaker[Session], settings: Settings
) -> None:
    factory = factory_for()
    assert engine.run_incremental(settings, factory=factory) is None  # not connected
    assert engine.run_backfill_chunk(settings, 1.0, factory=factory) is False
    auth.ensure_token_dir(settings)
    auth.token_file(settings).write_text(
        '{"di_token": "a", "di_refresh_token": "b"}', encoding="utf-8"
    )
    assert engine.run_backfill_chunk(settings, 0.0, factory=factory) is False  # budget
    with sf() as s:
        run = s.scalar(select(m.SyncRun).order_by(m.SyncRun.id.desc()))
        assert run is not None and run.kind == "backfill" and run.status == "ok"
        s.execute(
            text(
                "INSERT INTO garmin.athlete (id, is_demo) VALUES (1, true) "
                "ON CONFLICT (id) DO UPDATE SET is_demo = true"
            )
        )
        s.commit()
    assert engine.run_incremental(settings, factory=factory) is None  # demo DB
    assert engine.run_backfill_chunk(settings, 1.0, factory=factory) is False


# --- verify and probe ----------------------------------------------------------------------


def test_verify_and_probe(sf: sessionmaker[Session], settings: Settings) -> None:
    fake = FakeGarmin(n_activities=3, last_activity_day=TODAY)
    client = client_for(fake)
    engine.incremental(sf, client, TODAY, settings=settings)
    with sf() as s:
        report = verify.verify(s, client, today=TODAY, rng=Random(1))
    assert report.ok, verify.format_report(report)
    assert [c.name for c in report.checks][:1] == ["activity count"]
    assert len(report.checks) == 1 + 3 * 2 + 1
    text_report = verify.format_report(report)
    for private in ("demo-athlete", "Demo Athlete", "45.00", "1234567890", "Morning"):
        assert private not in text_report
    with sf() as s:
        s.execute(text("UPDATE garmin.activity SET distance_m = distance_m * 1.5"))
        s.commit()
        assert not verify.verify(s, client, today=TODAY, rng=Random(1)).ok
    results = dict(verify.probe(client, TODAY - timedelta(days=1)))
    assert set(results) == {d.name for d in DAILY}
    assert set(results.values()) == {"ok"}
