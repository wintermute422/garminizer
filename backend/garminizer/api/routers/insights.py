"""Insights endpoints: correlations, scatter plots, weekday patterns and cards.

The read model (metrics, the daily grid, correlations, cards) is ``garminizer.insights``.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from garminizer import insights
from garminizer.api.deps import RangeDep, SessionDep, data_bounds, rows
from garminizer.insights import (
    METRIC_KEYS,
    METRICS,
    WEEKDAY_COLUMNS,
    InsightCard,
    InsightCorrelations,
    InsightMetric,
    InsightScatter,
    InsightWeekday,
)

router = APIRouter(prefix="/api/insights", tags=["insights"])

LagQuery = Annotated[
    int, Query(ge=0, le=7, description="Days between x and y: x on day d, y on day d + lag")
]


@router.get("/metrics", response_model=list[InsightMetric])
def metrics() -> list[InsightMetric]:
    """Daily metrics available for correlations and scatter plots."""
    return list(METRICS)


@router.get("/correlations", response_model=InsightCorrelations)
def correlations(session: SessionDep, rng: RangeDep, lag: LagQuery = 0) -> InsightCorrelations:
    grid = insights.load_grid(session, rng.start, rng.end, METRIC_KEYS)
    return insights.correlation_matrix(grid, lag)


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
    grid = insights.load_grid(session, rng.start, rng.end, (x, y))
    return insights.scatter(grid, x, y, lag)


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


@router.get("/cards", response_model=list[InsightCard])
def cards(session: SessionDep, rng: RangeDep) -> list[InsightCard]:
    """Plain-English findings; a card only appears when there is enough data for it."""
    first_day = data_bounds(session)[0]
    start = min(max(rng.start, first_day), rng.end) if first_day else rng.start
    return insights.build_cards(insights.load_card_data(session, start, rng.end))
