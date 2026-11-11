"""The athlete's clock: which time zone "today" and local days are counted in.

One rule for the whole app (API, MCP, sync, analytics): the IANA zone Garmin stores for the
athlete (``garmin.athlete.time_zone``), else the configured ``TZ`` (settings.tz), else UTC.
Unknown zone names are skipped, never raised.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from garminizer import models as m

Now = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


def resolve_zone(*candidates: str | None) -> ZoneInfo:
    """The first valid IANA zone among ``candidates``; UTC when none is."""
    for name in candidates:
        if not name:
            continue
        try:
            return ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            continue
    return ZoneInfo("UTC")


@dataclass(frozen=True)
class AthleteClock:
    """A time zone plus a source of "now" (injectable for tests)."""

    zone: ZoneInfo
    now_utc: Now = field(default=_utc_now, compare=False)

    @property
    def name(self) -> str:
        """IANA name, for SQL ``AT TIME ZONE :tz``."""
        return self.zone.key

    def now(self) -> datetime:
        """Aware "now" in the athlete's zone."""
        return self.now_utc().astimezone(self.zone)

    def today(self) -> date:
        return self.now().date()

    def local_day(self, ts: datetime) -> date:
        """The athlete's calendar day of an aware timestamp."""
        return ts.astimezone(self.zone).date()

    def midnight(self, day: date) -> datetime:
        """00:00 of ``day`` in the athlete's zone, as an aware UTC datetime."""
        return datetime.combine(day, time(), self.zone).astimezone(UTC)

    def day_span(self, start: date, end: date) -> tuple[datetime, datetime]:
        """``[00:00 of start, 00:00 after end)`` in UTC: the instants of local days start..end."""
        return self.midnight(start), self.midnight(end + timedelta(days=1))


def stored_zone(session: Session) -> str | None:
    return session.scalar(select(m.Athlete.time_zone).order_by(m.Athlete.id).limit(1))


def athlete_clock(
    session: Session, fallback: str | None, *, now: Now | None = None
) -> AthleteClock:
    """The clock for the athlete in this database; ``fallback`` is the configured TZ."""
    return AthleteClock(resolve_zone(stored_zone(session), fallback), now or _utc_now)
