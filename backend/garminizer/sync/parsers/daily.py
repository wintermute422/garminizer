"""Daily wellness: summary, sleep, HRV and the intraday series (HR, stress, body battery, ...)."""

from __future__ import annotations

import statistics
from typing import Any

from garminizer import models as m
from garminizer.sync.parsers.common import (
    ParseContext,
    Replace,
    RowOp,
    Upsert,
    day_of,
    dedupe,
    dicts,
    dig,
    first,
    has_values,
    integer,
    non_negative_small,
    num,
    obj_or_empty,
    rnd,
    series,
    small,
    text,
    ts_utc,
)

SLEEP_STAGES = {0: "deep", 1: "light", 2: "rem", 3: "awake"}
# Columns of daily_summary that secondary datasets (spo2, respiration, intensity minutes) also
# provide: the user summary keeps a stored value when it has none itself.
SUMMARY_SHARED = frozenset(
    {
        "avg_spo2",
        "lowest_spo2",
        "avg_waking_respiration",
        "moderate_intensity_min",
        "vigorous_intensity_min",
    }
)


def _day(payload: dict[str, Any], ctx: ParseContext, *keys: str) -> Any:
    return day_of(first(payload, *keys, "calendarDate")) or ctx.require_day()


def parse_user_summary(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_user_summary → daily_summary (steps, calories, HR, stress, body battery, ...)."""
    p = obj_or_empty(payload, "user summary")
    row = {
        "steps": integer(p.get("totalSteps")),
        "step_goal": integer(p.get("dailyStepGoal")),
        "distance_m": num(p.get("totalDistanceMeters")),
        "floors_up": rnd(p.get("floorsAscended"), 1),
        "floors_down": rnd(p.get("floorsDescended"), 1),
        "floors_goal": rnd(p.get("userFloorsAscendedGoal"), 1),
        "total_kcal": rnd(p.get("totalKilocalories"), 1),
        "active_kcal": rnd(p.get("activeKilocalories"), 1),
        "bmr_kcal": rnd(p.get("bmrKilocalories"), 1),
        "resting_hr": small(p.get("restingHeartRate")),
        "min_hr": small(p.get("minHeartRate")),
        "max_hr": small(p.get("maxHeartRate")),
        "avg_stress": non_negative_small(p.get("averageStressLevel")),
        "max_stress": non_negative_small(p.get("maxStressLevel")),
        "stress_rest_s": integer(p.get("restStressDuration")),
        "stress_low_s": integer(p.get("lowStressDuration")),
        "stress_medium_s": integer(p.get("mediumStressDuration")),
        "stress_high_s": integer(p.get("highStressDuration")),
        "body_battery_high": small(p.get("bodyBatteryHighestValue")),
        "body_battery_low": small(p.get("bodyBatteryLowestValue")),
        "body_battery_charged": small(p.get("bodyBatteryChargedValue")),
        "body_battery_drained": small(p.get("bodyBatteryDrainedValue")),
        "body_battery_at_wake": small(p.get("bodyBatteryAtWakeTime")),
        "moderate_intensity_min": small(p.get("moderateIntensityMinutes")),
        "vigorous_intensity_min": small(p.get("vigorousIntensityMinutes")),
        "intensity_goal_min": small(p.get("intensityMinutesGoal")),
        "avg_spo2": rnd(p.get("averageSpo2"), 1),
        "lowest_spo2": rnd(p.get("lowestSpo2"), 1),
        "avg_waking_respiration": rnd(p.get("avgWakingRespirationValue"), 1),
        "sedentary_s": integer(p.get("sedentarySeconds")),
        "active_s": integer(p.get("activeSeconds")),
        "highly_active_s": integer(p.get("highlyActiveSeconds")),
        "sleeping_s": integer(p.get("sleepingSeconds")),
    }
    if not has_values(row):
        return []
    row["day"] = _day(p, ctx)
    return [Upsert(m.DailySummary, [row], ("day",), prefer_new=SUMMARY_SHARED)]


def _summary_fill(day: Any, values: dict[str, Any]) -> list[RowOp]:
    if not has_values(values):
        return []
    return [Upsert(m.DailySummary, [{"day": day, **values}], ("day",), keep_old=frozenset(values))]


def parse_hydration(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "hydration")
    values = {
        "hydration_ml": rnd(p.get("valueInML"), 1),
        "hydration_goal_ml": rnd(p.get("goalInML"), 1),
    }
    if not has_values(values):
        return []
    return [Upsert(m.DailySummary, [{"day": _day(p, ctx), **values}], ("day",))]


def parse_intensity_minutes(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "intensity minutes")
    return _summary_fill(
        _day(p, ctx),
        {
            "moderate_intensity_min": small(p.get("moderateMinutes")),
            "vigorous_intensity_min": small(p.get("vigorousMinutes")),
        },
    )


def _score(scores: dict[str, Any], name: str, field: str = "value") -> Any:
    return dig(scores, name, field)


def parse_sleep(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_sleep_data → sleep (keyed by the wake-up day) + sleep_stage hypnogram."""
    p = obj_or_empty(payload, "sleep")
    dto = obj_or_empty(p.get("dailySleepDTO"), "dailySleepDTO")
    start = ts_utc(dto.get("sleepStartTimestampGMT"))
    duration = integer(dto.get("sleepTimeSeconds"))
    if start is None and not duration:
        return []
    day = _day(dto, ctx)
    scores = obj_or_empty(dto.get("sleepScores"), "sleepScores")
    hr = [
        v
        for v in (num(x.get("value")) for x in dicts(p.get("sleepHeartRate"), "sleepHeartRate"))
        if v is not None and v > 0
    ]
    row = {
        "day": day,
        "start_utc": start,
        "end_utc": ts_utc(dto.get("sleepEndTimestampGMT")),
        "duration_s": duration,
        "deep_s": integer(dto.get("deepSleepSeconds")),
        "light_s": integer(dto.get("lightSleepSeconds")),
        "rem_s": integer(dto.get("remSleepSeconds")),
        "awake_s": integer(dto.get("awakeSleepSeconds")),
        "unmeasurable_s": integer(dto.get("unmeasurableSleepSeconds")),
        "score": small(_score(scores, "overall")),
        "score_quality": text(_score(scores, "overall", "qualifierKey")),
        "score_duration": small(_score(scores, "totalDuration")),
        "score_deep": small(_score(scores, "deepPercentage")),
        "score_rem": small(_score(scores, "remPercentage")),
        "score_light": small(_score(scores, "lightPercentage")),
        "score_awakenings": small(_score(scores, "awakeCount")),
        "score_stress": small(_score(scores, "stress")),
        "avg_hr": rnd(first(dto, "avgHeartRate", "averageHeartRate"), 1)
        or (round(statistics.fmean(hr), 1) if hr else None),
        "lowest_hr": small(first(dto, "lowestHeartRate")) or (round(min(hr)) if hr else None),
        "avg_respiration": rnd(dto.get("averageRespirationValue"), 1),
        "lowest_respiration": rnd(dto.get("lowestRespirationValue"), 1),
        "highest_respiration": rnd(dto.get("highestRespirationValue"), 1),
        "avg_spo2": rnd(dto.get("averageSpO2Value"), 1),
        "lowest_spo2": rnd(dto.get("lowestSpO2Value"), 1),
        "avg_stress": rnd(dto.get("avgSleepStress"), 1),
        "avg_overnight_hrv": rnd(first(p, "avgOvernightHrv") or dto.get("avgSleepHRV"), 1),
        "restless_moments": small(p.get("restlessMomentsCount")),
        "awake_count": small(dto.get("awakeCount")),
        "body_battery_change": small(p.get("bodyBatteryChange")),
        "sleep_need_min": small(dig(dto, "sleepNeed", "actual")),
        "feedback": text(dto.get("sleepScoreFeedback")),
    }
    stages = []
    for level in dicts(p.get("sleepLevels"), "sleepLevels"):
        s, e = ts_utc(level.get("startGMT")), ts_utc(level.get("endGMT"))
        code = integer(level.get("activityLevel"))
        stage = SLEEP_STAGES.get(code) if code is not None else None
        if s is None or e is None or e <= s or stage is None:
            continue
        stages.append({"day": day, "start_utc": s, "end_utc": e, "stage": stage})
    return [
        Upsert(m.Sleep, [row], ("day",)),
        Replace(m.SleepStage, {"day": day}, dedupe(stages, ("start_utc",))),
    ]


def parse_hrv(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "hrv")
    s = obj_or_empty(p.get("hrvSummary"), "hrvSummary")
    base = obj_or_empty(s.get("baseline"), "hrv baseline")
    row = {
        "last_night_avg_ms": rnd(s.get("lastNightAvg"), 1),
        "last_night_5min_high_ms": rnd(s.get("lastNight5MinHigh"), 1),
        "weekly_avg_ms": rnd(s.get("weeklyAvg"), 1),
        "baseline_low_ms": rnd(base.get("lowUpper"), 1),
        "baseline_balanced_low_ms": rnd(base.get("balancedLow"), 1),
        "baseline_balanced_upper_ms": rnd(base.get("balancedUpper"), 1),
        "status": text(s.get("status")),
        "feedback": text(s.get("feedbackPhrase")),
    }
    if not has_values(row):
        return []
    row["day"] = _day(s, ctx)
    return [Upsert(m.HrvDaily, [row], ("day",))]


def parse_heart_rates(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "heart rates")
    pts = series(p.get("heartRateValues"), p.get("heartRateValueDescriptors"), "heartrate")
    rows = [{"ts": t, "bpm": round(v)} for t, v in pts if 0 < v < 260]
    return [Upsert(m.HrSample, rows, ("ts",))] if rows else []


def parse_stress(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_stress_data → stress_sample (-1/-2 markers kept) + body_battery_sample."""
    p = obj_or_empty(payload, "stress")
    ops: list[RowOp] = []
    stress = series(
        p.get("stressValuesArray"), p.get("stressValueDescriptorsDTOList"), "stressLevel"
    )
    rows = [{"ts": t, "level": round(v)} for t, v in stress if -2 <= v <= 100]
    if rows:
        ops.append(Upsert(m.StressSample, rows, ("ts",)))
    bb = series(
        p.get("bodyBatteryValuesArray"),
        p.get("bodyBatteryValueDescriptorsDTOList"),
        "bodyBatteryLevel",
        key_field="bodyBatteryValueDescriptorKey",
        index_field="bodyBatteryValueDescriptorIndex",
        default_index=2,
    )
    bb_rows = [{"ts": t, "level": round(v)} for t, v in bb if 0 <= v <= 100]
    if bb_rows:
        ops.append(Upsert(m.BodyBatterySample, bb_rows, ("ts",)))
    return ops


def parse_respiration(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "respiration")
    pts = series(
        p.get("respirationValuesArray"), p.get("respirationValueDescriptorsDTOList"), "respiration"
    )
    ops: list[RowOp] = []
    rows = [{"ts": t, "breaths_per_min": round(v, 1)} for t, v in pts if 0 < v < 80]
    if rows:
        ops.append(Upsert(m.RespirationSample, rows, ("ts",)))
    if p:
        ops += _summary_fill(
            _day(p, ctx),
            {"avg_waking_respiration": rnd(p.get("avgWakingRespirationValue"), 1)},
        )
    return ops


def _spo2_points(p: dict[str, Any]) -> list[tuple[Any, float]]:
    readings = []
    for r in dicts(p.get("continuousReadingDTOList"), "continuousReadingDTOList"):
        t = ts_utc(first(r, "epochTimestamp", "readingTimestampGMT"))
        v = num(first(r, "spo2Reading", "spo2Value"))
        if t is not None and v is not None:
            readings.append((t, v))
    if readings:
        return readings
    for key in ("spO2SingleValues", "spO2HourlyAverages"):
        pts = series(p.get(key), None, "spo2")
        if pts:
            return list(pts)
    return []


def parse_spo2(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "spo2")
    ops: list[RowOp] = []
    rows = [{"ts": t, "spo2_pct": round(v, 1)} for t, v in _spo2_points(p) if 50 <= v <= 100]
    if rows:
        ops.append(Upsert(m.Spo2Sample, dedupe(rows, ("ts",)), ("ts",)))
    if p:
        ops += _summary_fill(
            _day(p, ctx),
            {
                "avg_spo2": rnd(p.get("averageSpO2"), 1),
                "lowest_spo2": rnd(p.get("lowestSpO2"), 1),
            },
        )
    return ops


def parse_steps(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_steps_data → 15-minute steps intervals."""
    rows = []
    for r in dicts(payload, "steps"):
        s, e = ts_utc(r.get("startGMT")), ts_utc(r.get("endGMT"))
        steps = integer(r.get("steps"))
        if s is None or e is None or steps is None:
            continue
        rows.append(
            {
                "start_utc": s,
                "end_utc": e,
                "steps": steps,
                "activity_level": text(r.get("primaryActivityLevel")),
            }
        )
    return [Upsert(m.StepsInterval, dedupe(rows, ("start_utc",)), ("start_utc",))] if rows else []
