"""Weigh-ins, blood pressure, personal records, badges and goals."""

from __future__ import annotations

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
    first,
    grams_to_kg,
    integer,
    num,
    obj_or_empty,
    rnd,
    small,
    text,
    ts_utc,
)

# Garmin personal-record type ids whose meaning is documented (library docstring and the
# Connect web app); unknown ids are kept as pr_type_<id>.
PR_TYPES = {
    1: "run_1k",
    2: "run_mile",
    3: "run_5k",
    4: "run_10k",
    5: "run_half_marathon",
    6: "run_marathon",
    7: "longest_run",
    8: "longest_ride",
    12: "most_steps_day",
    13: "most_steps_week",
    14: "most_steps_month",
}


def parse_body_composition(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_body_composition(range): dateWeightList (weights and masses in grams)."""
    p = obj_or_empty(payload, "body composition")
    rows = []
    for w in dicts(p.get("dateWeightList"), "dateWeightList"):
        when = ts_utc(first(w, "timestampGMT", "date"))
        weight = grams_to_kg(w.get("weight"))
        if when is None or weight is None:
            continue
        rows.append(
            {
                "measured_at": when,
                "weight_kg": weight,
                "bmi": rnd(w.get("bmi"), 1),
                "body_fat_pct": rnd(w.get("bodyFat"), 1),
                "body_water_pct": rnd(w.get("bodyWater"), 1),
                "muscle_mass_kg": grams_to_kg(w.get("muscleMass")),
                "bone_mass_kg": grams_to_kg(w.get("boneMass"), threshold=100.0),
                "visceral_fat": rnd(w.get("visceralFat"), 1),
                "metabolic_age": rnd(w.get("metabolicAge"), 1),
                "source": text(w.get("sourceType")),
            }
        )
    return (
        [Upsert(m.BodyComposition, dedupe(rows, ("measured_at",)), ("measured_at",))]
        if rows
        else []
    )


def parse_blood_pressure(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_blood_pressure(range): measurementSummaries[].measurements[]."""
    p = obj_or_empty(payload, "blood pressure")
    rows = []
    for summary in dicts(p.get("measurementSummaries"), "measurementSummaries"):
        for r in dicts(summary.get("measurements"), "measurements"):
            when = ts_utc(first(r, "measurementTimestampGMT", "measurementTimestamp"))
            sys_, dia = small(r.get("systolic")), small(r.get("diastolic"))
            if when is None or sys_ is None or dia is None:
                continue
            rows.append(
                {
                    "measured_at": when,
                    "systolic": sys_,
                    "diastolic": dia,
                    "pulse": small(r.get("pulse")),
                    "category": text(first(r, "category", "categoryName")),
                }
            )
    return (
        [Upsert(m.BloodPressure, dedupe(rows, ("measured_at",)), ("measured_at",))] if rows else []
    )


def parse_personal_records(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_personal_record → the current record set (replaces the stored one)."""
    if payload is None:
        return []
    rows = []
    for r in dicts(payload, "personal records"):
        record_id, type_id, value = (
            integer(r.get("id")),
            integer(r.get("typeId")),
            num(r.get("value")),
        )
        if record_id is None or type_id is None or value is None:
            continue
        rows.append(
            {
                "record_id": record_id,
                "type_id": type_id,
                "type_key": PR_TYPES.get(type_id, f"pr_type_{type_id}"),
                "value": value,
                "activity_id": integer(r.get("activityId")),
                "achieved_at": ts_utc(
                    first(
                        r,
                        "prStartTimeGmt",
                        "prStartTimeGmtFormatted",
                        "actStartDateTimeInGMTFormatted",
                    )
                ),
            }
        )
    return [Replace(m.PersonalRecord, {}, dedupe(rows, ("record_id",)))]


def parse_badges(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_earned_badges → the earned badge set (replaces the stored one)."""
    if payload is None:
        return []
    rows = []
    for b in dicts(payload, "badges"):
        badge_id, name = integer(b.get("badgeId")), text(first(b, "badgeName", "badgeKey"))
        if badge_id is None or name is None:
            continue
        category = first(b, "badgeCategoryKey", "badgeCategoryName", "badgeCategoryId")
        rows.append(
            {
                "badge_id": badge_id,
                "name": name,
                "category": text(category),
                "points": small(b.get("badgePoints")),
                "earned_at": ts_utc(b.get("badgeEarnedDate")),
                "earned_count": small(b.get("badgeEarnedNumber")),
            }
        )
    return [Replace(m.Badge, {}, dedupe(rows, ("badge_id",)))]


def parse_goals(payload: Any, ctx: ParseContext) -> list[RowOp]:
    """get_goals(status) → goals; the status is the raw key (active | future | past)."""
    rows = []
    for g in dicts(payload, "goals"):
        goal_id = integer(first(g, "id", "goalId", "goalPk"))
        if goal_id is None:
            continue
        rows.append(
            {
                "goal_id": goal_id,
                "goal_type": text(first(g, "goalType", "goalTypeKey", "goalCategory")) or "unknown",
                "target_value": num(first(g, "goalValue", "targetValue", "value")),
                "start_day": day_of(g.get("startDate")),
                "end_day": day_of(g.get("endDate")),
                "status": ctx.key,
            }
        )
    return [Upsert(m.Goal, dedupe(rows, ("goal_id",)), ("goal_id",))] if rows else []
