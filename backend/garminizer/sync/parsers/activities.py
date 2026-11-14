"""Activities: list items (primary activity row), summary details, laps, HR zones, weather, gear."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from garminizer import models as m
from garminizer.sports import FOOT_GROUPS, sport_group
from garminizer.sync.parsers.common import (
    ParseContext,
    Patch,
    Replace,
    RowOp,
    ShapeError,
    Upsert,
    dedupe,
    dicts,
    dig,
    f_to_c,
    first,
    flag,
    has_values,
    integer,
    items,
    mph_to_mps,
    num,
    obj,
    obj_or_empty,
    positive,
    rnd,
    small,
    text,
    ts_local,
    ts_utc,
)
from garminizer.sync.parsers.profile import gear_row

_CADENCE_KEYS = {
    "run": ("averageRunningCadenceInStepsPerMinute", "maxRunningCadenceInStepsPerMinute"),
    "ride": ("averageBikingCadenceInRevPerMinute", "maxBikingCadenceInRevPerMinute"),
    "swim": ("averageSwimCadenceInStrokesPerMinute", "maxSwimCadenceInStrokesPerMinute"),
}


def _cm_to_m(value: Any) -> float | None:
    f = positive(value)
    return None if f is None else round(f / 100.0, 3)


def _pool_length_m(value: Any) -> float | None:
    """poolLength comes in centimetres (2500.0 = 25 m)."""
    f = positive(value)
    if f is None:
        return None
    return round(f / 100.0, 2) if f > 200 else round(f, 2)


def _cadence(a: dict[str, Any], group: str) -> tuple[float | None, float | None]:
    keys = _CADENCE_KEYS.get("run" if group in FOOT_GROUPS else group)
    if keys is None:
        avg = first(a, *(k[0] for k in _CADENCE_KEYS.values()))
        mx = first(a, *(k[1] for k in _CADENCE_KEYS.values()))
    else:
        avg, mx = a.get(keys[0]), a.get(keys[1])
    return rnd(avg, 1), rnd(mx, 1)


def activity_row(a: dict[str, Any]) -> dict[str, Any]:
    """An activity-list item (get_activities) → full activity row (without computed columns)."""
    aid = integer(a.get("activityId"))
    if aid is None or aid <= 0:
        raise ShapeError("activity: activityId missing")
    start_utc = ts_utc(a.get("startTimeGMT")) or ts_utc(a.get("beginTimestamp"))
    if start_utc is None:
        raise ShapeError("activity: start time missing")
    start_local = ts_local(a.get("startTimeLocal")) or start_utc.replace(tzinfo=None)
    type_key = text(dig(a, "activityType", "typeKey")) or "other"
    group = sport_group(type_key)
    avg_cad, max_cad = _cadence(a, group)
    return {
        "activity_id": aid,
        "name": text(a.get("activityName")),
        "description": text(a.get("description")),
        "sport_type": type_key,
        "sport_group": group,
        "start_time_utc": start_utc,
        "start_time_local": start_local,
        "duration_s": num(a.get("duration")),
        "elapsed_s": num(a.get("elapsedDuration")),
        "moving_s": num(a.get("movingDuration")),
        "distance_m": num(a.get("distance")),
        "elevation_gain_m": rnd(a.get("elevationGain"), 1),
        "elevation_loss_m": rnd(a.get("elevationLoss"), 1),
        "min_elevation_m": rnd(a.get("minElevation"), 1),
        "max_elevation_m": rnd(a.get("maxElevation"), 1),
        "avg_speed_mps": rnd(a.get("averageSpeed"), 3),
        "max_speed_mps": rnd(a.get("maxSpeed"), 3),
        "avg_hr": small(a.get("averageHR")),
        "max_hr": small(a.get("maxHR")),
        "avg_cadence": avg_cad,
        "max_cadence": max_cad,
        "avg_power_w": rnd(a.get("avgPower"), 1),
        "max_power_w": rnd(a.get("maxPower"), 1),
        "normalized_power_w": rnd(a.get("normPower"), 1),
        "training_stress_score": rnd(a.get("trainingStressScore"), 1),
        "intensity_factor": rnd(a.get("intensityFactor"), 3),
        "calories": rnd(a.get("calories"), 1),
        "bmr_calories": rnd(positive(a.get("bmrCalories")), 1),
        "aerobic_te": rnd(a.get("aerobicTrainingEffect"), 1),
        "anaerobic_te": rnd(a.get("anaerobicTrainingEffect"), 1),
        "training_effect_label": text(a.get("trainingEffectLabel")),
        "training_load": rnd(a.get("activityTrainingLoad"), 1),
        "vo2max": rnd(a.get("vO2MaxValue"), 1),
        "min_temperature_c": rnd(a.get("minTemperature"), 1),
        "max_temperature_c": rnd(a.get("maxTemperature"), 1),
        "avg_respiration": rnd(a.get("avgRespirationRate"), 1),
        "avg_stride_length_m": _cm_to_m(a.get("avgStrideLength")),
        "avg_vertical_oscillation_cm": rnd(a.get("avgVerticalOscillation"), 2),
        "avg_ground_contact_ms": rnd(a.get("avgGroundContactTime"), 1),
        "avg_vertical_ratio": rnd(a.get("avgVerticalRatio"), 2),
        "steps": integer(a.get("steps")),
        "lap_count": small(a.get("lapCount")),
        "pool_length_m": _pool_length_m(a.get("poolLength")),
        "active_lengths": small(a.get("activeLengths")),
        "strokes": rnd(a.get("strokes"), 1),
        "avg_swolf": rnd(first(a, "averageSwolf", "avgSwolf"), 1),
        "total_sets": small(a.get("totalSets")),
        "total_reps": small(a.get("totalReps")),
        "moderate_intensity_min": small(a.get("moderateIntensityMinutes")),
        "vigorous_intensity_min": small(a.get("vigorousIntensityMinutes")),
        "body_battery_delta": small(a.get("differenceBodyBattery")),
        "water_estimated_ml": rnd(a.get("waterEstimated"), 1),
        "start_lat": num(a.get("startLatitude")),
        "start_lon": num(a.get("startLongitude")),
        "end_lat": num(a.get("endLatitude")),
        "end_lon": num(a.get("endLongitude")),
        "location_name": text(a.get("locationName")),
        "device_id": integer(a.get("deviceId")),
        "is_manual": flag(a.get("manualActivity")) or False,
        "is_favorite": flag(a.get("favorite")) or False,
        "updated_at": datetime.now(UTC),
    }


def parse_activity(payload: Any, ctx: ParseContext) -> list[RowOp]:
    row = activity_row(obj(payload, "activity"))
    return [Upsert(m.Activity, [row], ("activity_id",))]


def parse_activity_summary(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_activity → fills columns the list item did not have (never overrides it)."""
    p = obj_or_empty(payload, "activity summary")
    if not p:
        return []
    s = obj_or_empty(p.get("summaryDTO"), "summaryDTO")
    meta = obj_or_empty(p.get("metadataDTO"), "metadataDTO")
    values = {
        "description": text(p.get("description")),
        "location_name": text(p.get("locationName")),
        "elapsed_s": num(s.get("elapsedDuration")),
        "moving_s": num(s.get("movingDuration")),
        "min_elevation_m": rnd(s.get("minElevation"), 1),
        "max_elevation_m": rnd(s.get("maxElevation"), 1),
        "normalized_power_w": rnd(s.get("normalizedPower"), 1),
        "training_stress_score": rnd(s.get("trainingStressScore"), 1),
        "intensity_factor": rnd(s.get("intensityFactor"), 3),
        "avg_temperature_c": rnd(s.get("averageTemperature"), 1),
        "min_temperature_c": rnd(s.get("minTemperature"), 1),
        "max_temperature_c": rnd(s.get("maxTemperature"), 1),
        "avg_respiration": rnd(first(s, "avgRespirationRate", "averageRespirationRate"), 1),
        "avg_stride_length_m": _cm_to_m(s.get("strideLength")),
        "avg_vertical_oscillation_cm": rnd(s.get("verticalOscillation"), 2),
        "avg_ground_contact_ms": rnd(s.get("groundContactTime"), 1),
        "avg_vertical_ratio": rnd(s.get("verticalRatio"), 2),
        "steps": integer(s.get("steps")),
        "water_estimated_ml": rnd(s.get("waterEstimated"), 1),
        "body_battery_delta": small(s.get("differenceBodyBattery")),
        "lap_count": small(meta.get("lapCount")),
        "device_id": integer(dig(meta, "deviceMetaDataDTO", "deviceId")),
    }
    if not has_values(values):
        return []
    return [Patch(m.Activity, {"activity_id": ctx.require_activity_id()}, values)]


def parse_activity_splits(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_activity_splits → laps (lapDTOs) as recorded by the device."""
    aid = ctx.require_activity_id()
    p = obj_or_empty(payload, "activity splits")
    rows = []
    for i, lap in enumerate(dicts(p.get("lapDTOs"), "lapDTOs"), start=1):
        index = small(lap.get("lapIndex")) or i
        cadence = first(lap, "averageRunCadence", "averageBikeCadence", "averageCadence")
        rows.append(
            {
                "activity_id": aid,
                "lap_index": index,
                "start_time_utc": ts_utc(lap.get("startTimeGMT")),
                "duration_s": num(lap.get("duration")),
                "moving_s": num(lap.get("movingDuration")),
                "distance_m": num(lap.get("distance")),
                "avg_speed_mps": rnd(lap.get("averageSpeed"), 3),
                "max_speed_mps": rnd(lap.get("maxSpeed"), 3),
                "avg_hr": small(lap.get("averageHR")),
                "max_hr": small(lap.get("maxHR")),
                "avg_cadence": rnd(cadence, 1),
                "avg_power_w": rnd(lap.get("averagePower"), 1),
                "max_power_w": rnd(lap.get("maxPower"), 1),
                "normalized_power_w": rnd(lap.get("normalizedPower"), 1),
                "elevation_gain_m": rnd(lap.get("elevationGain"), 1),
                "elevation_loss_m": rnd(lap.get("elevationLoss"), 1),
                "calories": rnd(lap.get("calories"), 1),
                "intensity": (text(lap.get("intensityType")) or "").lower() or None,
            }
        )
    if payload is None:
        return []
    return [Replace(m.ActivityLap, {"activity_id": aid}, dedupe(rows, ("lap_index",)))]


def parse_activity_hr_zones(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_activity_hr_in_timezones → activity_zone (kind hr); zone 0 counts as zone 1."""
    aid = ctx.require_activity_id()
    zones = dicts(payload, "hr time in zones")
    seconds: dict[int, float] = {}
    lows: dict[int, float | None] = {}
    for z in zones:
        n = integer(z.get("zoneNumber"))
        secs = num(z.get("secsInZone"))
        if n is None or secs is None or n < 0:
            continue
        zone = max(n, 1)
        seconds[zone] = seconds.get(zone, 0.0) + secs
        if n >= 1:
            lows[zone] = num(z.get("zoneLowBoundary"))
    if not seconds:
        return []
    rows = [
        {
            "activity_id": aid,
            "kind": "hr",
            "zone": zone,
            "seconds": round(secs, 1),
            "low_value": lows.get(zone),
        }
        for zone, secs in sorted(seconds.items())
    ]
    return [Replace(m.ActivityZone, {"activity_id": aid, "kind": "hr"}, rows)]


def parse_activity_weather(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_activity_weather: temperatures in °F and wind in mph → °C and m/s."""
    aid = ctx.require_activity_id()
    if payload is None:
        return []
    p = obj_or_empty(payload, "activity weather")
    row = {
        "activity_id": aid,
        "issued_at": ts_utc(p.get("issueDate")),
        "temperature_c": f_to_c(p.get("temp")),
        "apparent_temperature_c": f_to_c(p.get("apparentTemp")),
        "dew_point_c": f_to_c(p.get("dewPoint")),
        "humidity_pct": rnd(p.get("relativeHumidity"), 1),
        "wind_speed_mps": mph_to_mps(p.get("windSpeed")),
        "wind_gust_mps": mph_to_mps(p.get("windGust")),
        "wind_direction_deg": rnd(p.get("windDirection"), 1),
        "condition": text(dig(p, "weatherTypeDTO", "desc")),
    }
    rows = [row] if has_values(row, ignore=("activity_id",)) else []
    return [Replace(m.ActivityWeather, {"activity_id": aid}, rows)]


def parse_activity_gear(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_activity_gear → gear rows (only filled in, never overriding) + activity_gear links."""
    aid = ctx.require_activity_id()
    if payload is None:
        return []
    gear = [r for r in (gear_row(g) for g in dicts(items(payload, "activity gear"), "gear")) if r]
    gear = dedupe(gear, ("uuid",))
    ops: list[RowOp] = []
    if gear:
        ops.append(Upsert(m.Gear, gear, ("uuid",), fill_all=True))
    links = [{"activity_id": aid, "gear_uuid": g["uuid"]} for g in gear]
    ops.append(Replace(m.ActivityGear, {"activity_id": aid}, links))
    return ops
