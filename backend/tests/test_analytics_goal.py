"""Weight goal maths against hand-computed values (synthetic numbers)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from garminizer.analytics import goal as g

D0 = date(2026, 3, 2)  # a Monday


def d(n: int) -> date:
    return D0 + timedelta(days=n)


# --- trend -----------------------------------------------------------------------------------


def test_trend_weights_three_two_one() -> None:
    trend = g.weighted_trend({d(0): 70.0, d(1): 71.0, d(2): 72.0})
    assert trend[d(0)] == 70.0
    assert trend[d(1)] == pytest.approx((71 * 3 + 70 * 2) / 5)
    assert trend[d(2)] == pytest.approx((72 * 3 + 71 * 2 + 70) / 6)


def test_trend_skips_missing_days_and_only_has_weigh_in_days() -> None:
    trend = g.weighted_trend({d(0): 70.0, d(2): 73.0})
    assert set(trend) == {d(0), d(2)}  # no trend on the day without a weigh-in
    assert trend[d(2)] == pytest.approx((73 * 3 + 70 * 1) / 4)  # yesterday missing


def test_trend_custom_weights() -> None:
    trend = g.weighted_trend({d(0): 60.0, d(1): 62.0}, factors=(1.0, 1.0))
    assert trend[d(1)] == pytest.approx(61.0)


# --- target line and checkpoints -------------------------------------------------------------


def plan(**kw: object) -> g.GoalPlan:
    values: dict[str, object] = {
        "start": d(0),
        "start_weight_kg": 70.0,
        "rate_kg_per_week": 0.7,
        "end": d(27),
    }
    values.update(kw)
    return g.GoalPlan(**values)  # type: ignore[arg-type]


def test_checkpoint_days_are_the_weekday_after_the_start_until_the_end() -> None:
    assert g.checkpoint_days(plan()) == [d(6), d(13), d(20), d(27)]  # Sundays
    # a start on the checkpoint weekday itself is not a checkpoint
    assert g.checkpoint_days(plan(start=d(6), end=d(20))) == [d(13), d(20)]
    assert g.checkpoint_days(plan(checkpoint_weekday=0, end=d(14))) == [d(7), d(14)]


def test_line_falls_by_rate_per_week() -> None:
    line = g.goal_line(plan(), {}, today=d(3))
    assert line.target_on(d(-1)) is None
    assert line.target_on(d(0)) == 70.0
    assert line.target_on(d(7)) == pytest.approx(69.3)
    assert line.target_on(d(1)) == pytest.approx(69.9)


def test_trend_below_target_on_checkpoint_restarts_the_line_lower() -> None:
    # target on day 6 = 70 - 0.6 = 69.4; trend 69.0 is below → new anchor 69.0
    line = g.goal_line(plan(), {d(6): 69.0}, today=d(10))
    assert [(a.day, a.weight_kg, a.kind) for a in line.anchors] == [
        (d(0), 70.0, "start"),
        (d(6), 69.0, "reached"),
    ]
    assert line.target_on(d(13)) == pytest.approx(68.3)
    assert line.target_on(d(6)) == pytest.approx(69.4)  # judged against the old line
    assert line.target_on(d(7)) == pytest.approx(68.9)  # the new week starts from the trend
    cp = line.checkpoints[0]
    assert (cp.day, cp.trend_kg, cp.status) == (d(6), 69.0, "reached")
    assert cp.target_kg == pytest.approx(69.4)


def test_trend_above_target_keeps_the_line() -> None:
    line = g.goal_line(plan(), {d(6): 69.8}, today=d(10))
    assert len(line.anchors) == 1
    assert line.checkpoints[0].status == "missed"
    assert line.target_on(d(13)) == pytest.approx(70 - 1.3)


def test_accepted_checkpoint_anchors_at_the_target_not_the_higher_trend() -> None:
    line = g.goal_line(plan(accepted=frozenset({d(6)})), {d(6): 69.8}, today=d(10))
    anchor = line.anchors[-1]
    assert (anchor.day, anchor.kind) == (d(6), "accepted")
    assert anchor.weight_kg == pytest.approx(69.4)
    assert line.checkpoints[0].status == "accepted"
    # min(trend, target) → the line continues exactly where it was
    assert line.target_on(d(13)) == pytest.approx(70 - 1.3)


def test_checkpoint_without_weigh_in_and_upcoming_ones() -> None:
    line = g.goal_line(plan(), {d(5): 69.0}, today=d(13))
    statuses = [(c.day, c.status) for c in line.checkpoints]
    # day 13 is today without a weigh-in yet → upcoming; later ones upcoming too
    assert statuses == [
        (d(6), "no_weigh_in"),
        (d(13), "upcoming"),
        (d(20), "upcoming"),
        (d(27), "upcoming"),
    ]


def test_upcoming_targets_follow_the_latest_anchor() -> None:
    line = g.goal_line(plan(), {d(6): 69.0}, today=d(6))
    assert line.checkpoints[1].target_kg == pytest.approx(68.3)


def test_on_plan_tolerance() -> None:
    assert g.on_plan(70.2, 70.0) is True
    assert g.on_plan(70.21, 70.0) is False
    assert g.on_plan(None, 70.0) is None


# --- body fat --------------------------------------------------------------------------------


def test_ewma_is_time_aware() -> None:
    pts = [(d(0), 20.0), (d(4), 22.0), (d(12), 22.0)]
    out = g.ewma(pts, half_life_days=4)
    assert out[0] == 20.0
    assert out[1] == pytest.approx(21.0)  # one half-life: halfway
    assert out[2] == pytest.approx(21.75)  # two half-lives: 3/4 of the way


def test_regression_slope_window_and_extension() -> None:
    pts = [(d(i), 20.0 - 0.1 * i) for i in range(0, 30, 2)]  # -0.1 per day
    reg = g.regression(pts)
    assert reg is not None
    assert reg.slope_per_week == pytest.approx(-0.7)
    assert reg.start_day == d(8)  # first point within last (28) - 21 days
    assert reg.end_day == d(35)  # 7 days ahead
    assert reg.end_value == pytest.approx(20.0 - 0.1 * 35)
    assert reg.points == 11


def test_regression_needs_four_points() -> None:
    assert g.regression([(d(0), 20.0), (d(1), 20.0), (d(2), 21.0)]) is None
    assert g.regression([]) is None
    assert g.regression([(d(0), 20.0)] * 4) is None  # no spread in time


# --- energy ----------------------------------------------------------------------------------


def test_bmr_formulas() -> None:
    est = g.bmr(80, 180, 40, "male", body_fat_pct=20)
    assert est.mifflin_st_jeor == pytest.approx(800 + 1125 - 200 + 5)
    assert est.harris_benedict == pytest.approx(88.362 + 1071.76 + 863.82 - 227.08)
    assert est.katch_mcardle == pytest.approx(370 + 21.6 * 64)
    assert est.mean == pytest.approx((1730 + 1796.862 + 1752.4) / 3)


def test_bmr_female_without_body_fat() -> None:
    est = g.bmr(60, 165, 30, "female")
    assert est.katch_mcardle is None
    assert est.mifflin_st_jeor == pytest.approx(600 + 1031.25 - 150 - 161)
    assert est.mean == pytest.approx((est.mifflin_st_jeor + est.harris_benedict) / 2)


def test_age_on_birthday() -> None:
    assert g.age_on(date(1990, 6, 15), date(2026, 6, 14)) == 35
    assert g.age_on(date(1990, 6, 15), date(2026, 6, 15)) == 36


def test_active_kcal() -> None:
    assert g.active_kcal(500, 80, 3600, 1800) == 420
    assert g.active_kcal(500, None, 3600, 2400) == pytest.approx(400)  # 100 kcal/h at rest
    assert g.active_kcal(500, None, None, None) == 500
    assert g.active_kcal(50, 80, None, None) == 0
    assert g.active_kcal(None, 80, 60, 1800) is None


def test_target_daily_balance() -> None:
    assert g.target_daily_balance(0.7) == pytest.approx(-770)
