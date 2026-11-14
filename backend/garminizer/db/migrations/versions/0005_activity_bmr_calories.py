"""activity.bmr_calories: the resting share of an activity's calories (Garmin bmrCalories)

Garmin's activity ``calories`` are the total burned during the activity, resting energy
included. The weight goal's energy balance counts only the active part (calories minus
bmrCalories) on top of the daily resting + everyday baseline, so rest is not counted twice.
Rows synced before this column existed are filled from the stored raw activity payloads.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-14 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FILL_FROM_RAW = """
    UPDATE garmin.activity a
    SET bmr_calories = round((r.payload ->> 'bmrCalories')::numeric, 1)
    FROM garmin.raw_payload r
    WHERE r.dataset = 'activity'
      AND r.key = a.activity_id::text
      AND jsonb_typeof(r.payload) = 'object'
      AND CASE WHEN jsonb_typeof(r.payload -> 'bmrCalories') = 'number'
               THEN (r.payload ->> 'bmrCalories')::numeric > 0 ELSE false END
"""


def upgrade() -> None:
    op.add_column(
        "activity",
        sa.Column(
            "bmr_calories",
            sa.REAL(),
            nullable=True,
            comment="Resting calories during the activity (part of calories)",
        ),
        schema="garmin",
    )
    op.execute(FILL_FROM_RAW)


def downgrade() -> None:
    op.drop_column("activity", "bmr_calories", schema="garmin")
