"""Body measurements, records, badges and goals."""

from __future__ import annotations

from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Big, Day, Real, Small, TsTz


class BodyComposition(Base):
    __tablename__ = "body_composition"
    __table_args__ = {"comment": "Weigh-ins (scale or manual)."}

    measured_at: Mapped[TsTz] = mapped_column(primary_key=True)
    weight_kg: Mapped[Real]
    bmi: Mapped[Real | None]
    body_fat_pct: Mapped[Real | None]
    body_water_pct: Mapped[Real | None]
    muscle_mass_kg: Mapped[Real | None]
    bone_mass_kg: Mapped[Real | None]
    visceral_fat: Mapped[Real | None]
    metabolic_age: Mapped[Real | None]
    source: Mapped[str | None]


class BloodPressure(Base):
    __tablename__ = "blood_pressure"
    __table_args__ = {"comment": "Blood pressure readings."}

    measured_at: Mapped[TsTz] = mapped_column(primary_key=True)
    systolic: Mapped[Small]
    diastolic: Mapped[Small]
    pulse: Mapped[Small | None]
    category: Mapped[str | None]


class PersonalRecord(Base):
    __tablename__ = "personal_record"
    __table_args__ = {"comment": "Personal records as tracked by Garmin."}

    record_id: Mapped[Big] = mapped_column(primary_key=True, autoincrement=False)
    type_id: Mapped[int]
    type_key: Mapped[str] = mapped_column(comment="e.g. run_5k, longest_ride, most_steps_day")
    value: Mapped[float] = mapped_column(comment="Seconds for times, metres, steps ...")
    activity_id: Mapped[Big | None]
    achieved_at: Mapped[TsTz | None]


class Badge(Base):
    __tablename__ = "badge"
    __table_args__ = {"comment": "Earned Garmin badges."}

    badge_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    name: Mapped[str]
    category: Mapped[str | None]
    points: Mapped[Small | None]
    earned_at: Mapped[TsTz | None]
    earned_count: Mapped[Small | None]


class Goal(Base):
    __tablename__ = "goal"
    __table_args__ = {"comment": "Goals set in Garmin Connect."}

    goal_id: Mapped[Big] = mapped_column(primary_key=True, autoincrement=False)
    goal_type: Mapped[str]
    target_value: Mapped[float | None]
    start_day: Mapped[Day | None]
    end_day: Mapped[Day | None]
    status: Mapped[str | None]
