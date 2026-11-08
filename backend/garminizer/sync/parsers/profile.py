"""Profile, settings, heart-rate zones, devices and gear."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from garminizer import models as m
from garminizer.sync.parsers.common import (
    ParseContext,
    Patch,
    RowOp,
    Upsert,
    day_of,
    dedupe,
    dicts,
    dig,
    first,
    grams_to_kg,
    has_values,
    integer,
    num,
    obj_or_empty,
    positive,
    rnd,
    small,
    text,
    ts_utc,
)

ATHLETE_ID = 1
GEAR_TYPES = {"shoes": "shoes", "shoe": "shoes", "bike": "bike", "bicycle": "bike"}


def _athlete(values: dict[str, Any]) -> list[RowOp]:
    row = {"id": ATHLETE_ID, **values, "updated_at": datetime.now(UTC)}
    return [Upsert(m.Athlete, [row], ("id",))]


def parse_identity(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """The logged-in profile as seen at login: {displayName, fullName, profileId}."""
    p = obj_or_empty(payload, "identity")
    if not p:
        return []
    return _athlete(
        {
            "display_name": text(p.get("displayName")),
            "full_name": text(p.get("fullName")),
            "profile_id": integer(p.get("profileId")),
        }
    )


def _unit_system(value: Any) -> str | None:
    s = text(value)
    if s is None:
        return None
    return "statute" if s.lower().startswith("statute") else "metric"


def _lt_speed_mps(value: Any) -> float | None:
    """userData.lactateThresholdSpeed looks like m/s divided by 10 (e.g. 0.34 for 3.4 m/s)."""
    f = positive(value)
    if f is None:
        return None
    return round(f * 10.0 if f < 1.5 else f, 3)


def parse_user_settings(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_user_profile → athlete gender, birth date, height, weight, units, LTHR, VO2max."""
    p = obj_or_empty(payload, "user settings")
    if not p:
        return []
    ud = obj_or_empty(p.get("userData"), "userData")
    height = positive(ud.get("height"))
    values: dict[str, Any] = {
        "gender": text(ud.get("gender")),
        "birth_date": day_of(ud.get("birthDate")),
        "height_cm": None if height is None else round(height * 100 if height < 3 else height, 1),
        "weight_kg": grams_to_kg(ud.get("weight")),
        "lactate_threshold_hr": small(ud.get("lactateThresholdHeartRate")),
        "lactate_threshold_speed_mps": _lt_speed_mps(ud.get("lactateThresholdSpeed")),
        "vo2max_running": rnd(ud.get("vo2MaxRunning"), 1),
        "vo2max_cycling": rnd(ud.get("vo2MaxCycling"), 1),
    }
    unit_system = _unit_system(ud.get("measurementSystem"))
    if unit_system is not None:
        values["unit_system"] = unit_system
    return _athlete(values)


def _zone(value: Any) -> str | None:
    name = text(value)
    if name is None:
        return None
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return name


def parse_personal_information(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_personal_information → athlete time zone and FTP."""
    p = obj_or_empty(payload, "personal information")
    if not p:
        return []
    bio = obj_or_empty(p.get("biometricProfile"), "biometricProfile")
    tz = _zone(first(p, "timeZone")) or _zone(dig(p, "userInfo", "timeZone"))
    return _athlete({"time_zone": tz, "ftp_w": small(bio.get("functionalThresholdPower"))})


def parse_nothing(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """Kept as raw payload only (e.g. the profile base, used to find the first account day)."""
    return []


def parse_hr_zones(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_heart_rate_zones → athlete max/resting HR and zone floors (DEFAULT sport)."""
    sets = dicts(payload, "heart rate zones")
    if not sets:
        return []
    chosen = next((s for s in sets if s.get("sport") == "DEFAULT"), sets[0])
    floors = [integer(chosen.get(f"zone{i}Floor")) for i in range(1, 6)]
    return _athlete(
        {
            "max_hr": small(chosen.get("maxHeartRateUsed")),
            "resting_hr": small(chosen.get("restingHeartRateUsed")),
            "hr_zones": floors if all(f is not None for f in floors) else None,
        }
    )


def parse_devices(payload: Any, ctx: ParseContext) -> list[RowOp]:
    rows = []
    for d in dicts(payload, "devices"):
        device_id = integer(first(d, "deviceId", "unitId"))
        if device_id is None:
            continue
        version = first(d, "currentFirmwareVersion", "softwareVersionString", "firmwareVersion")
        rows.append(
            {
                "device_id": device_id,
                "product_name": text(first(d, "productDisplayName", "productName", "partNumber")),
                "display_name": text(d.get("displayName")),
                "software_version": text(version),
                "is_primary": any(
                    d.get(k) is True
                    for k in ("primary", "primaryActivityTrackerIndicator", "primaryTrainingDevice")
                ),
                "image_url": text(d.get("imageUrl")),
            }
        )
    return [Upsert(m.Device, dedupe(rows, ("device_id",)), ("device_id",))] if rows else []


def parse_device_last_used(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "device last used")
    device_id = integer(first(p, "userDeviceId", "deviceId"))
    when = ts_utc(first(p, "lastUsedDeviceUploadTime", "lastUsedTime"))
    if device_id is None or when is None:
        return []
    return [Patch(m.Device, {"device_id": device_id}, {"last_used_at": when}, overwrite=True)]


def gear_row(g: dict[str, Any]) -> dict[str, Any] | None:
    """One gear object (legacy filterGear shape, as in get_gear and get_activity_gear)."""
    uuid = text(g.get("uuid"))
    if uuid is None:
        return None
    gtype = (text(first(g, "gearTypeName", "gearType")) or "").lower()
    status = (text(first(g, "gearStatusName", "gearStatus")) or "active").lower()
    return {
        "uuid": uuid,
        "gear_type": GEAR_TYPES.get(gtype, "other"),
        "display_name": text(first(g, "displayName", "customMakeModel")),
        "make": text(g.get("gearMakeName")),
        "model": text(first(g, "gearModelName", "customMakeModel")),
        "status": "retired" if status == "retired" else "active",
        "date_begin": day_of(g.get("dateBegin")),
        "date_end": day_of(g.get("dateEnd")),
        "max_distance_m": positive(g.get("maximumMeters")),
    }


def parse_gear(payload: Any, ctx: ParseContext) -> list[RowOp]:
    raw = payload.get("gearList") if isinstance(payload, dict) else payload
    rows = [r for r in (gear_row(g) for g in dicts(raw, "gear")) if r is not None]
    return [Upsert(m.Gear, dedupe(rows, ("uuid",)), ("uuid",))] if rows else []


def parse_gear_stats(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "gear stats")
    values = {
        "total_distance_m": num(p.get("totalDistance")),
        "total_activities": integer(p.get("totalActivities")),
    }
    if not has_values(values):
        return []
    return [Patch(m.Gear, {"uuid": ctx.key}, values, overwrite=True)]


def first_account_day_candidates(profile_base: Any, user_settings: Any) -> list[Any]:
    """Raw values that may hold the account creation date (shape not documented)."""
    out: list[Any] = []
    for payload in (profile_base, user_settings):
        if isinstance(payload, dict):
            for key in ("createDate", "createdDate", "userProfileCreateDate", "dateCreated"):
                out.append(payload.get(key))
    return out


__all__ = [
    "first_account_day_candidates",
    "gear_row",
    "parse_device_last_used",
    "parse_devices",
    "parse_gear",
    "parse_gear_stats",
    "parse_hr_zones",
    "parse_identity",
    "parse_nothing",
    "parse_personal_information",
    "parse_user_settings",
]
