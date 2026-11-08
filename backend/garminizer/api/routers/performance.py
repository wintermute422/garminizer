"""Performance: VO2max, race predictions, endurance/hill score, fitness age, efficiency."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter

from garminizer.api.deps import RangeDep, SessionDep, SportDep, one, rows
from garminizer.api.schemas import Model, TimePoint

router = APIRouter(prefix="/api/performance", tags=["performance"])


class PerformanceVo2maxPoint(Model):
    day: date
    running: float | None
    cycling: float | None


class PerformanceRacePredictionPoint(Model):
    day: date
    time_5k_s: float | None
    time_10k_s: float | None
    time_half_s: float | None
    time_marathon_s: float | None


class PerformanceEndurancePoint(Model):
    day: date
    score: float | None
    classification: str | None


class PerformanceHillPoint(Model):
    day: date
    score: float | None
    endurance: float | None
    strength: float | None


class PerformanceLatest(Model):
    """Latest non-null value of every metric up to the range end (each looked up on its own)."""

    vo2max_running: float | None
    vo2max_cycling: float | None
    fitness_age: float | None
    time_5k_s: float | None
    time_10k_s: float | None
    time_half_s: float | None
    time_marathon_s: float | None
    endurance_score: float | None
    endurance_class: str | None
    hill_score: float | None


class PerformanceSeries(Model):
    vo2max: list[PerformanceVo2maxPoint]
    race_predictions: list[PerformanceRacePredictionPoint]
    endurance: list[PerformanceEndurancePoint]
    hill: list[PerformanceHillPoint]
    fitness_age: list[TimePoint]
    latest: PerformanceLatest


class PerformanceEfficiencyPoint(Model):
    activity_id: int
    day: date
    name: str | None
    sport_group: str
    efficiency_factor: float
    aerobic_decoupling_pct: float | None
    avg_hr: int | None
    avg_speed_mps: float | None
    avg_power_w: float | None
    distance_m: float | None
    duration_s: float | None


LATEST_SQL = """
SELECT
  (SELECT vo2max_running FROM garmin.max_metric
   WHERE day <= :end AND vo2max_running IS NOT NULL ORDER BY day DESC LIMIT 1) AS vo2max_running,
  (SELECT vo2max_cycling FROM garmin.max_metric
   WHERE day <= :end AND vo2max_cycling IS NOT NULL ORDER BY day DESC LIMIT 1) AS vo2max_cycling,
  (SELECT fitness_age FROM garmin.max_metric
   WHERE day <= :end AND fitness_age IS NOT NULL ORDER BY day DESC LIMIT 1) AS fitness_age,
  (SELECT time_5k_s FROM garmin.race_prediction
   WHERE day <= :end AND time_5k_s IS NOT NULL ORDER BY day DESC LIMIT 1) AS time_5k_s,
  (SELECT time_10k_s FROM garmin.race_prediction
   WHERE day <= :end AND time_10k_s IS NOT NULL ORDER BY day DESC LIMIT 1) AS time_10k_s,
  (SELECT time_half_s FROM garmin.race_prediction
   WHERE day <= :end AND time_half_s IS NOT NULL ORDER BY day DESC LIMIT 1) AS time_half_s,
  (SELECT time_marathon_s FROM garmin.race_prediction
   WHERE day <= :end AND time_marathon_s IS NOT NULL ORDER BY day DESC LIMIT 1) AS time_marathon_s,
  (SELECT score FROM garmin.endurance_score
   WHERE day <= :end AND score IS NOT NULL ORDER BY day DESC LIMIT 1) AS endurance_score,
  (SELECT classification FROM garmin.endurance_score
   WHERE day <= :end AND classification IS NOT NULL ORDER BY day DESC LIMIT 1) AS endurance_class,
  (SELECT score FROM garmin.hill_score
   WHERE day <= :end AND score IS NOT NULL ORDER BY day DESC LIMIT 1) AS hill_score
"""


@router.get("", response_model=PerformanceSeries)
def performance(session: SessionDep, rng: RangeDep) -> PerformanceSeries:
    """Daily performance series in the range plus the latest known values."""
    p = rng.params()
    vo2 = rows(
        session,
        """
        SELECT day, vo2max_running AS running, vo2max_cycling AS cycling FROM garmin.max_metric
        WHERE day BETWEEN :start AND :end
          AND num_nonnulls(vo2max_running, vo2max_cycling) > 0
        ORDER BY day
        """,
        **p,
    )
    races = rows(
        session,
        """
        SELECT day, time_5k_s, time_10k_s, time_half_s, time_marathon_s
        FROM garmin.race_prediction
        WHERE day BETWEEN :start AND :end
          AND num_nonnulls(time_5k_s, time_10k_s, time_half_s, time_marathon_s) > 0
        ORDER BY day
        """,
        **p,
    )
    endurance = rows(
        session,
        """
        SELECT day, score, classification FROM garmin.endurance_score
        WHERE day BETWEEN :start AND :end AND num_nonnulls(score, classification) > 0
        ORDER BY day
        """,
        **p,
    )
    hill = rows(
        session,
        """
        SELECT day, score, endurance, strength FROM garmin.hill_score
        WHERE day BETWEEN :start AND :end AND num_nonnulls(score, endurance, strength) > 0
        ORDER BY day
        """,
        **p,
    )
    age = rows(
        session,
        """
        SELECT day, fitness_age AS value FROM garmin.max_metric
        WHERE day BETWEEN :start AND :end AND fitness_age IS NOT NULL
        ORDER BY day
        """,
        **p,
    )
    latest: dict[str, Any] = one(session, LATEST_SQL, end=rng.end) or {}
    return PerformanceSeries(
        vo2max=[PerformanceVo2maxPoint(**r) for r in vo2],
        race_predictions=[PerformanceRacePredictionPoint(**r) for r in races],
        endurance=[PerformanceEndurancePoint(**r) for r in endurance],
        hill=[PerformanceHillPoint(**r) for r in hill],
        fitness_age=[TimePoint(**r) for r in age],
        latest=PerformanceLatest(**latest),
    )


@router.get("/efficiency", response_model=list[PerformanceEfficiencyPoint])
def efficiency(
    session: SessionDep, rng: RangeDep, sport: SportDep
) -> list[PerformanceEfficiencyPoint]:
    """Efficiency factor and aerobic decoupling per activity (sport defaults to run)."""
    data = rows(
        session,
        """
        SELECT activity_id, start_time_local::date AS day, name, sport_group, efficiency_factor,
               aerobic_decoupling_pct, avg_hr, avg_speed_mps, avg_power_w, distance_m, duration_s
        FROM garmin.activity
        WHERE start_time_local >= :start AND start_time_local < :end_excl
          AND sport_group = :sport AND efficiency_factor IS NOT NULL
        ORDER BY start_time_local, activity_id
        """,
        sport=sport or "run",
        **rng.params(),
    )
    return [PerformanceEfficiencyPoint(**r) for r in data]
