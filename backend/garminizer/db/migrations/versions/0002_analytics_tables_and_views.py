"""analytics tables (best efforts, tracks, tiles, daily load) and SQL views

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-08 13:24:59.380944
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


VIEWS = {
    "weekly_volume": (
        "Training volume per ISO week and sport group.",
        """
        SELECT date_trunc('week', start_time_local)::date AS week, sport_group,
               count(*) AS activities, sum(distance_m) AS distance_m, sum(moving_s) AS moving_s,
               sum(duration_s) AS duration_s, sum(elevation_gain_m) AS elevation_gain_m,
               sum(training_load) AS training_load, sum(calories) AS calories
        FROM garmin.activity GROUP BY 1, 2
        """,
    ),
    "monthly_volume": (
        "Training volume per calendar month and sport group.",
        """
        SELECT date_trunc('month', start_time_local)::date AS month, sport_group,
               count(*) AS activities, sum(distance_m) AS distance_m, sum(moving_s) AS moving_s,
               sum(duration_s) AS duration_s, sum(elevation_gain_m) AS elevation_gain_m,
               sum(training_load) AS training_load, sum(calories) AS calories
        FROM garmin.activity GROUP BY 1, 2
        """,
    ),
    "explorer_tile": (
        "Every visited map tile with visit count and first/last visit (explorer squares).",
        """
        SELECT t.zoom, t.x, t.y, count(*) AS visits,
               min(a.start_time_utc) AS first_visit, max(a.start_time_utc) AS last_visit
        FROM garmin.activity_tile t JOIN garmin.activity a USING (activity_id)
        GROUP BY t.zoom, t.x, t.y
        """,
    ),
    "v_daily": (
        "One row per day with every daily metric side by side (for correlations).",
        """
        SELECT d.day, d.steps, d.resting_hr, d.avg_stress, d.body_battery_high,
               d.body_battery_low, d.body_battery_at_wake, d.active_kcal, d.total_kcal,
               d.moderate_intensity_min, d.vigorous_intensity_min, d.avg_spo2,
               s.duration_s AS sleep_s, s.deep_s AS sleep_deep_s, s.rem_s AS sleep_rem_s,
               s.score AS sleep_score, s.avg_overnight_hrv, h.last_night_avg_ms AS hrv_ms,
               h.weekly_avg_ms AS hrv_weekly_ms, h.status AS hrv_status,
               r.score AS readiness, t.status AS training_status, t.acwr AS garmin_acwr,
               l.load, l.ctl, l.atl, l.tsb, m.vo2max_running, w.weight_kg
        FROM garmin.daily_summary d
        LEFT JOIN garmin.sleep s USING (day)
        LEFT JOIN garmin.hrv_daily h USING (day)
        LEFT JOIN garmin.training_readiness r USING (day)
        LEFT JOIN garmin.training_status t USING (day)
        LEFT JOIN garmin.daily_load l USING (day)
        LEFT JOIN garmin.max_metric m USING (day)
        LEFT JOIN LATERAL (
            SELECT b.weight_kg FROM garmin.body_composition b
            WHERE b.measured_at::date <= d.day ORDER BY b.measured_at DESC LIMIT 1
        ) w ON true
        """,
    ),
}


def _create_views() -> None:
    for name, (comment, body) in VIEWS.items():
        op.execute(f"CREATE VIEW garmin.{name} AS {body}")
        op.execute(f"COMMENT ON VIEW garmin.{name} IS '{comment}'")


def _drop_views() -> None:
    for name in reversed(VIEWS):
        op.execute(f"DROP VIEW IF EXISTS garmin.{name}")


def upgrade() -> None:
    op.create_table(
        "daily_load",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column(
            "load", sa.REAL(), nullable=False, comment="Garmin training load (TRIMP when missing)"
        ),
        sa.Column("trimp", sa.REAL(), nullable=False),
        sa.Column("activities", sa.SmallInteger(), nullable=False),
        sa.Column(
            "ctl", sa.REAL(), nullable=False, comment="Chronic training load, 42-day EWMA (fitness)"
        ),
        sa.Column(
            "atl", sa.REAL(), nullable=False, comment="Acute training load, 7-day EWMA (fatigue)"
        ),
        sa.Column(
            "tsb",
            sa.REAL(),
            nullable=False,
            comment="Training stress balance = CTL - ATL of yesterday",
        ),
        sa.Column(
            "acwr", sa.REAL(), nullable=True, comment="Acute:chronic workload ratio (7/28 days)"
        ),
        sa.Column("monotony", sa.REAL(), nullable=True),
        sa.Column("strain", sa.REAL(), nullable=True),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_daily_load")),
        schema="garmin",
        comment="Training load per day with fitness (CTL), fatigue (ATL), form (TSB), ACWR.",
    )
    op.create_table(
        "activity_best_distance",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("distance_m", sa.Double(), nullable=False),
        sa.Column("seconds", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_best_distance_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "activity_id", "distance_m", name=op.f("pk_activity_best_distance")
        ),
        schema="garmin",
        comment="Fastest time over standard distances inside each run (e.g. best 5 km).",
    )
    op.create_index(
        op.f("ix_activity_best_distance_distance_m_seconds"),
        "activity_best_distance",
        ["distance_m", "seconds"],
        unique=False,
        schema="garmin",
    )
    op.create_table(
        "activity_best_effort",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False, comment="power (W) | speed (m/s) | hr"),
        sa.Column("duration_s", sa.Integer(), nullable=False),
        sa.Column("value", sa.REAL(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_best_effort_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "activity_id", "metric", "duration_s", name=op.f("pk_activity_best_effort")
        ),
        schema="garmin",
        comment="Mean-max: best average power/speed/HR over standard durations per activity.",
    )
    op.create_index(
        op.f("ix_activity_best_effort_metric_duration_s"),
        "activity_best_effort",
        ["metric", "duration_s"],
        unique=False,
        schema="garmin",
    )
    op.create_table(
        "activity_tile",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column("zoom", sa.SmallInteger(), nullable=False),
        sa.Column("x", sa.Integer(), nullable=False),
        sa.Column("y", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_tile_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", "zoom", "x", "y", name=op.f("pk_activity_tile")),
        schema="garmin",
        comment="Map tiles (slippy-map x/y) touched by each activity; see view explorer_tile.",
    )
    op.create_index(
        op.f("ix_activity_tile_zoom_x_y"),
        "activity_tile",
        ["zoom", "x", "y"],
        unique=False,
        schema="garmin",
    )
    op.create_table(
        "activity_track",
        sa.Column("activity_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "points",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            comment="[[lat, lon], ...] (Douglas-Peucker)",
        ),
        sa.Column("min_lat", sa.Double(), nullable=False),
        sa.Column("max_lat", sa.Double(), nullable=False),
        sa.Column("min_lon", sa.Double(), nullable=False),
        sa.Column("max_lon", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(
            ["activity_id"],
            ["garmin.activity.activity_id"],
            name=op.f("fk_activity_track_activity_id_activity"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("activity_id", name=op.f("pk_activity_track")),
        schema="garmin",
        comment="Simplified GPS track per activity for fast maps and heatmaps.",
    )
    op.add_column(
        "activity",
        sa.Column(
            "aerobic_decoupling_pct",
            sa.REAL(),
            nullable=True,
            comment="Pa:HR drift first vs second half (computed by Garminizer)",
        ),
        schema="garmin",
    )
    op.add_column(
        "activity",
        sa.Column(
            "efficiency_factor",
            sa.REAL(),
            nullable=True,
            comment="Output per heartbeat: (m/min or W) / bpm (computed by Garminizer)",
        ),
        schema="garmin",
    )
    op.add_column(
        "activity",
        sa.Column(
            "analytics_version",
            sa.SmallInteger(),
            server_default="0",
            nullable=False,
            comment="Version of the analytics that processed this activity",
        ),
        schema="garmin",
    )

    _create_views()


def downgrade() -> None:
    _drop_views()
    op.drop_column("activity", "analytics_version", schema="garmin")
    op.drop_column("activity", "efficiency_factor", schema="garmin")
    op.drop_column("activity", "aerobic_decoupling_pct", schema="garmin")
    op.drop_table("activity_track", schema="garmin")
    op.drop_index(op.f("ix_activity_tile_zoom_x_y"), table_name="activity_tile", schema="garmin")
    op.drop_table("activity_tile", schema="garmin")
    op.drop_index(
        op.f("ix_activity_best_effort_metric_duration_s"),
        table_name="activity_best_effort",
        schema="garmin",
    )
    op.drop_table("activity_best_effort", schema="garmin")
    op.drop_index(
        op.f("ix_activity_best_distance_distance_m_seconds"),
        table_name="activity_best_distance",
        schema="garmin",
    )
    op.drop_table("activity_best_distance", schema="garmin")
    op.drop_table("daily_load", schema="garmin")
