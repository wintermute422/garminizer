"""Shared SQL for activity queries: summary columns, moving time and the range/sport filter.

One place for what "an activity in the selected range and sport" and "activity time" mean, so
every dashboard counts the same activities and the same seconds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Annotated, Any

from fastapi import Depends

from garminizer.api.deps import RangeDep, SportDep

SUMMARY_COLUMNS = """
    a.activity_id, a.name, a.sport_type, a.sport_group, a.start_time_utc, a.start_time_local,
    a.duration_s, a.moving_s, a.distance_m, a.elevation_gain_m, a.avg_speed_mps, a.avg_hr,
    a.max_hr, a.avg_power_w, a.normalized_power_w, a.calories, a.training_load, a.aerobic_te,
    a.anaerobic_te, a.training_effect_label, a.vo2max, a.location_name,
    EXISTS (SELECT 1 FROM garmin.activity_track t WHERE t.activity_id = a.activity_id) AS has_track
"""


def moving_time(alias: str = "a") -> str:
    """Activity time everywhere: moving time, elapsed time when an activity has none."""
    p = f"{alias}." if alias else ""
    return f"coalesce({p}moving_s, {p}duration_s)"


@dataclass(frozen=True)
class ActivityFilter:
    """Activities whose local start day is within ``[start, end]``, optionally one sport group."""

    start: date
    end: date
    sport: str | None = None

    def sql(self, alias: str = "a") -> tuple[str, dict[str, Any]]:
        """``(where, params)``: a WHERE fragment with bound parameters (no user text inlined)."""
        p = f"{alias}." if alias else ""
        where = f"{p}start_time_local >= :start AND {p}start_time_local < :end_excl"
        params: dict[str, Any] = {
            "start": self.start,
            "end": self.end,
            "end_excl": self.end + timedelta(days=1),
        }
        sport, sport_params = self.sport_sql(alias)
        return where + sport, params | sport_params

    def sport_sql(self, alias: str = "a") -> tuple[str, dict[str, Any]]:
        """Only the sport part, ``" AND a.sport_group = :sport"`` (empty without a sport)."""
        return sport_only(self.sport, alias)


def sport_only(sport: str | None, alias: str = "a") -> tuple[str, dict[str, Any]]:
    """The sport filter alone, for queries with their own date logic (or none)."""
    if not sport:
        return "", {}
    p = f"{alias}." if alias else ""
    return f" AND {p}sport_group = :sport", {"sport": sport}


def activity_filter(rng: RangeDep, sport: SportDep) -> ActivityFilter:
    return ActivityFilter(rng.start, rng.end, sport)


ActivityFilterDep = Annotated[ActivityFilter, Depends(activity_filter)]
