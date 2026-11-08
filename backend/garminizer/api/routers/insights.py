"""Insights: correlations between daily metrics, scatter plots, weekday patterns and cards.

All daily metrics come from the ``v_daily`` view. Sleep is keyed by the wake-up day, so the
sleep of day d is the night *before* d (and is followed by the readiness score of d).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any, Literal

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session

from garminizer.analytics import FloatArray
from garminizer.analytics.series import linear_trend, pearson
from garminizer.analytics.stats import streaks
from garminizer.api.deps import RangeDep, SessionDep, data_bounds, rows
from garminizer.api.schemas import Model

router = APIRouter(prefix="/api/insights", tags=["insights"])

Trend = Literal["up", "down", "flat"]
Sentiment = Literal["good", "bad", "neutral"]
LagQuery = Annotated[
    int, Query(ge=0, le=7, description="Days between x and y: x on day d, y on day d + lag")
]

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
MIN_PAIRS = 14  # fewest days before a correlation card is shown


class InsightMetric(Model):
    key: str
    label: str
    unit: str
    higher_is_better: bool | None


def _metric(key: str, label: str, unit: str, higher_is_better: bool | None) -> InsightMetric:
    return InsightMetric(key=key, label=label, unit=unit, higher_is_better=higher_is_better)


METRICS: tuple[InsightMetric, ...] = (
    _metric("steps", "Steps", "steps", True),
    _metric("resting_hr", "Resting heart rate", "bpm", False),
    _metric("avg_stress", "Average stress", "score", False),
    _metric("body_battery_high", "Body Battery high", "score", True),
    _metric("body_battery_at_wake", "Body Battery at wake", "score", True),
    _metric("sleep_s", "Sleep duration", "s", True),
    _metric("sleep_deep_s", "Deep sleep", "s", True),
    _metric("sleep_rem_s", "REM sleep", "s", True),
    _metric("sleep_score", "Sleep score", "score", True),
    _metric("hrv_ms", "Overnight HRV", "ms", True),
    _metric("readiness", "Training readiness", "score", True),
    _metric("load", "Training load", "load", None),
    _metric("ctl", "Fitness (CTL)", "load", True),
    _metric("atl", "Fatigue (ATL)", "load", None),
    _metric("tsb", "Form (TSB)", "load", None),
    _metric("vo2max_running", "VO2max (running)", "ml/kg/min", True),
    _metric("weight_kg", "Weight", "kg", None),
    _metric("active_kcal", "Active calories", "kcal", None),
    _metric("vigorous_intensity_min", "Vigorous intensity minutes", "min", True),
)
METRIC_KEYS = tuple(m.key for m in METRICS)
WEEKDAY_COLUMNS = ("sleep_s", "steps", "avg_stress", "hrv_ms", "load", "readiness")


class InsightCorrelations(Model):
    """``r[i][j]`` correlates ``metrics[i]`` on day d with ``metrics[j]`` on day d + lag."""

    lag: int
    metrics: list[str]
    r: list[list[float | None]]
    n: list[list[int]]


class InsightScatterPoint(Model):
    day: date
    x: float
    y: float


class InsightScatter(Model):
    """Pairs of x on ``day`` and y on ``day + lag``, with Pearson r and a least-squares line."""

    x: str
    y: str
    lag: int
    points: list[InsightScatterPoint]
    r: float | None
    n: int
    slope: float | None
    intercept: float | None


class InsightWeekday(Model):
    weekday: int  # 0 = Monday
    sleep_s: float | None
    steps: float | None
    avg_stress: float | None
    hrv_ms: float | None
    load: float | None
    readiness: float | None


class InsightCard(Model):
    id: str
    title: str
    text: str
    value: float | None
    unit: str | None
    delta: float | None
    trend: Trend
    sentiment: Sentiment
    metric: str | None


# --------------------------------------------------------------------------------------------
# Daily metrics on a gap-free day axis
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Grid:
    """Daily metrics on consecutive days starting at ``first`` (NaN = no value)."""

    first: date
    size: int
    cols: dict[str, FloatArray]

    def day(self, i: int) -> date:
        return self.first + timedelta(days=i)

    def index(self, d: date) -> int:
        return min(max((d - self.first).days, 0), self.size)

    def window(self, key: str, start: date, end: date) -> FloatArray:
        return self.cols[key][self.index(start) : self.index(end + timedelta(days=1))]


def _grid(session: Session, start: date, end: date, keys: Iterable[str]) -> _Grid:
    """One query on v_daily; ``keys`` must be trusted column names (METRIC_KEYS)."""
    cols = list(dict.fromkeys(keys))
    data = rows(
        session,
        f"SELECT day, {', '.join(cols)} FROM garmin.v_daily "  # noqa: S608 - whitelisted
        "WHERE day BETWEEN :start AND :end ORDER BY day",
        start=start,
        end=end,
    )
    if not data:
        return _Grid(start, 0, {k: np.empty(0) for k in cols})
    first: date = data[0]["day"]
    size = (data[-1]["day"] - first).days + 1
    arrays = {k: np.full(size, np.nan) for k in cols}
    for r in data:
        i = (r["day"] - first).days
        for k in cols:
            if r[k] is not None:
                arrays[k][i] = float(r[k])
    return _Grid(first, size, arrays)


def _shifted(x: FloatArray, y: FloatArray, lag: int) -> tuple[FloatArray, FloatArray]:
    """x on day d paired with y on day d + lag."""
    n = min(x.size, y.size)
    if lag >= n:
        return np.empty(0), np.empty(0)
    return x[: n - lag], y[lag:n]


def _finite(v: float) -> float | None:
    return v if math.isfinite(v) else None


# --------------------------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------------------------


@router.get("/metrics", response_model=list[InsightMetric])
def metrics() -> list[InsightMetric]:
    """Daily metrics available for correlations and scatter plots."""
    return list(METRICS)


@router.get("/correlations", response_model=InsightCorrelations)
def correlations(session: SessionDep, rng: RangeDep, lag: LagQuery = 0) -> InsightCorrelations:
    keys = list(METRIC_KEYS)
    grid = _grid(session, rng.start, rng.end, keys)
    size = len(keys)
    r_out: list[list[float | None]] = [[None] * size for _ in keys]
    n_out = [[0] * size for _ in keys]
    for i, kx in enumerate(keys):
        for j, ky in enumerate(keys):
            if lag == 0 and j < i:  # symmetric without a lag
                r_out[i][j], n_out[i][j] = r_out[j][i], n_out[j][i]
                continue
            r, n = pearson(*_shifted(grid.cols[kx], grid.cols[ky], lag))
            r_out[i][j], n_out[i][j] = _finite(r), n
    return InsightCorrelations(lag=lag, metrics=keys, r=r_out, n=n_out)


@router.get("/scatter", response_model=InsightScatter)
def scatter(
    session: SessionDep,
    rng: RangeDep,
    x: Annotated[str, Query(description="Metric key (see /metrics) on day d")] = "sleep_score",
    y: Annotated[str, Query(description="Metric key on day d + lag")] = "readiness",
    lag: LagQuery = 0,
) -> InsightScatter:
    for key in (x, y):
        if key not in METRIC_KEYS:
            raise HTTPException(status_code=422, detail=f"unknown metric {key!r}")
    grid = _grid(session, rng.start, rng.end, (x, y))
    xs, ys = _shifted(grid.cols[x], grid.cols[y], lag)
    ok = np.flatnonzero(np.isfinite(xs) & np.isfinite(ys))
    points = [InsightScatterPoint(day=grid.day(int(i)), x=float(xs[i]), y=float(ys[i])) for i in ok]
    r, n = pearson(xs, ys)
    try:
        slope, intercept, _ = linear_trend(xs, ys)
    except ValueError:
        slope = intercept = math.nan
    return InsightScatter(
        x=x,
        y=y,
        lag=lag,
        points=points,
        r=_finite(r),
        n=n,
        slope=_finite(slope),
        intercept=_finite(intercept),
    )


@router.get("/weekday", response_model=list[InsightWeekday])
def weekday(session: SessionDep, rng: RangeDep) -> list[InsightWeekday]:
    """Average of daily metrics per weekday (0 = Monday)."""
    data = rows(
        session,
        """
        SELECT extract(isodow FROM day)::int - 1 AS weekday,
               avg(sleep_s)::float8 AS sleep_s, avg(steps)::float8 AS steps,
               avg(avg_stress)::float8 AS avg_stress, avg(hrv_ms)::float8 AS hrv_ms,
               avg(load)::float8 AS load, avg(readiness)::float8 AS readiness
        FROM garmin.v_daily WHERE day BETWEEN :start AND :end GROUP BY 1
        """,
        **rng.params(),
    )
    by_day = {r["weekday"]: r for r in data}
    empty: dict[str, Any] = dict.fromkeys(WEEKDAY_COLUMNS)
    return [InsightWeekday(**{**empty, **by_day.get(wd, {}), "weekday": wd}) for wd in range(7)]


# --------------------------------------------------------------------------------------------
# Cards
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _CardData:
    start: date  # range start, not before the first day with data
    end: date
    grid: _Grid  # daily metrics from min(start, end - 89 days) to end
    activities: list[dict[str, Any]]  # start_time_local, duration_s within [start, end]


def _num(v: float, nd: int = 1) -> str:
    """1234.5 -> '1,234.5'; 3.0 -> '3'."""
    s = f"{v:,.{nd}f}"
    return s.rstrip("0").rstrip(".") if "." in s else s


def _hm(seconds: float) -> str:
    minutes = round(seconds / 60)
    h, m = divmod(minutes, 60)
    if not h:
        return f"{m} min"
    return f"{h} h {m} min" if m else f"{h} h"


def _day(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def _trend(delta: float, eps: float) -> Trend:
    if abs(delta) < eps:
        return "flat"
    return "up" if delta > 0 else "down"


def _sentiment(trend: Trend, *, higher_is_better: bool) -> Sentiment:
    if trend == "flat":
        return "neutral"
    return "good" if (trend == "up") == higher_is_better else "bad"


def _values(a: FloatArray) -> FloatArray:
    return a[np.isfinite(a)]


def _strength(r: float) -> str:
    a = abs(r)
    return "strong" if a >= 0.5 else "moderate" if a >= 0.3 else "weak"


def _resting_hr_card(c: _CardData) -> InsightCard | None:
    recent = _values(c.grid.window("resting_hr", c.end - timedelta(days=29), c.end))
    before = _values(
        c.grid.window("resting_hr", c.end - timedelta(days=89), c.end - timedelta(days=30))
    )
    if recent.size < 14 or before.size < 21:
        return None
    now = float(recent.mean())
    delta = now - float(before.mean())
    trend = _trend(delta, 0.5)
    if trend == "flat":
        text = (
            f"Your resting heart rate is steady at {_num(now, 0)} bpm, about the same as in "
            "the previous two months."
        )
    else:
        direction = "lower" if delta < 0 else "higher"
        text = (
            f"Your resting heart rate is {_num(abs(delta))} bpm {direction} than in the previous "
            f"two months ({_num(now, 0)} bpm on average over the last 30 days)."
        )
    return InsightCard(
        id="resting_hr_change",
        title="Resting heart rate",
        text=text,
        value=round(now, 1),
        unit="bpm",
        delta=round(delta, 1),
        trend=trend,
        sentiment=_sentiment(trend, higher_is_better=False),
        metric="resting_hr",
    )


def _hrv_after_hard_days_card(c: _CardData) -> InsightCard | None:
    """HRV the night after a hard day (load >= 75th percentile of training days) vs others."""
    load = c.grid.window("load", c.start, c.end)
    hrv = c.grid.window("hrv_ms", c.start, c.end)
    trained = load[np.isfinite(load) & (load > 0)]
    if trained.size < 8:
        return None
    threshold = float(np.percentile(trained, 75))
    prev = load[:-1]
    hard = np.isfinite(prev) & (prev > 0) & (prev >= threshold)
    nxt = hrv[1:]
    ok = np.isfinite(nxt)
    after_hard, after_other = nxt[ok & hard], nxt[ok & ~hard]
    if after_hard.size < 5 or after_other.size < 5:
        return None
    hard_avg, other_avg = float(after_hard.mean()), float(after_other.mean())
    delta = hard_avg - other_avg
    trend = _trend(delta, 1.0)
    if trend == "flat":
        comparison = "about the same as"
    else:
        comparison = f"{_num(abs(delta))} ms {'lower' if delta < 0 else 'higher'} than"
    sentiment: Sentiment = "neutral"
    if delta >= -1.0:
        sentiment = "good"
    elif delta < -0.1 * other_avg:
        sentiment = "bad"
    return InsightCard(
        id="hrv_after_hard_days",
        title="Recovery after hard days",
        text=(
            f"After hard training days (load of {_num(threshold, 0)} or more) your overnight HRV "
            f"averages {_num(hard_avg, 0)} ms, {comparison} after other days."
        ),
        value=round(hard_avg, 1),
        unit="ms",
        delta=round(delta, 1),
        trend=trend,
        sentiment=sentiment,
        metric="hrv_ms",
    )


def _weekend_sleep_card(c: _CardData) -> InsightCard | None:
    """Nights ending on Saturday or Sunday vs nights ending on weekdays."""
    sleep = c.grid.window("sleep_s", c.start, c.end)
    first = c.grid.day(c.grid.index(c.start))
    wd = (first.weekday() + np.arange(sleep.size)) % 7
    ok = np.isfinite(sleep)
    weekend, weekday_ = sleep[ok & (wd >= 5)], sleep[ok & (wd < 5)]
    if weekend.size < 4 or weekday_.size < 10:
        return None
    we, wk = float(weekend.mean()), float(weekday_.mean())
    delta = we - wk
    trend = _trend(delta, 300.0)
    if trend == "flat":
        text = f"You sleep about the same on weekends and weekdays ({_hm(wk)} on average)."
    else:
        more = "longer" if delta > 0 else "less"
        text = (
            f"You sleep {_hm(abs(delta))} {more} on weekends ({_hm(we)}) than on weekdays "
            f"({_hm(wk)})."
        )
    return InsightCard(
        id="weekend_sleep",
        title="Weekend sleep",
        text=text,
        value=round(we),
        unit="s",
        delta=round(delta),
        trend=trend,
        sentiment="neutral",
        metric="sleep_s",
    )


def _training_weekday_card(c: _CardData) -> InsightCard | None:
    total = len(c.activities)
    if total < 5:
        return None
    counts = Counter(a["start_time_local"].weekday() for a in c.activities)
    wd, n = max(counts.items(), key=lambda kv: (kv[1], -kv[0]))
    return InsightCard(
        id="training_weekday",
        title="Favourite training day",
        text=(
            f"You train most on {WEEKDAYS[wd]}s: {n} of {total} activities "
            f"({_num(n / total * 100, 0)}%)."
        ),
        value=float(n),
        unit="activities",
        delta=None,
        trend="flat",
        sentiment="neutral",
        metric=None,
    )


def _fitness_card(c: _CardData) -> InsightCard | None:
    now = _values(c.grid.window("ctl", c.end - timedelta(days=6), c.end))
    then = _values(c.grid.window("ctl", c.end - timedelta(days=48), c.end - timedelta(days=42)))
    if not now.size or not then.size:
        return None
    ctl = float(now[-1])
    delta = ctl - float(then[-1])
    trend = _trend(delta, 1.0)
    if trend == "flat":
        text = f"Your fitness (CTL) held steady at {_num(ctl)} over the last 6 weeks."
    else:
        moved = "rose" if delta > 0 else "fell"
        text = (
            f"Your fitness (CTL) {moved} by {_num(abs(delta))} to {_num(ctl)} "
            "over the last 6 weeks."
        )
    return InsightCard(
        id="fitness_change",
        title="Fitness trend",
        text=text,
        value=round(ctl, 1),
        unit="load",
        delta=round(delta, 1),
        trend=trend,
        sentiment=_sentiment(trend, higher_is_better=True),
        metric="ctl",
    )


def _streak_card(c: _CardData) -> InsightCard | None:
    days = [a["start_time_local"].date() for a in c.activities]
    current, longest, longest_start = streaks(days, today=c.end)
    if longest < 2 or longest_start is None:
        return None
    if current >= longest:
        text = f"You are on your longest activity streak of this period: {current} days in a row."
    elif current >= 2:
        text = (
            f"You are on a {current}-day activity streak. Your longest in this period was "
            f"{longest} days, starting {_day(longest_start)}."
        )
    else:
        text = (
            f"Your longest activity streak in this period was {longest} days in a row, "
            f"starting {_day(longest_start)}."
        )
    return InsightCard(
        id="streak",
        title="Activity streak",
        text=text,
        value=float(current),
        unit="days",
        delta=None,
        trend="flat",
        sentiment="good" if current >= 3 else "neutral",
        metric=None,
    )


def _active_month_card(c: _CardData) -> InsightCard | None:
    months: dict[tuple[int, int], tuple[float, int]] = {}
    for a in c.activities:
        key = (a["start_time_local"].year, a["start_time_local"].month)
        seconds, count = months.get(key, (0.0, 0))
        months[key] = (seconds + float(a["duration_s"] or 0.0), count + 1)
    if len(months) < 2:
        return None
    (year, month), (seconds, count) = max(months.items(), key=lambda kv: kv[1][0])
    others = [s for k, (s, _) in months.items() if k != (year, month)]
    return InsightCard(
        id="most_active_month",
        title="Most active month",
        text=(
            f"{MONTHS[month - 1]} {year} was your most active month: {_hm(seconds)} of training "
            f"in {count} activities."
        ),
        value=round(seconds),
        unit="s",
        delta=round(seconds - sum(others) / len(others)),
        trend="flat",
        sentiment="good",
        metric=None,
    )


def _vo2max_card(c: _CardData) -> InsightCard | None:
    v = c.grid.window("vo2max_running", c.start, c.end)
    idx = np.flatnonzero(np.isfinite(v))
    if idx.size < 2 or idx[-1] - idx[0] < 14:
        return None
    first, last = float(v[idx[0]]), float(v[idx[-1]])
    delta = last - first
    trend = _trend(delta, 0.3)
    if trend == "flat":
        text = f"Your running VO2max held steady at {_num(last)} in this period."
    else:
        moved = "rose" if delta > 0 else "fell"
        text = f"Your running VO2max {moved} from {_num(first)} to {_num(last)} in this period."
    return InsightCard(
        id="vo2max_change",
        title="VO2max",
        text=text,
        value=round(last, 1),
        unit="ml/kg/min",
        delta=round(delta, 1),
        trend=trend,
        sentiment=_sentiment(trend, higher_is_better=True),
        metric="vo2max_running",
    )


def _correlation_card(
    card_id: str, title: str, metric: str, r: float, n: int, texts: tuple[str, str, str]
) -> InsightCard | None:
    """``texts``: (positive, negative, no link); each may use {strength}, {r} and {n}."""
    if n < MIN_PAIRS or not math.isfinite(r):
        return None
    trend = _trend(r, 0.1)
    template = {"up": texts[0], "down": texts[1], "flat": texts[2]}[trend]
    return InsightCard(
        id=card_id,
        title=title,
        text=template.format(strength=_strength(r), r=f"{r:.2f}", n=n),
        value=round(r, 2),
        unit="r",
        delta=None,
        trend=trend,
        sentiment="neutral",
        metric=metric,
    )


def _sleep_readiness_card(c: _CardData) -> InsightCard | None:
    """Sleep score of a night vs the training readiness of the morning after."""
    r, n = pearson(
        c.grid.window("sleep_score", c.start, c.end), c.grid.window("readiness", c.start, c.end)
    )
    return _correlation_card(
        "sleep_readiness",
        "Sleep and readiness",
        "sleep_score",
        r,
        n,
        (
            "Better sleep scores go with higher training readiness the next morning "
            "({strength} link, r = {r} over {n} nights).",
            "Surprisingly, better sleep scores go with lower training readiness the next "
            "morning ({strength} link, r = {r} over {n} nights).",
            "Your sleep score and next-morning training readiness are barely linked "
            "(r = {r} over {n} nights).",
        ),
    )


def _stress_sleep_card(c: _CardData) -> InsightCard | None:
    """Average stress of a day vs the sleep score of the following night."""
    r, n = pearson(
        *_shifted(
            c.grid.window("avg_stress", c.start, c.end),
            c.grid.window("sleep_score", c.start, c.end),
            1,
        )
    )
    return _correlation_card(
        "stress_sleep",
        "Stress and sleep",
        "avg_stress",
        r,
        n,
        (
            "On more stressful days your sleep score the following night tends to be higher "
            "({strength} link, r = {r} over {n} days).",
            "On more stressful days you sleep worse the following night "
            "({strength} link, r = {r} over {n} days).",
            "Daytime stress and your sleep score the following night are barely linked "
            "(r = {r} over {n} days).",
        ),
    )


def _consistency_card(c: _CardData) -> InsightCard | None:
    """Share of calendar weeks (Monday-Sunday) in the period with at least one activity."""
    first_monday = c.start - timedelta(days=c.start.weekday())
    last_monday = c.end - timedelta(days=c.end.weekday())
    weeks = (last_monday - first_monday).days // 7 + 1
    if weeks < 4:
        return None
    active = {
        a["start_time_local"].date() - timedelta(days=a["start_time_local"].weekday())
        for a in c.activities
    }
    pct = len(active) / weeks * 100
    sentiment: Sentiment = "good" if pct >= 80 else "bad" if pct < 50 else "neutral"
    return InsightCard(
        id="consistency",
        title="Consistency",
        text=f"You were active in {len(active)} of {weeks} weeks ({_num(pct, 0)}%).",
        value=round(pct, 1),
        unit="%",
        delta=None,
        trend="flat",
        sentiment=sentiment,
        metric=None,
    )


CARD_BUILDERS: tuple[Callable[[_CardData], InsightCard | None], ...] = (
    _resting_hr_card,
    _hrv_after_hard_days_card,
    _fitness_card,
    _vo2max_card,
    _sleep_readiness_card,
    _stress_sleep_card,
    _weekend_sleep_card,
    _training_weekday_card,
    _streak_card,
    _active_month_card,
    _consistency_card,
)
CARD_METRICS = (
    "resting_hr",
    "hrv_ms",
    "load",
    "sleep_s",
    "sleep_score",
    "readiness",
    "avg_stress",
    "ctl",
    "vo2max_running",
)


@router.get("/cards", response_model=list[InsightCard])
def cards(session: SessionDep, rng: RangeDep) -> list[InsightCard]:
    """Plain-English findings; a card only appears when there is enough data for it."""
    first_day = data_bounds(session)[0]
    start = min(max(rng.start, first_day), rng.end) if first_day else rng.start
    grid = _grid(session, min(start, rng.end - timedelta(days=89)), rng.end, CARD_METRICS)
    activities = rows(
        session,
        "SELECT start_time_local, duration_s FROM garmin.activity "
        "WHERE start_time_local >= :start AND start_time_local < :end_excl "
        "ORDER BY start_time_local",
        start=start,
        end_excl=rng.end + timedelta(days=1),
    )
    data = _CardData(start=start, end=rng.end, grid=grid, activities=activities)
    return [card for build in CARD_BUILDERS if (card := build(data)) is not None]
