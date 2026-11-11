"""The sync plan: which days and months are requested, in which order (no database)."""

from __future__ import annotations

from datetime import date, timedelta

from garminizer.sync import plan

TODAY = date(2024, 5, 10)
D = timedelta(days=1)


def test_days_forward_is_day_major_in_dataset_order() -> None:
    starts = {"sleep": TODAY - 2 * D, "steps": TODAY - D, "hrv": TODAY + D}
    assert list(plan.days_forward(starts, TODAY)) == [
        ("sleep", TODAY - 2 * D),
        ("sleep", TODAY - D),
        ("steps", TODAY - D),
        ("sleep", TODAY),
        ("steps", TODAY),
    ]
    assert list(plan.days_forward({}, TODAY)) == []


def test_days_backward_walks_each_dataset_down_to_the_floor() -> None:
    starts = {"sleep": TODAY, "steps": TODAY - D}
    assert list(plan.days_backward(starts, TODAY - 2 * D)) == [
        ("sleep", TODAY),
        ("sleep", TODAY - D),
        ("steps", TODAY - D),
        ("sleep", TODAY - 2 * D),
        ("steps", TODAY - 2 * D),
    ]
    assert list(plan.days_backward({"sleep": TODAY - 5 * D}, TODAY - 2 * D)) == []


def test_incremental_starts_overlap_and_never_pass_today() -> None:
    newest = {"sleep": TODAY - 10 * D, "steps": TODAY + 3 * D}
    starts = plan.incremental_starts(["sleep", "steps", "hrv"], newest, TODAY, overlap_days=2)
    assert starts == {"sleep": TODAY - 12 * D, "steps": TODAY, "hrv": TODAY - 2 * D}


def test_recent_starts_skip_days_already_stored() -> None:
    newest = {"sleep": TODAY - D, "steps": TODAY, "hrv": TODAY - 30 * D}
    starts = plan.recent_starts(["sleep", "steps", "hrv", "new"], newest, TODAY, overlap_days=2)
    assert starts == {
        "sleep": TODAY,  # yesterday is stored: only today
        "steps": TODAY + D,  # up to date: nothing to fetch
        "hrv": TODAY - 2 * D,  # old cursor: the overlap window only
        "new": TODAY - 2 * D,
    }
    assert list(plan.days_forward({"steps": starts["steps"]}, TODAY)) == []


def test_backfill_starts_continue_below_the_oldest_day() -> None:
    oldest = {"sleep": TODAY - 30 * D, "steps": TODAY - 3 * D}
    starts = plan.backfill_starts(["sleep", "steps", "hrv"], oldest, {"steps"}, TODAY)
    assert starts == {"sleep": TODAY - 31 * D, "hrv": TODAY}


def test_months() -> None:
    assert plan.months(date(2023, 11, 20), date(2024, 2, 3)) == [
        date(2023, 11, 1),
        date(2023, 12, 1),
        date(2024, 1, 1),
        date(2024, 2, 1),
    ]
    assert plan.months(TODAY + D, TODAY) == []  # start after the end: same month, still empty
    assert list(plan.months_backward(date(2024, 3, 15), date(2024, 1, 31))) == [
        date(2024, 3, 1),
        date(2024, 2, 1),
        date(2024, 1, 1),  # contains the floor
    ]
    assert plan.backfill_month_start(None, TODAY) == date(2024, 5, 1)
    assert plan.backfill_month_start(date(2024, 3, 1), TODAY) == date(2024, 2, 1)
    assert plan.backfill_month_start(date(2024, 1, 20), TODAY) == date(2023, 12, 1)
