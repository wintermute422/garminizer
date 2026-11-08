"""Meals and their food items: logged by the user (e.g. through Claude Desktop), not by Garmin."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from garminizer.db.base import Base, Big, Day, Real, Small, TsTz

MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "drink")
MEAL_SOURCES = ("claude", "manual", "demo")
CONFIDENCES = ("low", "medium", "high")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Meal(Base):
    __tablename__ = "meal"
    __table_args__ = (
        CheckConstraint(_in("meal_type", MEAL_TYPES), name="meal_type"),
        CheckConstraint(_in("source", MEAL_SOURCES), name="source"),
        CheckConstraint(_in("confidence", CONFIDENCES), name="confidence"),
        CheckConstraint("kcal >= 0", name="kcal_not_negative"),
        {"comment": "Meals and drinks with energy and macros (user input, e.g. Claude Desktop)."},
    )

    meal_id: Mapped[Big] = mapped_column(
        primary_key=True, autoincrement=True, comment="Meal number (generated)"
    )
    eaten_at: Mapped[TsTz] = mapped_column(comment="When the meal was eaten")
    day: Mapped[Day] = mapped_column(
        index=True, comment="Athlete's local calendar date of eaten_at"
    )
    meal_type: Mapped[str] = mapped_column(comment="breakfast | lunch | dinner | snack | drink")
    name: Mapped[str] = mapped_column(comment="Short description, e.g. 'Pasta with tomato sauce'")
    kcal: Mapped[Real] = mapped_column(comment="Energy (kcal)")
    protein_g: Mapped[Real | None] = mapped_column(comment="Protein (g)")
    carbs_g: Mapped[Real | None] = mapped_column(comment="Carbohydrates incl. sugar (g)")
    fat_g: Mapped[Real | None] = mapped_column(comment="Fat (g)")
    fiber_g: Mapped[Real | None] = mapped_column(comment="Dietary fibre (g)")
    sugar_g: Mapped[Real | None] = mapped_column(comment="Sugars, part of carbs_g (g)")
    saturated_fat_g: Mapped[Real | None] = mapped_column(comment="Saturated fat, part of fat_g (g)")
    sodium_mg: Mapped[Real | None] = mapped_column(comment="Sodium (mg); salt = sodium x 2.5")
    alcohol_g: Mapped[Real | None] = mapped_column(comment="Alcohol (g, 7 kcal/g)")
    water_ml: Mapped[Real | None] = mapped_column(comment="Water from drinks and food (ml)")
    notes: Mapped[str | None] = mapped_column(comment="Assumptions behind the estimate")
    source: Mapped[str] = mapped_column(comment="claude | manual | demo")
    confidence: Mapped[str | None] = mapped_column(
        comment="How sure the estimate is: low | medium | high"
    )
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="When the meal was logged"
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(), comment="Last change of the meal or its items"
    )

    items: Mapped[list[MealItem]] = relationship(
        order_by="MealItem.idx",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="selectin",
    )


class MealItem(Base):
    __tablename__ = "meal_item"
    __table_args__ = (
        CheckConstraint("kcal >= 0", name="kcal_not_negative"),
        {"comment": "Foods of a meal with portion and nutrients (meal totals are their sum)."},
    )

    meal_id: Mapped[Big] = mapped_column(
        ForeignKey("meal.meal_id", ondelete="CASCADE"),
        primary_key=True,
        comment="Meal this food belongs to",
    )
    idx: Mapped[Small] = mapped_column(primary_key=True, comment="Position in the meal (0-based)")
    food: Mapped[str] = mapped_column(comment="Food, e.g. 'Cooked spaghetti'")
    amount: Mapped[Real | None] = mapped_column(comment="Portion in `unit`, e.g. 1.5")
    unit: Mapped[str | None] = mapped_column(
        comment="Unit of amount, e.g. g, ml, piece, slice, tbsp"
    )
    grams: Mapped[Real | None] = mapped_column(comment="Portion weight (g)")
    kcal: Mapped[Real] = mapped_column(comment="Energy (kcal)")
    protein_g: Mapped[Real | None] = mapped_column(comment="Protein (g)")
    carbs_g: Mapped[Real | None] = mapped_column(comment="Carbohydrates (g)")
    fat_g: Mapped[Real | None] = mapped_column(comment="Fat (g)")
    fiber_g: Mapped[Real | None] = mapped_column(comment="Dietary fibre (g)")
