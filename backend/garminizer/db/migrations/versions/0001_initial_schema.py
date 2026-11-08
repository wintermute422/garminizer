"""initial schema: raw payloads, activities, wellness, performance, body, sync bookkeeping

Revision ID: 0001
Revises:
Create Date: 2026-11-08 12:58:12.414481
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS garmin")
    op.create_table(
        "activity",
        sa.Column("activity_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "sport_type", sa.Text(), nullable=False, comment="Garmin typeKey, e.g. trail_running"
        ),
        sa.Column(
            "sport_group",
            sa.Text(),
            nullable=False,
            comment="run | ride | swim | walk | hike | strength | cardio | winter | water | other",
        ),
        sa.Column("start_time_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("start_time_local", sa.DateTime(), nullable=False),
        sa.Column("duration_s", sa.Double(), nullable=True),
        sa.Column("elapsed_s", sa.Double(), nullable=True),
        sa.Column("moving_s", sa.Double(), nullable=True),
        sa.Column("distance_m", sa.Double(), nullable=True),
        sa.Column("elevation_gain_m", sa.REAL(), nullable=True),
        sa.Column("elevation_loss_m", sa.REAL(), nullable=True),
        sa.Column("min_elevation_m", sa.REAL(), nullable=True),
        sa.Column("max_elevation_m", sa.REAL(), nullable=True),
        sa.Column("avg_speed_mps", sa.REAL(), nullable=True),
        sa.Column("max_speed_mps", sa.REAL(), nullable=True),
        sa.Column("avg_hr", sa.SmallInteger(), nullable=True),
        sa.Column("max_hr", sa.SmallInteger(), nullable=True),
        sa.Column("avg_cadence", sa.REAL(), nullable=True, comment="steps/min (run) or rpm (ride)"),
        sa.Column("max_cadence", sa.REAL(), nullable=True),
        sa.Column("avg_power_w", sa.REAL(), nullable=True),
        sa.Column("max_power_w", sa.REAL(), nullable=True),
        sa.Column("normalized_power_w", sa.REAL(), nullable=True),
        sa.Column("training_stress_score", sa.REAL(), nullable=True),
        sa.Column("intensity_factor", sa.REAL(), nullable=True),
        sa.Column("calories", sa.REAL(), nullable=True),
        sa.Column("aerobic_te", sa.REAL(), nullable=True, comment="Aerobic training effect 0-5"),
        sa.Column(
            "anaerobic_te", sa.REAL(), nullable=True, comment="Anaerobic training effect 0-5"
        ),
        sa.Column("training_effect_label", sa.Text(), nullable=True),
        sa.Column(
            "training_load", sa.REAL(), nullable=True, comment="Garmin activity training load"
        ),
        sa.Column(
            "trimp", sa.REAL(), nullable=True, comment="Banister TRIMP (computed by Garminizer)"
        ),
        sa.Column("vo2max", sa.REAL(), nullable=True),
        sa.Column("avg_temperature_c", sa.REAL(), nullable=True),
        sa.Column("min_temperature_c", sa.REAL(), nullable=True),
        sa.Column("max_temperature_c", sa.REAL(), nullable=True),
        sa.Column("avg_respiration", sa.REAL(), nullable=True),
        sa.Column("avg_stride_length_m", sa.REAL(), nullable=True),
        sa.Column("avg_vertical_oscillation_cm", sa.REAL(), nullable=True),
        sa.Column("avg_ground_contact_ms", sa.REAL(), nullable=True),
        sa.Column("avg_vertical_ratio", sa.REAL(), nullable=True),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("lap_count", sa.SmallInteger(), nullable=True),
        sa.Column("pool_length_m", sa.REAL(), nullable=True),
        sa.Column("active_lengths", sa.SmallInteger(), nullable=True),
        sa.Column("strokes", sa.REAL(), nullable=True),
        sa.Column("avg_swolf", sa.REAL(), nullable=True),
        sa.Column("total_sets", sa.SmallInteger(), nullable=True),
        sa.Column("total_reps", sa.SmallInteger(), nullable=True),
        sa.Column("moderate_intensity_min", sa.SmallInteger(), nullable=True),
        sa.Column("vigorous_intensity_min", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_delta", sa.SmallInteger(), nullable=True),
        sa.Column("water_estimated_ml", sa.REAL(), nullable=True),
        sa.Column("start_lat", sa.Double(), nullable=True),
        sa.Column("start_lon", sa.Double(), nullable=True),
        sa.Column("end_lat", sa.Double(), nullable=True),
        sa.Column("end_lon", sa.Double(), nullable=True),
        sa.Column("location_name", sa.Text(), nullable=True),
        sa.Column("device_id", sa.BigInteger(), nullable=True),
        sa.Column("is_manual", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_favorite", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "has_samples",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="True when per-second samples were ingested",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("activity_id", name=op.f("pk_activity")),
        schema="garmin",
        comment="One row per recorded activity (summary values).",
    )
    op.create_index(
        op.f("ix_activity_sport_group_start_time_utc"),
        "activity",
        ["sport_group", "start_time_utc"],
        unique=False,
        schema="garmin",
    )
    op.create_index(
        op.f("ix_activity_start_time_utc"),
        "activity",
        ["start_time_utc"],
        unique=False,
        schema="garmin",
    )
    op.create_table(
        "app_setting",
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_app_setting")),
        schema="garmin",
        comment="Key/value settings changed from the UI.",
    )
    op.create_table(
        "athlete",
        sa.Column("id", sa.SmallInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "profile_id", sa.BigInteger(), nullable=True, comment="Garmin user profile number"
        ),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=True),
        sa.Column("gender", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("height_cm", sa.REAL(), nullable=True),
        sa.Column("weight_kg", sa.REAL(), nullable=True),
        sa.Column("max_hr", sa.SmallInteger(), nullable=True),
        sa.Column("resting_hr", sa.SmallInteger(), nullable=True),
        sa.Column("lactate_threshold_hr", sa.SmallInteger(), nullable=True),
        sa.Column("lactate_threshold_speed_mps", sa.REAL(), nullable=True),
        sa.Column(
            "ftp_w",
            sa.SmallInteger(),
            nullable=True,
            comment="Functional threshold power (cycling)",
        ),
        sa.Column("vo2max_running", sa.REAL(), nullable=True),
        sa.Column("vo2max_cycling", sa.REAL(), nullable=True),
        sa.Column(
            "unit_system",
            sa.Text(),
            server_default="metric",
            nullable=False,
            comment="metric | statute",
        ),
        sa.Column("time_zone", sa.Text(), nullable=True, comment="IANA zone, e.g. Europe/Berlin"),
        sa.Column(
            "hr_zones",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Heart-rate zone floors (bpm)",
        ),
        sa.Column(
            "power_zones",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Power zone floors (W)",
        ),
        sa.Column(
            "is_demo",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="True when generated by `garminizer demo seed`",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_athlete")),
        schema="garmin",
        comment="The athlete profile (one row; id is always 1).",
    )
    op.create_table(
        "badge",
        sa.Column("badge_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("points", sa.SmallInteger(), nullable=True),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("earned_count", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("badge_id", name=op.f("pk_badge")),
        schema="garmin",
        comment="Earned Garmin badges.",
    )
    op.create_table(
        "blood_pressure",
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("systolic", sa.SmallInteger(), nullable=False),
        sa.Column("diastolic", sa.SmallInteger(), nullable=False),
        sa.Column("pulse", sa.SmallInteger(), nullable=True),
        sa.Column("category", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("measured_at", name=op.f("pk_blood_pressure")),
        schema="garmin",
        comment="Blood pressure readings.",
    )
    op.create_table(
        "body_battery_sample",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_body_battery_sample")),
        schema="garmin",
        comment="All-day Body Battery level 0-100.",
    )
    op.create_table(
        "body_composition",
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("weight_kg", sa.REAL(), nullable=False),
        sa.Column("bmi", sa.REAL(), nullable=True),
        sa.Column("body_fat_pct", sa.REAL(), nullable=True),
        sa.Column("body_water_pct", sa.REAL(), nullable=True),
        sa.Column("muscle_mass_kg", sa.REAL(), nullable=True),
        sa.Column("bone_mass_kg", sa.REAL(), nullable=True),
        sa.Column("visceral_fat", sa.REAL(), nullable=True),
        sa.Column("metabolic_age", sa.REAL(), nullable=True),
        sa.Column("source", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("measured_at", name=op.f("pk_body_composition")),
        schema="garmin",
        comment="Weigh-ins (scale or manual).",
    )
    op.create_table(
        "daily_summary",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=True),
        sa.Column("step_goal", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Double(), nullable=True),
        sa.Column("floors_up", sa.REAL(), nullable=True),
        sa.Column("floors_down", sa.REAL(), nullable=True),
        sa.Column("floors_goal", sa.REAL(), nullable=True),
        sa.Column("total_kcal", sa.REAL(), nullable=True),
        sa.Column("active_kcal", sa.REAL(), nullable=True),
        sa.Column("bmr_kcal", sa.REAL(), nullable=True),
        sa.Column("resting_hr", sa.SmallInteger(), nullable=True),
        sa.Column("min_hr", sa.SmallInteger(), nullable=True),
        sa.Column("max_hr", sa.SmallInteger(), nullable=True),
        sa.Column("avg_stress", sa.SmallInteger(), nullable=True),
        sa.Column("max_stress", sa.SmallInteger(), nullable=True),
        sa.Column("stress_rest_s", sa.Integer(), nullable=True),
        sa.Column("stress_low_s", sa.Integer(), nullable=True),
        sa.Column("stress_medium_s", sa.Integer(), nullable=True),
        sa.Column("stress_high_s", sa.Integer(), nullable=True),
        sa.Column("body_battery_high", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_low", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_charged", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_drained", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_at_wake", sa.SmallInteger(), nullable=True),
        sa.Column("moderate_intensity_min", sa.SmallInteger(), nullable=True),
        sa.Column("vigorous_intensity_min", sa.SmallInteger(), nullable=True),
        sa.Column("intensity_goal_min", sa.SmallInteger(), nullable=True),
        sa.Column("avg_spo2", sa.REAL(), nullable=True),
        sa.Column("lowest_spo2", sa.REAL(), nullable=True),
        sa.Column("avg_waking_respiration", sa.REAL(), nullable=True),
        sa.Column("hydration_ml", sa.REAL(), nullable=True),
        sa.Column("hydration_goal_ml", sa.REAL(), nullable=True),
        sa.Column("sedentary_s", sa.Integer(), nullable=True),
        sa.Column("active_s", sa.Integer(), nullable=True),
        sa.Column("highly_active_s", sa.Integer(), nullable=True),
        sa.Column("sleeping_s", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_daily_summary")),
        schema="garmin",
        comment="One row per calendar day (athlete's local date).",
    )
    op.create_table(
        "device",
        sa.Column("device_id", sa.BigInteger(), nullable=False),
        sa.Column("product_name", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("software_version", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("device_id", name=op.f("pk_device")),
        schema="garmin",
        comment="Garmin devices that recorded data.",
    )
    op.create_table(
        "endurance_score",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("classification", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_endurance_score")),
        schema="garmin",
        comment="Garmin endurance score.",
    )
    op.create_table(
        "gear",
        sa.Column("uuid", sa.Text(), nullable=False),
        sa.Column("gear_type", sa.Text(), nullable=False, comment="shoes | bike | other"),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("make", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.Text(), server_default="active", nullable=False, comment="active | retired"
        ),
        sa.Column("date_begin", sa.Date(), nullable=True),
        sa.Column("date_end", sa.Date(), nullable=True),
        sa.Column("max_distance_m", sa.Double(), nullable=True, comment="Retirement threshold"),
        sa.Column("total_distance_m", sa.Double(), nullable=True),
        sa.Column("total_activities", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("uuid", name=op.f("pk_gear")),
        schema="garmin",
        comment="Shoes, bikes and other equipment tracked in Garmin Connect.",
    )
    op.create_table(
        "goal",
        sa.Column("goal_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("goal_type", sa.Text(), nullable=False),
        sa.Column("target_value", sa.Double(), nullable=True),
        sa.Column("start_day", sa.Date(), nullable=True),
        sa.Column("end_day", sa.Date(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("goal_id", name=op.f("pk_goal")),
        schema="garmin",
        comment="Goals set in Garmin Connect.",
    )
    op.create_table(
        "hill_score",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("endurance", sa.REAL(), nullable=True),
        sa.Column("strength", sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_hill_score")),
        schema="garmin",
        comment="Garmin hill score with its endurance/strength parts.",
    )
    op.create_table(
        "hr_sample",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bpm", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_hr_sample")),
        schema="garmin",
        comment="All-day heart rate (about every 2 minutes).",
    )
    op.create_table(
        "hrv_daily",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("last_night_avg_ms", sa.REAL(), nullable=True),
        sa.Column("last_night_5min_high_ms", sa.REAL(), nullable=True),
        sa.Column("weekly_avg_ms", sa.REAL(), nullable=True),
        sa.Column("baseline_low_ms", sa.REAL(), nullable=True),
        sa.Column("baseline_balanced_low_ms", sa.REAL(), nullable=True),
        sa.Column("baseline_balanced_upper_ms", sa.REAL(), nullable=True),
        sa.Column("status", sa.Text(), nullable=True, comment="BALANCED | UNBALANCED | LOW | POOR"),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_hrv_daily")),
        schema="garmin",
        comment="Overnight heart-rate variability summary.",
    )
    op.create_table(
        "max_metric",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("vo2max_running", sa.REAL(), nullable=True),
        sa.Column("vo2max_cycling", sa.REAL(), nullable=True),
        sa.Column("fitness_age", sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_max_metric")),
        schema="garmin",
        comment="VO2max estimates and fitness age.",
    )
    op.create_table(
        "personal_record",
        sa.Column("record_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("type_id", sa.Integer(), nullable=False),
        sa.Column(
            "type_key",
            sa.Text(),
            nullable=False,
            comment="e.g. run_5k, longest_ride, most_steps_day",
        ),
        sa.Column(
            "value", sa.Double(), nullable=False, comment="Seconds for times, metres, steps ..."
        ),
        sa.Column("activity_id", sa.BigInteger(), nullable=True),
        sa.Column("achieved_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("record_id", name=op.f("pk_personal_record")),
        schema="garmin",
        comment="Personal records as tracked by Garmin.",
    )
    op.create_table(
        "race_prediction",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("time_5k_s", sa.REAL(), nullable=True),
        sa.Column("time_10k_s", sa.REAL(), nullable=True),
        sa.Column("time_half_s", sa.REAL(), nullable=True),
        sa.Column("time_marathon_s", sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_race_prediction")),
        schema="garmin",
        comment="Predicted race times (seconds).",
    )
    op.create_table(
        "raw_payload",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "dataset",
            sa.Text(),
            nullable=False,
            comment="Logical dataset, e.g. sleep, activity_details",
        ),
        sa.Column(
            "key", sa.Text(), nullable=False, comment="Day (YYYY-MM-DD), activity id or range key"
        ),
        sa.Column(
            "endpoint", sa.Text(), nullable=False, comment="Client method that produced the payload"
        ),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="JSON body (null = empty)",
        ),
        sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("parse_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_payload")),
        sa.UniqueConstraint("dataset", "key", name=op.f("uq_raw_payload_dataset_key")),
        schema="garmin",
        comment="Verbatim Garmin API responses; `garminizer reparse` rebuilds from these.",
    )
    op.create_index(
        op.f("ix_raw_payload_parsed_at"),
        "raw_payload",
        ["parsed_at"],
        unique=False,
        schema="garmin",
        postgresql_where=sa.text("parsed_at IS NULL"),
    )
    op.create_table(
        "respiration_sample",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breaths_per_min", sa.REAL(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_respiration_sample")),
        schema="garmin",
        comment="All-day respiration rate (breaths/min).",
    )
    op.create_table(
        "sleep",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("start_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Integer(), nullable=True),
        sa.Column("deep_s", sa.Integer(), nullable=True),
        sa.Column("light_s", sa.Integer(), nullable=True),
        sa.Column("rem_s", sa.Integer(), nullable=True),
        sa.Column("awake_s", sa.Integer(), nullable=True),
        sa.Column("unmeasurable_s", sa.Integer(), nullable=True),
        sa.Column("score", sa.SmallInteger(), nullable=True, comment="Overall sleep score 0-100"),
        sa.Column(
            "score_quality", sa.Text(), nullable=True, comment="EXCELLENT | GOOD | FAIR | POOR"
        ),
        sa.Column("score_duration", sa.SmallInteger(), nullable=True),
        sa.Column("score_deep", sa.SmallInteger(), nullable=True),
        sa.Column("score_rem", sa.SmallInteger(), nullable=True),
        sa.Column("score_light", sa.SmallInteger(), nullable=True),
        sa.Column("score_awakenings", sa.SmallInteger(), nullable=True),
        sa.Column("score_stress", sa.SmallInteger(), nullable=True),
        sa.Column("avg_hr", sa.REAL(), nullable=True),
        sa.Column("lowest_hr", sa.SmallInteger(), nullable=True),
        sa.Column("avg_respiration", sa.REAL(), nullable=True),
        sa.Column("lowest_respiration", sa.REAL(), nullable=True),
        sa.Column("highest_respiration", sa.REAL(), nullable=True),
        sa.Column("avg_spo2", sa.REAL(), nullable=True),
        sa.Column("lowest_spo2", sa.REAL(), nullable=True),
        sa.Column("avg_stress", sa.REAL(), nullable=True),
        sa.Column("avg_overnight_hrv", sa.REAL(), nullable=True),
        sa.Column("restless_moments", sa.SmallInteger(), nullable=True),
        sa.Column("awake_count", sa.SmallInteger(), nullable=True),
        sa.Column("body_battery_change", sa.SmallInteger(), nullable=True),
        sa.Column("sleep_need_min", sa.SmallInteger(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_sleep")),
        schema="garmin",
        comment="One row per night, keyed by the wake-up day.",
    )
    op.create_table(
        "sleep_stage",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False, comment="deep | light | rem | awake"),
        sa.PrimaryKeyConstraint("day", "start_utc", name=op.f("pk_sleep_stage")),
        schema="garmin",
        comment="Hypnogram: sleep stage intervals per night.",
    )
    op.create_table(
        "spo2_sample",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("spo2_pct", sa.REAL(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_spo2_sample")),
        schema="garmin",
        comment="Pulse-ox readings (%).",
    )
    op.create_table(
        "steps_interval",
        sa.Column("start_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("steps", sa.Integer(), nullable=False),
        sa.Column(
            "activity_level",
            sa.Text(),
            nullable=True,
            comment="sedentary | active | highlyActive | sleeping | none",
        ),
        sa.PrimaryKeyConstraint("start_utc", name=op.f("pk_steps_interval")),
        schema="garmin",
        comment="Steps per 15-minute interval with activity level.",
    )
    op.create_table(
        "stress_sample",
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("level", sa.SmallInteger(), nullable=False),
        sa.PrimaryKeyConstraint("ts", name=op.f("pk_stress_sample")),
        schema="garmin",
        comment="All-day stress level 0-100; -1 = not enough data, -2 = activity.",
    )
    op.create_table(
        "sync_cursor",
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column("oldest_day", sa.Date(), nullable=True, comment="Backfill has reached this day"),
        sa.Column(
            "newest_day", sa.Date(), nullable=True, comment="Incremental sync reached this day"
        ),
        sa.Column(
            "complete",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="Backfill reached the first day with data",
        ),
        sa.Column(
            "state",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="Dataset-specific resume state",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("dataset", name=op.f("pk_sync_cursor")),
        schema="garmin",
        comment="How far each dataset has been synced (resume point).",
    )
    op.create_table(
        "sync_run",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "kind", sa.Text(), nullable=False, comment="incremental | backfill | reparse | demo"
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default="running",
            nullable=False,
            comment="running | ok | error",
        ),
        sa.Column("requests", sa.Integer(), server_default="0", nullable=False),
        sa.Column("items_written", sa.Integer(), server_default="0", nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_run")),
        schema="garmin",
        comment="One row per sync/backfill/reparse run.",
    )
    op.create_table(
        "training_readiness",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=True),
        sa.Column(
            "level", sa.Text(), nullable=True, comment="PRIME | HIGH | MODERATE | LOW | POOR"
        ),
        sa.Column("sleep_score_factor", sa.SmallInteger(), nullable=True),
        sa.Column("recovery_time_min", sa.SmallInteger(), nullable=True),
        sa.Column("recovery_factor", sa.SmallInteger(), nullable=True),
        sa.Column("acwr_factor", sa.SmallInteger(), nullable=True),
        sa.Column("hrv_factor", sa.SmallInteger(), nullable=True),
        sa.Column("stress_history_factor", sa.SmallInteger(), nullable=True),
        sa.Column("sleep_history_factor", sa.SmallInteger(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_training_readiness")),
        schema="garmin",
        comment="Morning training readiness score and its factors.",
    )
    op.create_table(
        "training_status",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=True,
            comment="PEAKING | PRODUCTIVE | MAINTAINING | RECOVERY | UNPRODUCTIVE | DETRAINING ...",
        ),
        sa.Column("acute_load", sa.REAL(), nullable=True),
        sa.Column("chronic_load", sa.REAL(), nullable=True),
        sa.Column("acwr", sa.REAL(), nullable=True, comment="Acute:chronic workload ratio"),
        sa.Column("acwr_status", sa.Text(), nullable=True),
        sa.Column("load_low_aerobic", sa.REAL(), nullable=True),
        sa.Column("load_high_aerobic", sa.REAL(), nullable=True),
        sa.Column("load_anaerobic", sa.REAL(), nullable=True),
        sa.Column("target_low_aerobic_min", sa.REAL(), nullable=True),
        sa.Column("target_low_aerobic_max", sa.REAL(), nullable=True),
        sa.Column("target_high_aerobic_min", sa.REAL(), nullable=True),
        sa.Column("target_high_aerobic_max", sa.REAL(), nullable=True),
        sa.Column("target_anaerobic_min", sa.REAL(), nullable=True),
        sa.Column("target_anaerobic_max", sa.REAL(), nullable=True),
        sa.Column("load_balance_feedback", sa.Text(), nullable=True),
        sa.Column("heat_acclimation_pct", sa.REAL(), nullable=True),
        sa.Column("altitude_acclimation_m", sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_training_status")),
        schema="garmin",
        comment="Garmin training status and load balance per day.",
    )
    op.create_table(
        "activity_file",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("file_format", sa.Text(), server_default="fit_zip", nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_file_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", name=op.f("pk_activity_file")),
        schema="garmin",
        comment="Original activity files as downloaded (zip containing FIT).",
    )
    op.create_table(
        "activity_gear",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("gear_uuid", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_gear_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["gear_uuid"],
            ["garmin.gear.uuid"],
            name=op.f("fk_activity_gear_gear_uuid_gear"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "gear_uuid", name=op.f("pk_activity_gear")),
        schema="garmin",
        comment="Which gear was used in which activity.",
    )
    op.create_table(
        "activity_lap",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("lap_index", sa.SmallInteger(), nullable=False),
        sa.Column("start_time_utc", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_s", sa.Double(), nullable=True),
        sa.Column("moving_s", sa.Double(), nullable=True),
        sa.Column("distance_m", sa.Double(), nullable=True),
        sa.Column("avg_speed_mps", sa.REAL(), nullable=True),
        sa.Column("max_speed_mps", sa.REAL(), nullable=True),
        sa.Column("avg_hr", sa.SmallInteger(), nullable=True),
        sa.Column("max_hr", sa.SmallInteger(), nullable=True),
        sa.Column("avg_cadence", sa.REAL(), nullable=True),
        sa.Column("avg_power_w", sa.REAL(), nullable=True),
        sa.Column("max_power_w", sa.REAL(), nullable=True),
        sa.Column("normalized_power_w", sa.REAL(), nullable=True),
        sa.Column("elevation_gain_m", sa.REAL(), nullable=True),
        sa.Column("elevation_loss_m", sa.REAL(), nullable=True),
        sa.Column("calories", sa.REAL(), nullable=True),
        sa.Column(
            "intensity", sa.Text(), nullable=True, comment="active | rest | warmup | cooldown ..."
        ),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_lap_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "lap_index", name=op.f("pk_activity_lap")),
        schema="garmin",
        comment="Laps (manual or auto) as recorded by the device.",
    )
    op.create_table(
        "activity_sample",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("t_s", sa.Integer(), nullable=False, comment="Seconds since activity start"),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lat", sa.Double(), nullable=True),
        sa.Column("lon", sa.Double(), nullable=True),
        sa.Column("altitude_m", sa.REAL(), nullable=True),
        sa.Column("distance_m", sa.Double(), nullable=True),
        sa.Column("speed_mps", sa.REAL(), nullable=True),
        sa.Column("hr", sa.SmallInteger(), nullable=True),
        sa.Column("cadence", sa.SmallInteger(), nullable=True),
        sa.Column("power_w", sa.SmallInteger(), nullable=True),
        sa.Column("temperature_c", sa.REAL(), nullable=True),
        sa.Column("vertical_oscillation_cm", sa.REAL(), nullable=True),
        sa.Column("ground_contact_ms", sa.REAL(), nullable=True),
        sa.Column("stride_length_m", sa.REAL(), nullable=True),
        sa.Column("respiration_rate", sa.REAL(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_sample_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "t_s", name=op.f("pk_activity_sample")),
        schema="garmin",
        comment="Per-record samples from the activity's FIT file.",
    )
    op.create_table(
        "activity_split",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False, comment="km | mi"),
        sa.Column("split_index", sa.SmallInteger(), nullable=False),
        sa.Column("distance_m", sa.Double(), nullable=False),
        sa.Column("duration_s", sa.Double(), nullable=False),
        sa.Column("avg_hr", sa.REAL(), nullable=True),
        sa.Column("avg_cadence", sa.REAL(), nullable=True),
        sa.Column("avg_power_w", sa.REAL(), nullable=True),
        sa.Column("elevation_gain_m", sa.REAL(), nullable=True),
        sa.Column("elevation_loss_m", sa.REAL(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_split_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "activity_id", "unit", "split_index", name=op.f("pk_activity_split")
        ),
        schema="garmin",
        comment="Even km/mile splits computed by Garminizer from samples.",
    )
    op.create_table(
        "activity_weather",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("temperature_c", sa.REAL(), nullable=True),
        sa.Column("apparent_temperature_c", sa.REAL(), nullable=True),
        sa.Column("dew_point_c", sa.REAL(), nullable=True),
        sa.Column("humidity_pct", sa.REAL(), nullable=True),
        sa.Column("wind_speed_mps", sa.REAL(), nullable=True),
        sa.Column("wind_gust_mps", sa.REAL(), nullable=True),
        sa.Column("wind_direction_deg", sa.REAL(), nullable=True),
        sa.Column("condition", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_weather_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", name=op.f("pk_activity_weather")),
        schema="garmin",
        comment="Weather at the activity start (from Garmin).",
    )
    op.create_table(
        "activity_zone",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, comment="hr | power"),
        sa.Column("zone", sa.SmallInteger(), nullable=False, comment="1-5 (or 1-7 for power)"),
        sa.Column("seconds", sa.Double(), nullable=False),
        sa.Column("low_value", sa.REAL(), nullable=True, comment="Zone floor in bpm or W"),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_zone_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "kind", "zone", name=op.f("pk_activity_zone")),
        schema="garmin",
        comment="Time spent in heart-rate / power zones per activity.",
    )
    op.create_table(
        "sync_error",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.BigInteger(), nullable=True),
        sa.Column("dataset", sa.Text(), nullable=False),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["garmin.sync_run.id"],
            name=op.f("fk_sync_error_run_id_sync_run"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sync_error")),
        schema="garmin",
        comment="Errors during sync (kept for diagnosis, values redacted).",
    )


def downgrade() -> None:
    op.drop_table("sync_error", schema="garmin")
    op.drop_table("activity_zone", schema="garmin")
    op.drop_table("activity_weather", schema="garmin")
    op.drop_table("activity_split", schema="garmin")
    op.drop_table("activity_sample", schema="garmin")
    op.drop_table("activity_lap", schema="garmin")
    op.drop_table("activity_gear", schema="garmin")
    op.drop_table("activity_file", schema="garmin")
    op.drop_table("training_status", schema="garmin")
    op.drop_table("training_readiness", schema="garmin")
    op.drop_table("sync_run", schema="garmin")
    op.drop_table("sync_cursor", schema="garmin")
    op.drop_table("stress_sample", schema="garmin")
    op.drop_table("steps_interval", schema="garmin")
    op.drop_table("spo2_sample", schema="garmin")
    op.drop_table("sleep_stage", schema="garmin")
    op.drop_table("sleep", schema="garmin")
    op.drop_table("respiration_sample", schema="garmin")
    op.drop_index(
        op.f("ix_raw_payload_parsed_at"),
        table_name="raw_payload",
        schema="garmin",
        postgresql_where=sa.text("parsed_at IS NULL"),
    )
    op.drop_table("raw_payload", schema="garmin")
    op.drop_table("race_prediction", schema="garmin")
    op.drop_table("personal_record", schema="garmin")
    op.drop_table("max_metric", schema="garmin")
    op.drop_table("hrv_daily", schema="garmin")
    op.drop_table("hr_sample", schema="garmin")
    op.drop_table("hill_score", schema="garmin")
    op.drop_table("goal", schema="garmin")
    op.drop_table("gear", schema="garmin")
    op.drop_table("endurance_score", schema="garmin")
    op.drop_table("device", schema="garmin")
    op.drop_table("daily_summary", schema="garmin")
    op.drop_table("body_composition", schema="garmin")
    op.drop_table("body_battery_sample", schema="garmin")
    op.drop_table("blood_pressure", schema="garmin")
    op.drop_table("badge", schema="garmin")
    op.drop_table("athlete", schema="garmin")
    op.drop_table("app_setting", schema="garmin")
    op.drop_index(op.f("ix_activity_start_time_utc"), table_name="activity", schema="garmin")
    op.drop_index(
        op.f("ix_activity_sport_group_start_time_utc"), table_name="activity", schema="garmin"
    )
    op.drop_table("activity", schema="garmin")
