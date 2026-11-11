"""body_composition: 0 composition readings mean "not measured" → NULL

Garmin reports 0 for fat, water, BMI, muscle/bone mass, visceral fat and metabolic age when a
scale took no composition reading (or the weight was entered by hand). Earlier syncs stored
those zeros; the parser now maps them to None, and this clears the rows already stored.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-11 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CLEAR_ZERO_READINGS = """
    UPDATE garmin.body_composition SET
        bmi = NULLIF(GREATEST(bmi, 0), 0),
        body_fat_pct = NULLIF(GREATEST(body_fat_pct, 0), 0),
        body_water_pct = NULLIF(GREATEST(body_water_pct, 0), 0),
        muscle_mass_kg = NULLIF(GREATEST(muscle_mass_kg, 0), 0),
        bone_mass_kg = NULLIF(GREATEST(bone_mass_kg, 0), 0),
        visceral_fat = NULLIF(GREATEST(visceral_fat, 0), 0),
        metabolic_age = NULLIF(GREATEST(metabolic_age, 0), 0)
    WHERE bmi <= 0 OR body_fat_pct <= 0 OR body_water_pct <= 0 OR muscle_mass_kg <= 0
       OR bone_mass_kg <= 0 OR visceral_fat <= 0 OR metabolic_age <= 0
"""


def upgrade() -> None:
    op.execute(CLEAR_ZERO_READINGS)


def downgrade() -> None:
    """Nothing to restore: the zeros carried no information."""
