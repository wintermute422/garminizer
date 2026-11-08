"""Training readiness/status and performance metrics (daily series)."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Day, Real, Small


class TrainingReadiness(Base):
    __tablename__ = "training_readiness"
    __table_args__ = {"comment": "Morning training readiness score and its factors."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    score: Mapped[Small | None]
    level: Mapped[str | None] = mapped_column(comment="PRIME | HIGH | MODERATE | LOW | POOR")
    sleep_score_factor: Mapped[Small | None]
    recovery_time_min: Mapped[Small | None]
    recovery_factor: Mapped[Small | None]
    acwr_factor: Mapped[Small | None]
    hrv_factor: Mapped[Small | None]
    stress_history_factor: Mapped[Small | None]
    sleep_history_factor: Mapped[Small | None]
    feedback: Mapped[str | None]


class TrainingStatus(Base):
    __tablename__ = "training_status"
    __table_args__ = {"comment": "Garmin training status and load balance per day."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    status: Mapped[str | None] = mapped_column(
        comment="PEAKING | PRODUCTIVE | MAINTAINING | RECOVERY | UNPRODUCTIVE | DETRAINING ..."
    )
    acute_load: Mapped[Real | None]
    chronic_load: Mapped[Real | None]
    acwr: Mapped[Real | None] = mapped_column(comment="Acute:chronic workload ratio")
    acwr_status: Mapped[str | None]
    load_low_aerobic: Mapped[Real | None]
    load_high_aerobic: Mapped[Real | None]
    load_anaerobic: Mapped[Real | None]
    target_low_aerobic_min: Mapped[Real | None]
    target_low_aerobic_max: Mapped[Real | None]
    target_high_aerobic_min: Mapped[Real | None]
    target_high_aerobic_max: Mapped[Real | None]
    target_anaerobic_min: Mapped[Real | None]
    target_anaerobic_max: Mapped[Real | None]
    load_balance_feedback: Mapped[str | None]
    heat_acclimation_pct: Mapped[Real | None]
    altitude_acclimation_m: Mapped[Real | None]


class MaxMetric(Base):
    __tablename__ = "max_metric"
    __table_args__ = {"comment": "VO2max estimates and fitness age."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    vo2max_running: Mapped[Real | None]
    vo2max_cycling: Mapped[Real | None]
    fitness_age: Mapped[Real | None]


class RacePrediction(Base):
    __tablename__ = "race_prediction"
    __table_args__ = {"comment": "Predicted race times (seconds)."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    time_5k_s: Mapped[Real | None]
    time_10k_s: Mapped[Real | None]
    time_half_s: Mapped[Real | None]
    time_marathon_s: Mapped[Real | None]


class EnduranceScore(Base):
    __tablename__ = "endurance_score"
    __table_args__ = {"comment": "Garmin endurance score."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    score: Mapped[Real | None]
    classification: Mapped[str | None]


class HillScore(Base):
    __tablename__ = "hill_score"
    __table_args__ = {"comment": "Garmin hill score with its endurance/strength parts."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    score: Mapped[Real | None]
    endurance: Mapped[Real | None]
    strength: Mapped[Real | None]
