"""The athlete clock: one fallback rule for every "today" and local day in the app."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.athlete import AthleteClock, athlete_clock, resolve_zone

NOW = datetime(2026, 3, 29, 23, 30, tzinfo=UTC)  # already 30 March in Berlin (CEST)


@pytest.mark.parametrize(
    ("stored", "fallback", "expected"),
    [
        ("Europe/Berlin", "America/New_York", "Europe/Berlin"),  # Garmin's zone wins
        (None, "America/New_York", "America/New_York"),  # else the configured TZ
        ("", "America/New_York", "America/New_York"),
        ("Not/AZone", "America/New_York", "America/New_York"),  # unknown names are skipped
        ("Not/AZone", "Also/Wrong", "UTC"),
        (None, None, "UTC"),
    ],
)
def test_resolve_zone_order(stored: str | None, fallback: str | None, expected: str) -> None:
    assert resolve_zone(stored, fallback).key == expected


def test_clock_days_and_midnights() -> None:
    clock = AthleteClock(resolve_zone("Europe/Berlin"), lambda: NOW)
    assert clock.name == "Europe/Berlin"
    assert clock.today() == date(2026, 3, 30)
    assert clock.now().utcoffset() is not None
    assert clock.local_day(datetime(2026, 3, 29, 22, 30, tzinfo=UTC)) == date(2026, 3, 30)
    # DST starts on 29 March: midnight is 23:00 UTC before, 22:00 UTC after
    assert clock.midnight(date(2026, 3, 29)) == datetime(2026, 3, 28, 23, 0, tzinfo=UTC)
    assert clock.midnight(date(2026, 3, 30)) == datetime(2026, 3, 29, 22, 0, tzinfo=UTC)
    t0, t1 = clock.day_span(date(2026, 3, 29), date(2026, 3, 29))
    assert (t1 - t0).total_seconds() == 23 * 3600  # the short day


def test_athlete_clock_reads_the_stored_zone(db: Session) -> None:
    assert athlete_clock(db, "America/New_York").name == "America/New_York"
    db.add(m.Athlete(id=1, time_zone="Asia/Tokyo", is_demo=False))
    db.flush()
    clock = athlete_clock(db, "America/New_York", now=lambda: NOW)
    assert clock.name == "Asia/Tokyo"
    assert clock.today() == date(2026, 3, 30)
