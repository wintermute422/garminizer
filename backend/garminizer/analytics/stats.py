"""Small statistics over calendar days: activity streaks."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from itertools import pairwise

ONE_DAY = timedelta(days=1)


def streaks(days: Iterable[date], today: date | None = None) -> tuple[int, int, date | None]:
    """``(current, longest, start of longest)`` streaks of consecutive days.

    The current streak is the run ending today, or yesterday when today has no entry yet
    (0 otherwise). Duplicates are ignored; datetimes count as their date. On a tie the
    earliest longest streak is reported. ``today`` defaults to ``date.today()``.
    """
    unique = sorted({d.date() if isinstance(d, datetime) else d for d in days})
    if not unique:
        return 0, 0, None

    longest, longest_start = 1, unique[0]
    run, run_start = 1, unique[0]
    for prev, cur in pairwise(unique):
        if cur - prev == ONE_DAY:
            run += 1
        else:
            run, run_start = 1, cur
        if run > longest:
            longest, longest_start = run, run_start

    present = set(unique)
    ref = today if today is not None else date.today()
    if isinstance(ref, datetime):
        ref = ref.date()
    if ref not in present:
        ref -= ONE_DAY
    current = 0
    while ref in present:
        current += 1
        ref -= ONE_DAY
    return current, longest, longest_start
