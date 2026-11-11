"""Records: best-effort curves, best times over standard distances, Garmin PRs, year race."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query

from garminizer.analytics.curves import STANDARD_DISTANCES_M
from garminizer.api.activity_sql import SUMMARY_COLUMNS, sport_only
from garminizer.api.deps import SessionDep, SportDep, data_bounds, rows
from garminizer.api.schemas import ActivitySummary, Model

router = APIRouter(prefix="/api/records", tags=["records"])

DEFAULT_SPORT = "run"
CURVE_WINDOWS: tuple[tuple[str, str, int | None], ...] = (
    ("all", "All time", None),
    ("365d", "Last 365 days", 365),
    ("90d", "Last 90 days", 90),
)
DISTANCE_LABELS: dict[float, str] = dict(
    zip(
        (float(d) for d in STANDARD_DISTANCES_M),
        (
            "400 m",
            "1 km",
            "1 mile",
            "5 km",
            "10 km",
            "15 km",
            "Half marathon",
            "30 km",
            "Marathon",
        ),
        strict=True,
    )
)
CUMULATIVE_COLUMNS = {
    "distance": "distance_m",
    "duration": "duration_s",
    "elevation": "elevation_gain_m",
}
TOP_COLUMNS = {
    "distance": "a.distance_m",
    "duration": "a.duration_s",
    "elevation": "a.elevation_gain_m",
    "load": "a.training_load",
    "speed": "a.avg_speed_mps",
}


class RecordsCurvePoint(Model):
    duration_s: int
    value: float
    activity_id: int
    day: date


class RecordsCurveWindow(Model):
    key: str
    label: str
    points: list[RecordsCurvePoint]


class RecordsCurve(Model):
    metric: str
    sport_group: str
    windows: list[RecordsCurveWindow]


class RecordsBestTime(Model):
    seconds: float
    activity_id: int
    day: date
    name: str | None


class RecordsProgressionPoint(Model):
    day: date
    seconds: float
    activity_id: int


class RecordsDistance(Model):
    distance_m: float
    label: str
    best: RecordsBestTime | None
    best_this_year: RecordsBestTime | None
    progression: list[RecordsProgressionPoint]


class RecordsPersonal(Model):
    record_id: int
    type_id: int
    type_key: str
    value: float
    activity_id: int | None
    achieved_at: datetime | None
    activity_name: str | None


class RecordsCumulativePoint(Model):
    day_of_year: int
    value: float


class RecordsCumulativeYear(Model):
    year: int
    total: float
    points: list[RecordsCumulativePoint]


class RecordsCumulative(Model):
    metric: str
    sport_group: str
    years: list[RecordsCumulativeYear]


@router.get("/curves", response_model=RecordsCurve)
def curves(
    session: SessionDep,
    sport: SportDep,
    metric: Annotated[Literal["power", "speed", "hr"], Query()] = "speed",
) -> RecordsCurve:
    """All-time / 365-day / 90-day best average value per duration (sport defaults to run).

    Windows end at the last day with data. A point is the best average held for at least
    that duration (non-increasing curve) and names the activity holding it (earliest on ties).
    """
    group = sport or DEFAULT_SPORT
    last = data_bounds(session)[1]
    points: dict[str, list[RecordsCurvePoint]] = {key: [] for key, _, _ in CURVE_WINDOWS}
    if last is not None:
        cuts = {
            key: datetime.combine(last - timedelta(days=days - 1), datetime.min.time())
            for key, _, days in CURVE_WINDOWS
            if days is not None
        }
        data = rows(
            session,
            """
            WITH w(key, cut) AS (
                VALUES ('all', CAST(NULL AS timestamp)),
                       ('365d', CAST(:cut_365d AS timestamp)),
                       ('90d', CAST(:cut_90d AS timestamp))
            )
            SELECT DISTINCT ON (w.key, b.duration_s)
                   w.key, b.duration_s, b.value, b.activity_id, a.start_time_local::date AS day
            FROM w
            JOIN garmin.activity a
              ON a.sport_group = :sport AND (w.cut IS NULL OR a.start_time_local >= w.cut)
            JOIN garmin.activity_best_effort b
              ON b.activity_id = a.activity_id AND b.metric = :metric
            ORDER BY w.key, b.duration_s, b.value DESC, a.start_time_local, b.activity_id
            """,
            sport=group,
            metric=metric,
            cut_365d=cuts["365d"],
            cut_90d=cuts["90d"],
        )
        for r in data:
            points[r.pop("key")].append(RecordsCurvePoint(**r))
    return RecordsCurve(
        metric=metric,
        sport_group=group,
        windows=[
            RecordsCurveWindow(key=key, label=label, points=_envelope(points[key]))
            for key, label, _ in CURVE_WINDOWS
        ],
    )


def _envelope(points: list[RecordsCurvePoint]) -> list[RecordsCurvePoint]:
    """Best value held for *at least* each duration, so the curve never rises with duration.

    Mean-max values may rise slightly between durations that are not multiples of each other
    (e.g. 2 s vs 3 s); an effort held for longer also counts for every shorter duration, and
    the point then names the activity of that longer effort. ``points`` are sorted by duration.
    """
    out: list[RecordsCurvePoint] = []
    best: RecordsCurvePoint | None = None
    for p in reversed(points):
        if best is None or p.value >= best.value:
            best = p
        out.append(best.model_copy(update={"duration_s": p.duration_s}))
    out.reverse()
    return out


@router.get("/distances", response_model=list[RecordsDistance])
def distances(session: SessionDep, sport: SportDep) -> list[RecordsDistance]:
    """Best times over standard distances inside activities (sport defaults to run).

    ``best_this_year`` is the calendar year of the last day with data; ``progression`` lists
    every new all-time best in chronological order.
    """
    group = sport or DEFAULT_SPORT
    last = data_bounds(session)[1]
    progression = rows(
        session,
        """
        SELECT distance_m, seconds, activity_id, day, name FROM (
            SELECT d.distance_m, d.seconds, d.activity_id, a.start_time_local::date AS day,
                   a.name, a.start_time_local,
                   min(d.seconds) OVER (
                       PARTITION BY d.distance_m ORDER BY a.start_time_local, d.activity_id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) AS previous_best
            FROM garmin.activity_best_distance d JOIN garmin.activity a USING (activity_id)
            WHERE a.sport_group = :sport
        ) s
        WHERE previous_best IS NULL OR seconds < previous_best
        ORDER BY distance_m, start_time_local, activity_id
        """,
        sport=group,
    )
    this_year: list[dict[str, Any]] = []
    if last is not None:
        this_year = rows(
            session,
            """
            SELECT DISTINCT ON (d.distance_m) d.distance_m, d.seconds, d.activity_id,
                   a.start_time_local::date AS day, a.name
            FROM garmin.activity_best_distance d JOIN garmin.activity a USING (activity_id)
            WHERE a.sport_group = :sport
              AND a.start_time_local >= :year_start AND a.start_time_local < :year_end
            ORDER BY d.distance_m, d.seconds, a.start_time_local, d.activity_id
            """,
            sport=group,
            year_start=date(last.year, 1, 1),
            year_end=date(last.year + 1, 1, 1),
        )
    steps: dict[float, list[dict[str, Any]]] = {d: [] for d in DISTANCE_LABELS}
    for r in progression:
        steps.setdefault(float(r["distance_m"]), []).append(r)
    year_best = {float(r["distance_m"]): r for r in this_year}

    def best(r: dict[str, Any] | None) -> RecordsBestTime | None:
        if r is None:
            return None
        return RecordsBestTime(
            seconds=r["seconds"], activity_id=r["activity_id"], day=r["day"], name=r["name"]
        )

    return [
        RecordsDistance(
            distance_m=d,
            label=label,
            best=best(steps[d][-1] if steps[d] else None),
            best_this_year=best(year_best.get(d)),
            progression=[
                RecordsProgressionPoint(
                    day=r["day"], seconds=r["seconds"], activity_id=r["activity_id"]
                )
                for r in steps[d]
            ],
        )
        for d, label in DISTANCE_LABELS.items()
    ]


@router.get("/personal", response_model=list[RecordsPersonal])
def personal(session: SessionDep) -> list[RecordsPersonal]:
    """Personal records as tracked by Garmin (times in s, distances in m, counts)."""
    data = rows(
        session,
        """
        SELECT p.record_id, p.type_id, p.type_key, p.value, p.activity_id, p.achieved_at,
               a.name AS activity_name
        FROM garmin.personal_record p LEFT JOIN garmin.activity a USING (activity_id)
        ORDER BY p.type_id, p.record_id
        """,
    )
    return [RecordsPersonal(**r) for r in data]


@router.get("/cumulative", response_model=RecordsCumulative)
def cumulative(
    session: SessionDep,
    sport: SportDep,
    metric: Annotated[Literal["distance", "duration", "elevation"], Query()] = "distance",
) -> RecordsCumulative:
    """Running total per day of year for every year with activities (sport defaults to run).

    One point per day from 1 January to 31 December (to the last day with data in the
    latest year); days without activities carry the running total.
    """
    group = sport or DEFAULT_SPORT
    column = CUMULATIVE_COLUMNS[metric]
    last = data_bounds(session)[1]
    daily = rows(
        session,
        f"""
        SELECT start_time_local::date AS day, sum(coalesce({column}, 0)) AS value
        FROM garmin.activity WHERE sport_group = :sport
        GROUP BY 1 ORDER BY 1
        """,  # noqa: S608 - column comes from a whitelist
        sport=group,
    )
    by_day: dict[date, float] = {r["day"]: float(r["value"]) for r in daily}
    years: list[RecordsCumulativeYear] = []
    for year in sorted({d.year for d in by_day}):
        day = date(year, 1, 1)
        stop = date(year, 12, 31)
        if last is not None and last.year == year:
            stop = min(stop, last)
        running = 0.0
        points: list[RecordsCumulativePoint] = []
        while day <= stop:
            running += by_day.get(day, 0.0)
            points.append(
                RecordsCumulativePoint(day_of_year=day.timetuple().tm_yday, value=round(running, 1))
            )
            day += timedelta(days=1)
        years.append(RecordsCumulativeYear(year=year, total=round(running, 1), points=points))
    return RecordsCumulative(metric=metric, sport_group=group, years=years)


@router.get("/top", response_model=list[ActivitySummary])
def top(
    session: SessionDep,
    sport: SportDep,
    by: Annotated[Literal["distance", "duration", "elevation", "load", "speed"], Query()] = (
        "distance"
    ),
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> list[ActivitySummary]:
    """All-time top activities by distance, duration, elevation gain, load or average speed."""
    column = TOP_COLUMNS[by]
    sport_sql, sport_params = sport_only(sport)
    params: dict[str, Any] = {"limit": limit, **sport_params}
    where = f"{column} IS NOT NULL" + sport_sql
    data = rows(
        session,
        f"SELECT {SUMMARY_COLUMNS} FROM garmin.activity a WHERE {where} "  # noqa: S608 - whitelisted
        f"ORDER BY {column} DESC, a.start_time_utc, a.activity_id LIMIT :limit",
        **params,
    )
    return [ActivitySummary(**r) for r in data]
