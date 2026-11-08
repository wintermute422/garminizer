"""Tables computed by Garminizer's analytics pipeline (rebuildable from the core tables)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column

from garminizer.db.base import Base, Big, Day, Real, Small

_ACTIVITY_FK = "activity.activity_id"


class ActivityBestEffort(Base):
    __tablename__ = "activity_best_effort"
    __table_args__ = (
        Index(None, "metric", "duration_s"),
        {"comment": "Mean-max: best average power/speed/HR over standard durations per activity."},
    )

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    metric: Mapped[str] = mapped_column(primary_key=True, comment="power (W) | speed (m/s) | hr")
    duration_s: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[Real]


class ActivityBestDistance(Base):
    __tablename__ = "activity_best_distance"
    __table_args__ = (
        Index(None, "distance_m", "seconds"),
        {"comment": "Fastest time over standard distances inside each run (e.g. best 5 km)."},
    )

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    distance_m: Mapped[float] = mapped_column(primary_key=True)
    seconds: Mapped[float]


class ActivityTrack(Base):
    __tablename__ = "activity_track"
    __table_args__ = {"comment": "Simplified GPS track per activity for fast maps and heatmaps."}

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    points: Mapped[list[Any]] = mapped_column(comment="[[lat, lon], ...] (Douglas-Peucker)")
    min_lat: Mapped[float]
    max_lat: Mapped[float]
    min_lon: Mapped[float]
    max_lon: Mapped[float]


class ActivityTile(Base):
    __tablename__ = "activity_tile"
    __table_args__ = (
        Index(None, "zoom", "x", "y"),
        {"comment": "Map tiles (slippy-map x/y) touched by each activity; see view explorer_tile."},
    )

    activity_id: Mapped[Big] = mapped_column(
        ForeignKey(_ACTIVITY_FK, ondelete="CASCADE"), primary_key=True
    )
    zoom: Mapped[Small] = mapped_column(primary_key=True)
    x: Mapped[int] = mapped_column(primary_key=True)
    y: Mapped[int] = mapped_column(primary_key=True)


class DailyLoad(Base):
    __tablename__ = "daily_load"
    __table_args__ = {
        "comment": "Training load per day with fitness (CTL), fatigue (ATL), form (TSB), ACWR."
    }

    day: Mapped[Day] = mapped_column(primary_key=True)
    load: Mapped[Real] = mapped_column(comment="Garmin training load (TRIMP when missing)")
    trimp: Mapped[Real]
    activities: Mapped[Small]
    ctl: Mapped[Real] = mapped_column(comment="Chronic training load, 42-day EWMA (fitness)")
    atl: Mapped[Real] = mapped_column(comment="Acute training load, 7-day EWMA (fatigue)")
    tsb: Mapped[Real] = mapped_column(comment="Training stress balance = CTL - ATL of yesterday")
    acwr: Mapped[Real | None] = mapped_column(comment="Acute:chronic workload ratio (7/28 days)")
    monotony: Mapped[Real | None]
    strain: Mapped[Real | None]
