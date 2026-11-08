"""Daily wellness, sleep, HRV and intraday samples."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Day, Real, Small, TsTz


class DailySummary(Base):
    __tablename__ = "daily_summary"
    __table_args__ = {"comment": "One row per calendar day (athlete's local date)."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    steps: Mapped[int | None]
    step_goal: Mapped[int | None]
    distance_m: Mapped[float | None]
    floors_up: Mapped[Real | None]
    floors_down: Mapped[Real | None]
    floors_goal: Mapped[Real | None]
    total_kcal: Mapped[Real | None]
    active_kcal: Mapped[Real | None]
    bmr_kcal: Mapped[Real | None]
    resting_hr: Mapped[Small | None]
    min_hr: Mapped[Small | None]
    max_hr: Mapped[Small | None]
    avg_stress: Mapped[Small | None]
    max_stress: Mapped[Small | None]
    stress_rest_s: Mapped[int | None]
    stress_low_s: Mapped[int | None]
    stress_medium_s: Mapped[int | None]
    stress_high_s: Mapped[int | None]
    body_battery_high: Mapped[Small | None]
    body_battery_low: Mapped[Small | None]
    body_battery_charged: Mapped[Small | None]
    body_battery_drained: Mapped[Small | None]
    body_battery_at_wake: Mapped[Small | None]
    moderate_intensity_min: Mapped[Small | None]
    vigorous_intensity_min: Mapped[Small | None]
    intensity_goal_min: Mapped[Small | None]
    avg_spo2: Mapped[Real | None]
    lowest_spo2: Mapped[Real | None]
    avg_waking_respiration: Mapped[Real | None]
    hydration_ml: Mapped[Real | None]
    hydration_goal_ml: Mapped[Real | None]
    sedentary_s: Mapped[int | None]
    active_s: Mapped[int | None]
    highly_active_s: Mapped[int | None]
    sleeping_s: Mapped[int | None]


class Sleep(Base):
    __tablename__ = "sleep"
    __table_args__ = {"comment": "One row per night, keyed by the wake-up day."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    start_utc: Mapped[TsTz | None]
    end_utc: Mapped[TsTz | None]
    duration_s: Mapped[int | None]
    deep_s: Mapped[int | None]
    light_s: Mapped[int | None]
    rem_s: Mapped[int | None]
    awake_s: Mapped[int | None]
    unmeasurable_s: Mapped[int | None]
    score: Mapped[Small | None] = mapped_column(comment="Overall sleep score 0-100")
    score_quality: Mapped[str | None] = mapped_column(comment="EXCELLENT | GOOD | FAIR | POOR")
    score_duration: Mapped[Small | None]
    score_deep: Mapped[Small | None]
    score_rem: Mapped[Small | None]
    score_light: Mapped[Small | None]
    score_awakenings: Mapped[Small | None]
    score_stress: Mapped[Small | None]
    avg_hr: Mapped[Real | None]
    lowest_hr: Mapped[Small | None]
    avg_respiration: Mapped[Real | None]
    lowest_respiration: Mapped[Real | None]
    highest_respiration: Mapped[Real | None]
    avg_spo2: Mapped[Real | None]
    lowest_spo2: Mapped[Real | None]
    avg_stress: Mapped[Real | None]
    avg_overnight_hrv: Mapped[Real | None]
    restless_moments: Mapped[Small | None]
    awake_count: Mapped[Small | None]
    body_battery_change: Mapped[Small | None]
    sleep_need_min: Mapped[Small | None]
    feedback: Mapped[str | None]


class SleepStage(Base):
    __tablename__ = "sleep_stage"
    __table_args__ = {"comment": "Hypnogram: sleep stage intervals per night."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    start_utc: Mapped[TsTz] = mapped_column(primary_key=True)
    end_utc: Mapped[TsTz]
    stage: Mapped[str] = mapped_column(comment="deep | light | rem | awake")


class HrvDaily(Base):
    __tablename__ = "hrv_daily"
    __table_args__ = {"comment": "Overnight heart-rate variability summary."}

    day: Mapped[Day] = mapped_column(primary_key=True)
    last_night_avg_ms: Mapped[Real | None]
    last_night_5min_high_ms: Mapped[Real | None]
    weekly_avg_ms: Mapped[Real | None]
    baseline_low_ms: Mapped[Real | None]
    baseline_balanced_low_ms: Mapped[Real | None]
    baseline_balanced_upper_ms: Mapped[Real | None]
    status: Mapped[str | None] = mapped_column(comment="BALANCED | UNBALANCED | LOW | POOR")
    feedback: Mapped[str | None]


class HrSample(Base):
    __tablename__ = "hr_sample"
    __table_args__ = {"comment": "All-day heart rate (about every 2 minutes)."}

    ts: Mapped[TsTz] = mapped_column(primary_key=True)
    bpm: Mapped[Small]


class StressSample(Base):
    __tablename__ = "stress_sample"
    __table_args__ = {"comment": "All-day stress level 0-100; -1 = not enough data, -2 = activity."}

    ts: Mapped[TsTz] = mapped_column(primary_key=True)
    level: Mapped[Small]


class BodyBatterySample(Base):
    __tablename__ = "body_battery_sample"
    __table_args__ = {"comment": "All-day Body Battery level 0-100."}

    ts: Mapped[TsTz] = mapped_column(primary_key=True)
    level: Mapped[Small]


class RespirationSample(Base):
    __tablename__ = "respiration_sample"
    __table_args__ = {"comment": "All-day respiration rate (breaths/min)."}

    ts: Mapped[TsTz] = mapped_column(primary_key=True)
    breaths_per_min: Mapped[Real]


class Spo2Sample(Base):
    __tablename__ = "spo2_sample"
    __table_args__ = {"comment": "Pulse-ox readings (%)."}

    ts: Mapped[TsTz] = mapped_column(primary_key=True)
    spo2_pct: Mapped[Real]


class StepsInterval(Base):
    __tablename__ = "steps_interval"
    __table_args__ = {"comment": "Steps per 15-minute interval with activity level."}

    start_utc: Mapped[TsTz] = mapped_column(primary_key=True)
    end_utc: Mapped[TsTz]
    steps: Mapped[int]
    activity_level: Mapped[str | None] = mapped_column(
        comment="sedentary | active | highlyActive | sleeping | none"
    )
