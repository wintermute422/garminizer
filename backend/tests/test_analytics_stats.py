"""S3a: day streaks."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from garminizer.analytics.stats import streaks


def _days(start: date, count: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(count)]


# synthetic calendar: Jan 1-5 (5 days), Jan 8-9 (2), Jan 11-12 (2)
DAYS = _days(date(2024, 1, 1), 5) + _days(date(2024, 1, 8), 2) + _days(date(2024, 1, 11), 2)


def test_streak_ending_today_or_yesterday() -> None:
    assert streaks(DAYS, today=date(2024, 1, 12)) == (2, 5, date(2024, 1, 1))
    assert streaks(DAYS, today=date(2024, 1, 13)) == (2, 5, date(2024, 1, 1))  # yesterday
    assert streaks(DAYS, today=date(2024, 1, 14)) == (0, 5, date(2024, 1, 1))
    assert streaks(DAYS, today=date(2024, 1, 4)) == (4, 5, date(2024, 1, 1))


def test_duplicates_and_order_are_ignored() -> None:
    shuffled = list(reversed(DAYS)) + DAYS[:3] + [datetime(2024, 1, 12, 18, 30)]
    assert streaks(shuffled, today=date(2024, 1, 12)) == (2, 5, date(2024, 1, 1))


def test_tie_reports_the_earliest_longest_streak() -> None:
    days = _days(date(2024, 3, 1), 3) + _days(date(2024, 3, 10), 3)
    assert streaks(days, today=date(2024, 3, 12)) == (3, 3, date(2024, 3, 1))
    later_longer = _days(date(2024, 3, 1), 2) + _days(date(2024, 3, 10), 4)
    assert streaks(later_longer, today=date(2024, 5, 1)) == (0, 4, date(2024, 3, 10))


def test_streak_edge_cases() -> None:
    assert streaks([], today=date(2024, 1, 1)) == (0, 0, None)
    assert streaks([date(2024, 2, 29)], today=date(2024, 2, 29)) == (1, 1, date(2024, 2, 29))
    # across a month and year boundary
    days = _days(date(2023, 12, 30), 4)
    assert streaks(days, today=date(2024, 1, 2)) == (4, 4, date(2023, 12, 30))
    # default "today" is the real current date
    assert streaks([date.today()]) == (1, 1, date.today())
