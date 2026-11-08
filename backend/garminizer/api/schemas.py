"""Response models shared by several routers (all units SI: m, s, m/s, kg, W, bpm)."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class Model(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class SystemHealth(Model):
    status: str
    version: str
    database: bool


class SportCount(Model):
    sport_group: str
    activities: int


class AthleteOut(Model):
    display_name: str | None
    is_demo: bool
    unit_system: str
    time_zone: str | None
    birth_date: date | None
    gender: str | None
    height_cm: float | None
    weight_kg: float | None
    max_hr: int | None
    resting_hr: int | None
    lactate_threshold_hr: int | None
    ftp_w: int | None
    vo2max_running: float | None
    vo2max_cycling: float | None
    hr_zones: list[float] | None


class Meta(Model):
    version: str
    athlete: AthleteOut | None
    first_day: date | None
    last_day: date | None
    activity_count: int
    sports: list[SportCount]
    last_sync_at: datetime | None
    map_style_url: str
    map_style_url_dark: str


class ActivitySummary(Model):
    activity_id: int
    name: str | None
    sport_type: str
    sport_group: str
    start_time_utc: datetime
    start_time_local: datetime
    duration_s: float | None
    moving_s: float | None
    distance_m: float | None
    elevation_gain_m: float | None
    avg_speed_mps: float | None
    avg_hr: int | None
    max_hr: int | None
    avg_power_w: float | None
    normalized_power_w: float | None
    calories: float | None
    training_load: float | None
    aerobic_te: float | None
    anaerobic_te: float | None
    training_effect_label: str | None
    vo2max: float | None
    location_name: str | None
    has_track: bool = False


class TimePoint(Model):
    day: date
    value: float | None
