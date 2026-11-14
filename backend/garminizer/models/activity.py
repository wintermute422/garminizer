"""Activities and everything recorded during them."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, LargeBinary
from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Big, Real, Small, Ts, TsTz

_ACTIVITY_FK = "activity.activity_id"


class Activity(Base):
    __tablename__ = "activity"
    __table_args__ = (
        Index(None, "start_time_utc"),
        Index(None, "sport_group", "start_time_utc"),
        {"comment": "One row per recorded activity (summary values)."},
    )

    activity_id: Mapped[Big] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str | None]
    description: Mapped[str | None]
    sport_type: Mapped[str] = mapped_column(comment="Garmin typeKey, e.g. trail_running")
    sport_group: Mapped[str] = mapped_column(
        comment="run | ride | swim | walk | hike | strength | cardio | winter | water | other"
    )
    start_time_utc: Mapped[TsTz]
    start_time_local: Mapped[Ts]
    duration_s: Mapped[float | None]
    elapsed_s: Mapped[float | None]
    moving_s: Mapped[float | None]
    distance_m: Mapped[float | None]
    elevation_gain_m: Mapped[Real | None]
    elevation_loss_m: Mapped[Real | None]
    min_elevation_m: Mapped[Real | None]
    max_elevation_m: Mapped[Real | None]
    avg_speed_mps: Mapped[Real | None]
    max_speed_mps: Mapped[Real | None]
    avg_hr: Mapped[Small | None]
    max_hr: Mapped[Small | None]
    avg_cadence: Mapped[Real | None] = mapped_column(comment="steps/min (run) or rpm (ride)")
    max_cadence: Mapped[Real | None]
    avg_power_w: Mapped[Real | None]
    max_power_w: Mapped[Real | None]
    normalized_power_w: Mapped[Real | None]
    training_stress_score: Mapped[Real | None]
    intensity_factor: Mapped[Real | None]
    calories: Mapped[Real | None]
    bmr_calories: Mapped[Real | None] = mapped_column(
        comment="Resting calories during the activity (part of calories)"
    )
    aerobic_te: Mapped[Real | None] = mapped_column(comment="Aerobic training effect 0-5")
    anaerobic_te: Mapped[Real | None] = mapped_column(comment="Anaerobic training effect 0-5")
    training_effect_label: Mapped[str | None]
    training_load: Mapped[Real | None] = mapped_column(comment="Garmin activity training load")
    trimp: Mapped[Real | None] = mapped_column(comment="Banister TRIMP (computed by Garminizer)")
    vo2max: Mapped[Real | None]
    avg_temperature_c: Mapped[Real | None]
    min_temperature_c: Mapped[Real | None]
    max_temperature_c: Mapped[Real | None]
    avg_respiration: Mapped[Real | None]
    avg_stride_length_m: Mapped[Real | None]
    avg_vertical_oscillation_cm: Mapped[Real | None]
    avg_ground_contact_ms: Mapped[Real | None]
    avg_vertical_ratio: Mapped[Real | None]
    steps: Mapped[int | None]
    lap_count: Mapped[Small | None]
    pool_length_m: Mapped[Real | None]
    active_lengths: Mapped[Small | None]
    strokes: Mapped[Real | None]
    avg_swolf: Mapped[Real | None]
    total_sets: Mapped[Small | None]
    total_reps: Mapped[Small | None]
    moderate_intensity_min: Mapped[Small | None]
    vigorous_intensity_min: Mapped[Small | None]
    body_battery_delta: Mapped[Small | None]
    water_estimated_ml: Mapped[Real | None]
    start_lat: Mapped[float | None]
    start_lon: Mapped[float | None]
    end_lat: Mapped[float | None]
    end_lon: Mapped[float | None]
    location_name: Mapped[str | None]
    device_id: Mapped[Big | None]
    is_manual: Mapped[bool] = mapped_column(server_default="false")
    is_favorite: Mapped[bool] = mapped_column(server_default="false")
    has_samples: Mapped[bool] = mapped_column(
        server_default="false", comment="True when per-second samples were ingested"
    )
    aerobic_decoupling_pct: Mapped[Real | None] = mapped_column(
        comment="Pa:HR drift first vs second half (computed by Garminizer)"
    )
    efficiency_factor: Mapped[Real | None] = mapped_column(
        comment="Output per heartbeat: (m/min or W) / bpm (computed by Garminizer)"
    )
    analytics_version: Mapped[Small] = mapped_column(
        server_default="0", comment="Version of the analytics that processed this activity"
    )
    updated_at: Mapped[TsTz | None]


class ActivitySample(Base):
    __tablename__ = "activity_sample"
    __table_args__ = {"comment": "Per-record samples from the activity's FIT file."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    t_s: Mapped[int] = mapped_column(primary_key=True, comment="Seconds since activity start")
    ts: Mapped[TsTz]
    lat: Mapped[float | None]
    lon: Mapped[float | None]
    altitude_m: Mapped[Real | None]
    distance_m: Mapped[float | None]
    speed_mps: Mapped[Real | None]
    hr: Mapped[Small | None]
    cadence: Mapped[Small | None]
    power_w: Mapped[Small | None]
    temperature_c: Mapped[Real | None]
    vertical_oscillation_cm: Mapped[Real | None]
    ground_contact_ms: Mapped[Real | None]
    stride_length_m: Mapped[Real | None]
    respiration_rate: Mapped[Real | None]


class ActivityLap(Base):
    __tablename__ = "activity_lap"
    __table_args__ = {"comment": "Laps (manual or auto) as recorded by the device."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    lap_index: Mapped[Small] = mapped_column(primary_key=True)
    start_time_utc: Mapped[TsTz | None]
    duration_s: Mapped[float | None]
    moving_s: Mapped[float | None]
    distance_m: Mapped[float | None]
    avg_speed_mps: Mapped[Real | None]
    max_speed_mps: Mapped[Real | None]
    avg_hr: Mapped[Small | None]
    max_hr: Mapped[Small | None]
    avg_cadence: Mapped[Real | None]
    avg_power_w: Mapped[Real | None]
    max_power_w: Mapped[Real | None]
    normalized_power_w: Mapped[Real | None]
    elevation_gain_m: Mapped[Real | None]
    elevation_loss_m: Mapped[Real | None]
    calories: Mapped[Real | None]
    intensity: Mapped[str | None] = mapped_column(comment="active | rest | warmup | cooldown ...")


class ActivitySplit(Base):
    __tablename__ = "activity_split"
    __table_args__ = {"comment": "Even km/mile splits computed by Garminizer from samples."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    unit: Mapped[str] = mapped_column(primary_key=True, comment="km | mi")
    split_index: Mapped[Small] = mapped_column(primary_key=True)
    distance_m: Mapped[float]
    duration_s: Mapped[float]
    avg_hr: Mapped[Real | None]
    avg_cadence: Mapped[Real | None]
    avg_power_w: Mapped[Real | None]
    elevation_gain_m: Mapped[Real | None]
    elevation_loss_m: Mapped[Real | None]


class ActivityZone(Base):
    __tablename__ = "activity_zone"
    __table_args__ = {"comment": "Time spent in heart-rate / power zones per activity."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    kind: Mapped[str] = mapped_column(primary_key=True, comment="hr | power")
    zone: Mapped[Small] = mapped_column(primary_key=True, comment="1-5 (or 1-7 for power)")
    seconds: Mapped[float]
    low_value: Mapped[Real | None] = mapped_column(comment="Zone floor in bpm or W")


class ActivityWeather(Base):
    __tablename__ = "activity_weather"
    __table_args__ = {"comment": "Weather at the activity start (from Garmin)."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    issued_at: Mapped[TsTz | None]
    temperature_c: Mapped[Real | None]
    apparent_temperature_c: Mapped[Real | None]
    dew_point_c: Mapped[Real | None]
    humidity_pct: Mapped[Real | None]
    wind_speed_mps: Mapped[Real | None]
    wind_gust_mps: Mapped[Real | None]
    wind_direction_deg: Mapped[Real | None]
    condition: Mapped[str | None]


class ActivityFile(Base):
    __tablename__ = "activity_file"
    __table_args__ = {"comment": "Original activity files as downloaded (zip containing FIT)."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    file_format: Mapped[str] = mapped_column(server_default="fit_zip")
    content: Mapped[bytes] = mapped_column(LargeBinary)
    size_bytes: Mapped[int]
    sha256: Mapped[str]
    fetched_at: Mapped[datetime]
