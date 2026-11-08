"""Training readiness/status, VO2max, race predictions, endurance and hill score."""

from __future__ import annotations

import re
from typing import Any

from garminizer import models as m
from garminizer.sync.parsers.common import (
    ParseContext,
    RowOp,
    Upsert,
    day_of,
    dedupe,
    dicts,
    dig,
    first,
    has_values,
    num,
    obj_or_empty,
    rnd,
    small,
    text,
)

_PHRASE_SUFFIX = re.compile(r"_\d+$")
ENDURANCE_CLASSES = (
    ("classificationLowerLimitElite", "ELITE"),
    ("classificationLowerLimitSuperior", "SUPERIOR"),
    ("classificationLowerLimitExpert", "EXPERT"),
    ("classificationLowerLimitWellTrained", "WELL_TRAINED"),
    ("classificationLowerLimitTrained", "TRAINED"),
    ("classificationLowerLimitIntermediate", "INTERMEDIATE"),
)
# Fallback when the response carries no limits (same bands the demo data uses).
DEFAULT_ENDURANCE_LIMITS = {
    "ELITE": 9500.0,
    "SUPERIOR": 8500.0,
    "EXPERT": 7500.0,
    "WELL_TRAINED": 6500.0,
    "TRAINED": 5500.0,
    "INTERMEDIATE": 4500.0,
    "RECREATIONAL": 3000.0,
}


def _snapshots(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        return [payload]
    return dicts(payload, "snapshots")


def parse_training_readiness(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """The morning snapshot (AFTER_WAKEUP_RESET), else the earliest of the day."""
    snaps = [s for s in _snapshots(payload) if s.get("score") is not None]
    if not snaps:
        return []
    morning = [s for s in snaps if s.get("inputContext") == "AFTER_WAKEUP_RESET"]
    pick = (morning or sorted(snaps, key=lambda s: str(s.get("timestamp") or "")))[0]
    row = {
        "day": day_of(pick.get("calendarDate")) or ctx.require_day(),
        "score": small(pick.get("score")),
        "level": text(pick.get("level")),
        "sleep_score_factor": small(pick.get("sleepScoreFactorPercent")),
        "recovery_time_min": small(pick.get("recoveryTime")),
        "recovery_factor": small(pick.get("recoveryTimeFactorPercent")),
        "acwr_factor": small(pick.get("acwrFactorPercent")),
        "hrv_factor": small(pick.get("hrvFactorPercent")),
        "stress_history_factor": small(pick.get("stressHistoryFactorPercent")),
        "sleep_history_factor": small(pick.get("sleepHistoryFactorPercent")),
        "feedback": text(first(pick, "feedbackShort", "feedbackLong")),
    }
    return [Upsert(m.TrainingReadiness, [row], ("day",))]


def _per_device(container: Any) -> dict[str, Any]:
    """Pick the primary training device's entry from Garmin's {deviceId: {...}} maps."""
    if not isinstance(container, dict):
        return {}
    entries = [v for v in container.values() if isinstance(v, dict)]
    if not entries:
        return {}
    return next((e for e in entries if e.get("primaryTrainingDevice") is True), entries[0])


def _status_phrase(value: Any) -> str | None:
    s = text(value)
    return _PHRASE_SUFFIX.sub("", s).upper() if s else None


def parse_training_status(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_training_status (aggregated, "as of" the requested day) → training_status row."""
    p = obj_or_empty(payload, "training status")
    status = _per_device(dig(p, "mostRecentTrainingStatus", "latestTrainingStatusData"))
    acute = obj_or_empty(status.get("acuteTrainingLoadDTO"), "acuteTrainingLoadDTO")
    balance = _per_device(
        dig(p, "mostRecentTrainingLoadBalance", "metricsTrainingLoadBalanceDTOMap")
    )
    heat = obj_or_empty(
        p.get("heatAltitudeAcclimationDTO")
        or dig(p, "mostRecentVO2Max", "heatAltitudeAcclimation"),
        "heatAltitudeAcclimation",
    )
    row: dict[str, Any] = {
        "status": _status_phrase(status.get("trainingStatusFeedbackPhrase")),
        "acute_load": rnd(acute.get("dailyTrainingLoadAcute"), 1),
        "chronic_load": rnd(acute.get("dailyTrainingLoadChronic"), 1),
        "acwr": rnd(acute.get("dailyAcuteChronicWorkloadRatio"), 2),
        "acwr_status": text(acute.get("acwrStatus")),
        "load_low_aerobic": rnd(balance.get("monthlyLoadAerobicLow"), 1),
        "load_high_aerobic": rnd(balance.get("monthlyLoadAerobicHigh"), 1),
        "load_anaerobic": rnd(balance.get("monthlyLoadAnaerobic"), 1),
        "target_low_aerobic_min": rnd(balance.get("monthlyLoadAerobicLowTargetMin"), 1),
        "target_low_aerobic_max": rnd(balance.get("monthlyLoadAerobicLowTargetMax"), 1),
        "target_high_aerobic_min": rnd(balance.get("monthlyLoadAerobicHighTargetMin"), 1),
        "target_high_aerobic_max": rnd(balance.get("monthlyLoadAerobicHighTargetMax"), 1),
        "target_anaerobic_min": rnd(balance.get("monthlyLoadAnaerobicTargetMin"), 1),
        "target_anaerobic_max": rnd(balance.get("monthlyLoadAnaerobicTargetMax"), 1),
        "load_balance_feedback": _status_phrase(balance.get("trainingBalanceFeedbackPhrase")),
        "heat_acclimation_pct": rnd(heat.get("heatAcclimationPercentage"), 1),
        "altitude_acclimation_m": rnd(heat.get("altitudeAcclimation"), 1),
    }
    if not has_values(row):
        return []
    row["day"] = ctx.require_day()
    return [Upsert(m.TrainingStatus, [row], ("day",))]


def parse_max_metrics(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_max_metrics → VO2max (running = "generic", cycling) and fitness age."""
    rows = []
    for e in _snapshots(payload):
        generic = obj_or_empty(e.get("generic"), "generic")
        cycling = obj_or_empty(e.get("cycling"), "cycling")
        row: dict[str, Any] = {
            "vo2max_running": rnd(first(generic, "vo2MaxPreciseValue", "vo2MaxValue"), 1),
            "vo2max_cycling": rnd(first(cycling, "vo2MaxPreciseValue", "vo2MaxValue"), 1),
            "fitness_age": rnd(generic.get("fitnessAge"), 1),
        }
        if not has_values(row):
            continue
        row["day"] = (
            day_of(first(generic, "calendarDate") or first(cycling, "calendarDate"))
            or ctx.require_day()
        )
        rows.append(row)
    return [Upsert(m.MaxMetric, dedupe(rows, ("day",)), ("day",))] if rows else []


def parse_race_predictions(payload: Any, ctx: ParseContext) -> list[RowOp]:
    rows = []
    for e in _snapshots(payload):
        day = day_of(e.get("calendarDate"))
        row = {
            "time_5k_s": rnd(e.get("time5K"), 1),
            "time_10k_s": rnd(e.get("time10K"), 1),
            "time_half_s": rnd(e.get("timeHalfMarathon"), 1),
            "time_marathon_s": rnd(e.get("timeMarathon"), 1),
        }
        if day is None or not has_values(row):
            continue
        rows.append({"day": day, **row})
    return [Upsert(m.RacePrediction, dedupe(rows, ("day",)), ("day",))] if rows else []


def _endurance_class(score: float | None, dto: dict[str, Any]) -> str | None:
    if score is None:
        return None
    limits = {name: num(dto.get(key)) for key, name in ENDURANCE_CLASSES}
    if not any(v is not None for v in limits.values()):
        limits = {k: v for k, v in DEFAULT_ENDURANCE_LIMITS.items() if k != "RECREATIONAL"}
    for name, low in sorted(
        ((k, v) for k, v in limits.items() if v is not None), key=lambda kv: -kv[1]
    ):
        if score >= low:
            return name
    return "RECREATIONAL" if score >= DEFAULT_ENDURANCE_LIMITS["RECREATIONAL"] else "UNTRAINED"


def parse_endurance_score(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_endurance_score(range, aggregation=daily): groupMap {day: {groupAverage}} + DTO."""
    p = obj_or_empty(payload, "endurance score")
    dto = obj_or_empty(p.get("enduranceScoreDTO"), "enduranceScoreDTO")
    by_day: dict[Any, float] = {}
    group_map = p.get("groupMap")
    if isinstance(group_map, dict):
        for key, value in group_map.items():
            day = day_of(key)
            score = num(dig(value, "groupAverage"))
            if day is not None and score is not None:
                by_day[day] = score
    dto_day, dto_score = day_of(dto.get("calendarDate")), num(dto.get("overallScore"))
    if dto_day is not None and dto_score is not None:
        by_day[dto_day] = dto_score
    rows = [
        {"day": d, "score": round(s, 1), "classification": _endurance_class(s, dto)}
        for d, s in sorted(by_day.items())
    ]
    return [Upsert(m.EnduranceScore, rows, ("day",))] if rows else []


def parse_hill_score(payload: Any, ctx: ParseContext) -> list[RowOp]:
    p = obj_or_empty(payload, "hill score")
    rows = []
    for e in dicts(p.get("hillScoreDTOList"), "hillScoreDTOList"):
        day = day_of(e.get("calendarDate"))
        row = {
            "score": rnd(e.get("overallScore"), 1),
            "endurance": rnd(e.get("enduranceScore"), 1),
            "strength": rnd(e.get("strengthScore"), 1),
        }
        if day is None or not has_values(row):
            continue
        rows.append({"day": day, **row})
    return [Upsert(m.HillScore, dedupe(rows, ("day",)), ("day",))] if rows else []


__all__ = [
    "parse_endurance_score",
    "parse_hill_score",
    "parse_max_metrics",
    "parse_race_predictions",
    "parse_training_readiness",
    "parse_training_status",
]
