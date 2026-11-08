"""Declarative base, shared column types and the `garmin` schema metadata."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any

from sqlalchemy import REAL, BigInteger, Date, DateTime, Double, MetaData, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, mapped_column

SCHEMA = "garmin"

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Column types used throughout the models. REAL (4 bytes) is plenty for sensor values; DOUBLE
# is used for coordinates and cumulative distances.
Real = Annotated[float, mapped_column(REAL)]
Small = Annotated[int, mapped_column(SmallInteger)]
Big = Annotated[int, mapped_column(BigInteger)]
TsTz = Annotated[datetime, mapped_column(DateTime(timezone=True))]
Ts = Annotated[datetime, mapped_column(DateTime(timezone=False))]
Day = Annotated[date, mapped_column(Date)]


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy reads this class attribute
        str: Text(),
        float: Double(),
        datetime: DateTime(timezone=True),
        dict[str, Any]: JSONB(),
        list[Any]: JSONB(),
    }
