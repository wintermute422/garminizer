"""nutrition: meals and food items (user input), intake columns in v_daily

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 15:10:43.029140
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

V_DAILY_COMMENT = "One row per day with every daily metric side by side (for correlations)."

# The v_daily definition of migration 0002 (restored by the downgrade).
V_DAILY_0002 = """
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
        """

# Same columns plus the logged intake at the end (CREATE OR REPLACE VIEW only appends columns).
# energy_balance_kcal = intake - Garmin's total burn; NULL on days without logged meals.
V_DAILY_0003 = """
        SELECT d.day, d.steps, d.resting_hr, d.avg_stress, d.body_battery_high,
               d.body_battery_low, d.body_battery_at_wake, d.active_kcal, d.total_kcal,
               d.moderate_intensity_min, d.vigorous_intensity_min, d.avg_spo2,
               s.duration_s AS sleep_s, s.deep_s AS sleep_deep_s, s.rem_s AS sleep_rem_s,
               s.score AS sleep_score, s.avg_overnight_hrv, h.last_night_avg_ms AS hrv_ms,
               h.weekly_avg_ms AS hrv_weekly_ms, h.status AS hrv_status,
               r.score AS readiness, t.status AS training_status, t.acwr AS garmin_acwr,
               l.load, l.ctl, l.atl, l.tsb, m.vo2max_running, w.weight_kg,
               n.intake_kcal, n.protein_g, n.carbs_g, n.fat_g,
               n.intake_kcal - d.total_kcal AS energy_balance_kcal
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
        LEFT JOIN (
            SELECT day, sum(kcal) AS intake_kcal, sum(protein_g) AS protein_g,
                   sum(carbs_g) AS carbs_g, sum(fat_g) AS fat_g
            FROM garmin.meal GROUP BY day
        ) n USING (day)
        """


def upgrade() -> None:
    op.create_table(
        "meal",
        sa.Column(
            "meal_id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
            comment="Meal number (generated)",
        ),
        sa.Column(
            "eaten_at",
            sa.DateTime(timezone=True),
            nullable=False,
            comment="When the meal was eaten",
        ),
        sa.Column(
            "day", sa.Date(), nullable=False, comment="Athlete's local calendar date of eaten_at"
        ),
        sa.Column(
            "meal_type",
            sa.Text(),
            nullable=False,
            comment="breakfast | lunch | dinner | snack | drink",
        ),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
            comment="Short description, e.g. 'Pasta with tomato sauce'",
        ),
        sa.Column("kcal", sa.REAL(), nullable=False, comment="Energy (kcal)"),
        sa.Column("protein_g", sa.REAL(), nullable=True, comment="Protein (g)"),
        sa.Column("carbs_g", sa.REAL(), nullable=True, comment="Carbohydrates incl. sugar (g)"),
        sa.Column("fat_g", sa.REAL(), nullable=True, comment="Fat (g)"),
        sa.Column("fiber_g", sa.REAL(), nullable=True, comment="Dietary fibre (g)"),
        sa.Column("sugar_g", sa.REAL(), nullable=True, comment="Sugars, part of carbs_g (g)"),
        sa.Column(
            "saturated_fat_g", sa.REAL(), nullable=True, comment="Saturated fat, part of fat_g (g)"
        ),
        sa.Column(
            "sodium_mg", sa.REAL(), nullable=True, comment="Sodium (mg); salt = sodium x 2.5"
        ),
        sa.Column("alcohol_g", sa.REAL(), nullable=True, comment="Alcohol (g, 7 kcal/g)"),
        sa.Column("water_ml", sa.REAL(), nullable=True, comment="Water from drinks and food (ml)"),
        sa.Column("notes", sa.Text(), nullable=True, comment="Assumptions behind the estimate"),
        sa.Column("source", sa.Text(), nullable=False, comment="claude | manual | demo"),
        sa.Column(
            "confidence",
            sa.Text(),
            nullable=True,
            comment="How sure the estimate is: low | medium | high",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="When the meal was logged",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
            comment="Last change of the meal or its items",
        ),
        sa.CheckConstraint(
            "confidence IN ('low', 'medium', 'high')", name=op.f("ck_meal_confidence")
        ),
        sa.CheckConstraint(
            "meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'drink')",
            name=op.f("ck_meal_meal_type"),
        ),
        sa.CheckConstraint("source IN ('claude', 'manual', 'demo')", name=op.f("ck_meal_source")),
        sa.CheckConstraint("kcal >= 0", name=op.f("ck_meal_kcal_not_negative")),
        sa.PrimaryKeyConstraint("meal_id", name=op.f("pk_meal")),
        schema="garmin",
        comment="Meals and drinks with energy and macros (user input, e.g. Claude Desktop).",
    )
    op.create_index(op.f("ix_meal_day"), "meal", ["day"], unique=False, schema="garmin")
    op.create_table(
        "meal_item",
        sa.Column("meal_id", sa.BigInteger(), nullable=False, comment="Meal this food belongs to"),
        sa.Column(
            "idx", sa.SmallInteger(), nullable=False, comment="Position in the meal (0-based)"
        ),
        sa.Column("food", sa.Text(), nullable=False, comment="Food, e.g. 'Cooked spaghetti'"),
        sa.Column("amount", sa.REAL(), nullable=True, comment="Portion in `unit`, e.g. 1.5"),
        sa.Column(
            "unit",
            sa.Text(),
            nullable=True,
            comment="Unit of amount, e.g. g, ml, piece, slice, tbsp",
        ),
        sa.Column("grams", sa.REAL(), nullable=True, comment="Portion weight (g)"),
        sa.Column("kcal", sa.REAL(), nullable=False, comment="Energy (kcal)"),
        sa.Column("protein_g", sa.REAL(), nullable=True, comment="Protein (g)"),
        sa.Column("carbs_g", sa.REAL(), nullable=True, comment="Carbohydrates (g)"),
        sa.Column("fat_g", sa.REAL(), nullable=True, comment="Fat (g)"),
        sa.Column("fiber_g", sa.REAL(), nullable=True, comment="Dietary fibre (g)"),
        sa.CheckConstraint("kcal >= 0", name=op.f("ck_meal_item_kcal_not_negative")),
        sa.ForeignKeyConstraint(
            ["meal_id"],
            ["garmin.meal.meal_id"],
            name=op.f("fk_meal_item_meal_id_meal"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("meal_id", "idx", name=op.f("pk_meal_item")),
        schema="garmin",
        comment="Foods of a meal with portion and nutrients (meal totals are their sum).",
    )
    op.execute(f"CREATE OR REPLACE VIEW garmin.v_daily AS {V_DAILY_0003}")
    op.execute(f"COMMENT ON VIEW garmin.v_daily IS '{V_DAILY_COMMENT}'")


def downgrade() -> None:
    # CREATE OR REPLACE cannot drop columns: rebuild the 0002 view before dropping its source.
    op.execute("DROP VIEW garmin.v_daily")
    op.execute(f"CREATE VIEW garmin.v_daily AS {V_DAILY_0002}")
    op.execute(f"COMMENT ON VIEW garmin.v_daily IS '{V_DAILY_COMMENT}'")
    op.drop_table("meal_item", schema="garmin")
    op.drop_index(op.f("ix_meal_day"), table_name="meal", schema="garmin")
    op.drop_table("meal", schema="garmin")
