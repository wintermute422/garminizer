"""Which days and months a sync asks Garmin for, in which order (pure; no I/O).

The engine executes the plan one unit at a time and stops when its time budget runs out, so
the order matters: day-major, every dataset of a day before the next day, so a cut-off run
leaves whole days behind it rather than one dataset far ahead of the others.

Cursor semantics: ``newest`` is the newest day an incremental sync reached, ``oldest`` the
oldest day a backfill reached (both per dataset, None when never synced).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import date, timedelta

from garminizer.sync.parsers.common import month_bounds

ONE_DAY = timedelta(days=1)


def days_forward(starts: Mapping[str, date], until: date) -> Iterator[tuple[str, date]]:
    """``(dataset, day)`` from each dataset's start day up to ``until``, day by day.

    Datasets keep the order of ``starts`` within a day; a start after ``until`` yields nothing.
    """
    if not starts:
        return
    day = min(starts.values())
    while day <= until:
        for name, first in starts.items():
            if day >= first:
                yield name, day
        day += ONE_DAY


def days_backward(starts: Mapping[str, date], floor: date) -> Iterator[tuple[str, date]]:
    """``(dataset, day)`` from each dataset's start day back to ``floor``, newest day first."""
    if not starts:
        return
    day = max(starts.values())
    while day >= floor:
        for name, first in starts.items():
            if day <= first:
                yield name, day
        day -= ONE_DAY


def incremental_starts(
    names: Sequence[str], newest: Mapping[str, date | None], today: date, overlap_days: int
) -> dict[str, date]:
    """Re-fetch ``overlap_days`` before each dataset's newest day (Garmin revises recent days);
    never synced: the last ``overlap_days`` days. Never after today."""
    overlap = timedelta(days=overlap_days)
    out: dict[str, date] = {}
    for name in names:
        last = newest.get(name)
        out[name] = min(today, last - overlap) if last else today - overlap
    return out


def recent_starts(
    names: Sequence[str], newest: Mapping[str, date | None], today: date, overlap_days: int
) -> dict[str, date]:
    """The last ``overlap_days`` days, skipping days already stored (start after ``newest``).

    A resumed run (or a later backfill chunk on the same day) asks for nothing twice; a start
    after today means the dataset is already up to date.
    """
    floor = today - timedelta(days=overlap_days)
    out: dict[str, date] = {}
    for name in names:
        last = newest.get(name)
        out[name] = floor if last is None else max(floor, last + ONE_DAY)
    return out


def backfill_starts(
    names: Sequence[str], oldest: Mapping[str, date | None], complete: set[str], today: date
) -> dict[str, date]:
    """The day before each dataset's oldest day (today when never backfilled); complete ones
    are left out."""
    return {
        name: (last - ONE_DAY) if (last := oldest.get(name)) else today
        for name in names
        if name not in complete
    }


def months(first: date, last: date) -> list[date]:
    """First days of the months from ``first``'s month to ``last``'s month (empty if reversed)."""
    if first > last:
        return []
    out, cur = [], first.replace(day=1)
    while cur <= last:
        out.append(cur)
        cur = month_bounds(cur)[1] + ONE_DAY
    return out


def months_backward(start: date, floor: date) -> Iterator[date]:
    """First days of months from ``start``'s month back to the month containing ``floor``."""
    month = start.replace(day=1)
    while month_bounds(month)[1] >= floor:
        yield month
        month = (month - ONE_DAY).replace(day=1)


def backfill_month_start(oldest: date | None, today: date) -> date:
    """The month before the oldest backfilled month; this month when never backfilled."""
    if oldest is None:
        return today.replace(day=1)
    return (oldest.replace(day=1) - ONE_DAY).replace(day=1)
