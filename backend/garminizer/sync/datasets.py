"""Registry of everything Garminizer fetches: scope, client method, arguments, parser, tables.

Scopes:
* static   - fetched once per run (profile, devices, gear, records, badges, goals); `keys`
             yields several raw keys for one dataset (e.g. one per gear item).
* activity - the paginated activity list; every list item is its own raw payload (key = id).
* detail   - per-activity requests (key = activity id), fetched for new/changed activities.
* daily    - one request per calendar day (key = YYYY-MM-DD).
* range    - one request per calendar month (key = YYYY-MM).

The registry order is also the parse order (reparse), so profile and activities come before
the rows that reference them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from garminconnect import Garmin
from sqlalchemy import select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.garmin.client import GarminClient, Identity
from garminizer.sync import parsers as p
from garminizer.sync.parsers.common import Parser

Scope = Literal["static", "activity", "detail", "daily", "range"]
Args = tuple[tuple[Any, ...], dict[str, Any]]
ACTIVITY_PAGE_SIZE = 50
GOAL_STATUSES = ("active", "future", "past")


@dataclass(frozen=True)
class Unit:
    """One unit of work: a raw key plus what the arguments are built from."""

    key: str
    day: date | None = None
    start: date | None = None
    end: date | None = None
    activity_id: int | None = None


@dataclass(frozen=True)
class FetchContext:
    today: date
    identity: Identity


def _no_args(unit: Unit, ctx: FetchContext) -> Args:
    return (), {}


def _day(unit: Unit, ctx: FetchContext) -> Args:
    assert unit.day is not None
    return (unit.day.isoformat(),), {}


def _range(unit: Unit, ctx: FetchContext) -> Args:
    assert unit.start is not None and unit.end is not None
    return (unit.start.isoformat(), unit.end.isoformat()), {}


def _range_daily_type(unit: Unit, ctx: FetchContext) -> Args:
    args, _ = _range(unit, ctx)
    return args, {"_type": "daily"}


def _range_daily_aggregation(unit: Unit, ctx: FetchContext) -> Args:
    args, _ = _range(unit, ctx)
    return args, {"aggregation": "daily"}


def _activity(unit: Unit, ctx: FetchContext) -> Args:
    assert unit.activity_id is not None
    return (str(unit.activity_id),), {}


def _download(unit: Unit, ctx: FetchContext) -> Args:
    args, _ = _activity(unit, ctx)
    return args, {"dl_fmt": Garmin.ActivityDownloadFormat.ORIGINAL}


def _page(unit: Unit, ctx: FetchContext) -> Args:
    """Activity list page: ``unit.key`` is the start index."""
    return (int(unit.key), ACTIVITY_PAGE_SIZE), {}


def _profile_number(unit: Unit, ctx: FetchContext) -> Args:
    return (str(ctx.identity.profile_id),), {}


def _key_arg(unit: Unit, ctx: FetchContext) -> Args:
    return (unit.key,), {}


def _goal_status(unit: Unit, ctx: FetchContext) -> Args:
    return (), {"status": unit.key}


def _gear_keys(session: Session) -> list[str]:
    return list(session.scalars(select(m.Gear.uuid).order_by(m.Gear.uuid)))


def _goal_keys(session: Session) -> list[str]:
    return list(GOAL_STATUSES)


@dataclass(frozen=True)
class Dataset:
    name: str
    scope: Scope
    method: str | None  # None: produced locally (identity from the login profile)
    parser: Parser
    tables: tuple[str, ...]  # every table the parser writes (enforced by a test)
    args: Callable[[Unit, FetchContext], Args] = _no_args
    keys: Callable[[Session], list[str]] | None = None
    requires_profile_id: bool = False
    binary: bool = False

    def fetch(self, client: GarminClient, unit: Unit, ctx: FetchContext) -> Any:
        """One Garmin request for ``unit`` (raises the client's GarminError subclasses)."""
        if self.method is None:
            raise ValueError(f"{self.name} is produced locally, not fetched")
        args, kwargs = self.args(unit, ctx)
        return client.call(self.method, *args, **kwargs)


REGISTRY: tuple[Dataset, ...] = (
    # --- static: profile, devices, gear, records ------------------------------------------
    Dataset("identity", "static", None, p.parse_identity, ("athlete",)),
    Dataset("user_settings", "static", "get_user_profile", p.parse_user_settings, ("athlete",)),
    Dataset(
        "personal_information",
        "static",
        "get_personal_information",
        p.parse_personal_information,
        ("athlete",),
    ),
    Dataset("profile_base", "static", "get_user_profile_base", p.parse_nothing, ()),
    Dataset("hr_zones", "static", "get_heart_rate_zones", p.parse_hr_zones, ("athlete",)),
    Dataset("devices", "static", "get_devices", p.parse_devices, ("device",)),
    Dataset(
        "device_last_used", "static", "get_device_last_used", p.parse_device_last_used, ("device",)
    ),
    Dataset(
        "gear",
        "static",
        "get_gear",
        p.parse_gear,
        ("gear",),
        args=_profile_number,
        requires_profile_id=True,
    ),
    Dataset(
        "gear_stats",
        "static",
        "get_gear_stats",
        p.parse_gear_stats,
        ("gear",),
        args=_key_arg,
        keys=_gear_keys,
    ),
    Dataset(
        "personal_records",
        "static",
        "get_personal_record",
        p.parse_personal_records,
        ("personal_record",),
    ),
    Dataset("badges", "static", "get_earned_badges", p.parse_badges, ("badge",)),
    Dataset(
        "goals", "static", "get_goals", p.parse_goals, ("goal",), args=_goal_status, keys=_goal_keys
    ),
    # --- activities -------------------------------------------------------------------------
    Dataset("activity", "activity", "get_activities", p.parse_activity, ("activity",), _page),
    Dataset(
        "activity_summary",
        "detail",
        "get_activity",
        p.parse_activity_summary,
        ("activity",),
        args=_activity,
    ),
    Dataset(
        "activity_splits",
        "detail",
        "get_activity_splits",
        p.parse_activity_splits,
        ("activity_lap",),
        args=_activity,
    ),
    Dataset(
        "activity_hr_zones",
        "detail",
        "get_activity_hr_in_timezones",
        p.parse_activity_hr_zones,
        ("activity_zone",),
        args=_activity,
    ),
    Dataset(
        "activity_weather",
        "detail",
        "get_activity_weather",
        p.parse_activity_weather,
        ("activity_weather",),
        args=_activity,
    ),
    Dataset(
        "activity_gear",
        "detail",
        "get_activity_gear",
        p.parse_activity_gear,
        ("activity_gear", "gear"),
        args=_activity,
    ),
    Dataset(
        "activity_file",
        "detail",
        "download_activity",
        p.parse_nothing,
        ("activity_file", "activity_sample"),
        args=_download,
        binary=True,
    ),
    # --- daily ------------------------------------------------------------------------------
    Dataset(
        "user_summary",
        "daily",
        "get_user_summary",
        p.parse_user_summary,
        ("daily_summary",),
        args=_day,
    ),
    Dataset(
        "hydration", "daily", "get_hydration_data", p.parse_hydration, ("daily_summary",), args=_day
    ),
    Dataset(
        "intensity_minutes",
        "daily",
        "get_intensity_minutes_data",
        p.parse_intensity_minutes,
        ("daily_summary",),
        args=_day,
    ),
    Dataset("sleep", "daily", "get_sleep_data", p.parse_sleep, ("sleep", "sleep_stage"), args=_day),
    Dataset("hrv", "daily", "get_hrv_data", p.parse_hrv, ("hrv_daily",), args=_day),
    Dataset(
        "heart_rates", "daily", "get_heart_rates", p.parse_heart_rates, ("hr_sample",), args=_day
    ),
    Dataset(
        "stress",
        "daily",
        "get_stress_data",
        p.parse_stress,
        ("stress_sample", "body_battery_sample"),
        args=_day,
    ),
    Dataset(
        "respiration",
        "daily",
        "get_respiration_data",
        p.parse_respiration,
        ("respiration_sample", "daily_summary"),
        args=_day,
    ),
    Dataset(
        "spo2", "daily", "get_spo2_data", p.parse_spo2, ("spo2_sample", "daily_summary"), args=_day
    ),
    Dataset("steps", "daily", "get_steps_data", p.parse_steps, ("steps_interval",), args=_day),
    Dataset(
        "training_readiness",
        "daily",
        "get_training_readiness",
        p.parse_training_readiness,
        ("training_readiness",),
        args=_day,
    ),
    Dataset(
        "training_status",
        "daily",
        "get_training_status",
        p.parse_training_status,
        ("training_status",),
        args=_day,
    ),
    Dataset(
        "max_metrics", "daily", "get_max_metrics", p.parse_max_metrics, ("max_metric",), args=_day
    ),
    # --- monthly ranges ---------------------------------------------------------------------
    Dataset(
        "body_composition",
        "range",
        "get_body_composition",
        p.parse_body_composition,
        ("body_composition",),
        args=_range,
    ),
    Dataset(
        "blood_pressure",
        "range",
        "get_blood_pressure",
        p.parse_blood_pressure,
        ("blood_pressure",),
        args=_range,
    ),
    Dataset(
        "race_predictions",
        "range",
        "get_race_predictions",
        p.parse_race_predictions,
        ("race_prediction",),
        args=_range_daily_type,
    ),
    Dataset(
        "endurance_score",
        "range",
        "get_endurance_score",
        p.parse_endurance_score,
        ("endurance_score",),
        args=_range_daily_aggregation,
    ),
    Dataset(
        "hill_score", "range", "get_hill_score", p.parse_hill_score, ("hill_score",), args=_range
    ),
)

DATASETS: dict[str, Dataset] = {d.name: d for d in REGISTRY}
PARSE_ORDER: dict[str, int] = {d.name: i for i, d in enumerate(REGISTRY)}


def by_scope(scope: Scope) -> tuple[Dataset, ...]:
    return tuple(d for d in REGISTRY if d.scope == scope)


STATIC = by_scope("static")
DETAIL = by_scope("detail")
DAILY = by_scope("daily")
RANGE = by_scope("range")
ACTIVITY = DATASETS["activity"]
