"""Insight cards and correlations through the pure read-model interface (no database)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, timedelta

import numpy as np
import pytest

from garminizer.insights import (
    CARD_METRICS,
    MIN_PAIRS,
    CardActivity,
    CardData,
    DailyGrid,
    InsightCard,
    build_cards,
    correlation_matrix,
    scatter,
)

END = date(2026, 6, 30)  # a Tuesday
DAYS = 120
FIRST = END - timedelta(days=DAYS - 1)


def grid(cols: Mapping[str, list[float] | np.ndarray], first: date = FIRST) -> DailyGrid:
    arrays = {k: np.asarray(v, dtype=float) for k, v in cols.items()}
    size = len(next(iter(arrays.values())))
    for key in CARD_METRICS:
        arrays.setdefault(key, np.full(size, np.nan))
    return DailyGrid(first, size, arrays)


def cards(
    cols: Mapping[str, list[float] | np.ndarray],
    activities: list[CardActivity] | None = None,
    start: date = FIRST,
) -> dict[str, InsightCard]:
    data = CardData(start=start, end=END, grid=grid(cols), activities=activities or [])
    return {c.id: c for c in build_cards(data)}


def flat(value: float, n: int = DAYS) -> np.ndarray:
    return np.full(n, value)


def test_no_data_only_consistency() -> None:
    out = cards({"resting_hr": flat(np.nan)})
    assert list(out) == ["consistency"]  # weeks without activity still count
    assert out["consistency"].text == "You were active in 0 of 18 weeks (0%)."
    assert out["consistency"].sentiment == "bad"


def test_resting_hr_lower_is_good_and_flat_is_neutral() -> None:
    hr = np.concatenate([flat(55.0, DAYS - 30), flat(52.0, 30)])
    card = cards({"resting_hr": hr})["resting_hr_change"]
    assert (card.value, card.delta, card.trend, card.sentiment) == (52.0, -3.0, "down", "good")
    assert "3 bpm lower" in card.text
    steady = cards({"resting_hr": flat(52.0)})["resting_hr_change"]
    assert (steady.trend, steady.sentiment) == ("flat", "neutral")
    sparse = hr.copy()
    sparse[-30:-17] = np.nan  # only 17 of the last 30 days, fine; 13 is not
    sparse[-17:-4] = np.nan
    assert "resting_hr_change" not in cards({"resting_hr": sparse})


def test_hrv_after_hard_days() -> None:
    load = np.where(np.arange(DAYS) % 4 == 0, 300.0, 50.0)
    hrv = np.where(np.roll(load, 1) == 300.0, 40.0, 50.0)  # the night after a hard day
    card = cards({"load": load, "hrv_ms": hrv})["hrv_after_hard_days"]
    assert card.value == 40.0
    assert card.delta == -10.0
    assert card.sentiment == "bad"  # more than 10 % below other days


def test_weekend_sleep() -> None:
    weekday = np.array([(FIRST + timedelta(days=i)).weekday() for i in range(DAYS)])
    sleep = np.where(weekday >= 5, 9 * 3600.0, 7 * 3600.0)
    card = cards({"sleep_s": sleep})["weekend_sleep"]
    assert (card.value, card.delta, card.trend) == (9 * 3600, 2 * 3600, "up")
    assert card.text == "You sleep 2 h longer on weekends (9 h) than on weekdays (7 h)."


def test_fitness_and_vo2max_trends() -> None:
    ctl = np.linspace(40.0, 60.0, DAYS)
    vo2 = flat(np.nan)
    vo2[10], vo2[100] = 50.0, 52.0
    out = cards({"ctl": ctl, "vo2max_running": vo2})
    assert out["fitness_change"].trend == "up"
    assert out["fitness_change"].sentiment == "good"
    assert out["fitness_change"].value == 60.0
    assert (out["vo2max_change"].value, out["vo2max_change"].delta) == (52.0, 2.0)
    assert "rose from 50 to 52" in out["vo2max_change"].text


def test_correlation_cards_need_enough_pairs() -> None:
    rng = np.random.default_rng(1)
    score = rng.normal(75, 8, DAYS)
    out = cards({"sleep_score": score, "readiness": score * 0.9 + 5})
    card = out["sleep_readiness"]
    assert (card.value, card.trend, card.x_metric, card.y_metric, card.lag) == (
        1.0,
        "up",
        "sleep_score",
        "readiness",
        0,
    )
    few = score.copy()
    few[MIN_PAIRS - 1 :] = np.nan
    assert "sleep_readiness" not in cards({"sleep_score": few, "readiness": score})


def test_stress_sleep_uses_the_following_night() -> None:
    rng = np.random.default_rng(2)
    stress = rng.normal(35, 10, DAYS)
    sleep_score = np.empty(DAYS)
    sleep_score[0] = 70.0
    sleep_score[1:] = 100 - stress[:-1]  # night after a stressful day is worse
    card = cards({"avg_stress": stress, "sleep_score": sleep_score})["stress_sleep"]
    assert card.value == -1.0
    assert card.lag == 1


def _act(day: date, hour: int = 7, seconds: float = 3600.0) -> CardActivity:
    return CardActivity(
        start=datetime.combine(day, datetime.min.time()) + timedelta(hours=hour), seconds=seconds
    )


def test_activity_cards() -> None:
    tuesdays = [END - timedelta(days=7 * k) for k in range(12)]  # 12 Tuesdays
    june = [date(2026, 6, d) for d in (27, 28, 29)]  # Sat-Mon, then END (Tue) -> 4-day streak
    acts = sorted(
        [_act(d) for d in tuesdays] + [_act(d, seconds=7200.0) for d in june],
        key=lambda a: a.start,
    )
    out = cards({"ctl": flat(np.nan)}, acts, start=END - timedelta(days=83))
    assert out["training_weekday"].value_label == "Tuesday"
    assert out["training_weekday"].text == "You train most on Tuesdays: 12 of 15 activities (80%)."
    assert out["streak"].value == 4.0
    assert out["streak"].sentiment == "good"
    assert out["most_active_month"].value_label == "June 2026"
    assert out["most_active_month"].value == 5 * 3600 + 3 * 7200
    assert out["consistency"].text == "You were active in 12 of 13 weeks (92%)."
    assert out["consistency"].sentiment == "good"


def test_correlation_matrix_and_scatter() -> None:
    x = np.arange(30, dtype=float)
    g = grid({"steps": x, "sleep_s": np.roll(x, 1), "weight_kg": flat(np.nan, 30)})
    m = correlation_matrix(g, lag=1)
    assert "weight_kg" not in m.metrics  # too few days
    i, j = m.metrics.index("steps"), m.metrics.index("sleep_s")
    assert m.r[i][j] == pytest.approx(1.0)
    assert m.n[i][j] == 29
    s = scatter(g, "steps", "sleep_s", 1)
    assert s.n == 29
    assert s.slope == pytest.approx(1.0)  # y on d + 1 equals x on d
    assert s.intercept == pytest.approx(0.0)
    assert s.points[0].day == FIRST
