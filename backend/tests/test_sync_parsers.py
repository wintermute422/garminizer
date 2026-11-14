"""A4: every parser maps its fixture to the expected typed rows; writer semantics; FIT decoding."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.sync import fit, store
from garminizer.sync import parsers as p
from garminizer.sync.datasets import REGISTRY
from garminizer.sync.parsers.common import ParseContext, Patch, Replace, RowOp, ShapeError, Upsert
from tests.garmin_fake import fit_points, load, make_fit, zip_of

DAY = "2024-05-01"
RUN = "1234567890"


def utc(year: int, month: int, day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def run_parser(
    parser: p.Parser, fixture: str | None, key: str = DAY, payload: Any = None
) -> list[RowOp]:
    data = load(fixture) if fixture is not None else payload
    return parser(data, ParseContext("test", key))


def rows(ops: list[RowOp], model: type[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for op in ops:
        if op.model is not model:
            continue
        if isinstance(op, Patch):
            out.append(op.values)
        else:
            out += op.rows
    return out


def only(ops: list[RowOp], model: type[Any]) -> dict[str, Any]:
    found = rows(ops, model)
    assert len(found) == 1, found
    return found[0]


# --- profile, devices, gear ----------------------------------------------------------------


def test_identity() -> None:
    ops = run_parser(
        p.parse_identity,
        None,
        "self",
        {"displayName": "demo-athlete", "fullName": "Demo Athlete", "profileId": 1234567890},
    )
    row = only(ops, m.Athlete)
    assert (row["id"], row["display_name"], row["full_name"], row["profile_id"]) == (
        1,
        "demo-athlete",
        "Demo Athlete",
        1234567890,
    )


def test_user_settings() -> None:
    row = only(run_parser(p.parse_user_settings, "get_user_profile", "self"), m.Athlete)
    assert row["gender"] == "MALE"
    assert row["birth_date"] == date(1990, 6, 15)
    assert row["height_cm"] == 178.0
    assert row["weight_kg"] == 72.5
    assert row["unit_system"] == "metric"
    assert row["lactate_threshold_hr"] == 170
    assert row["lactate_threshold_speed_mps"] == 3.4
    assert (row["vo2max_running"], row["vo2max_cycling"]) == (52.0, 49.0)


def test_personal_information() -> None:
    row = only(
        run_parser(p.parse_personal_information, "get_personal_information", "self"), m.Athlete
    )
    assert row["time_zone"] == "Europe/Rome"
    assert row["ftp_w"] == 265


def test_hr_zones_use_the_default_sport() -> None:
    row = only(run_parser(p.parse_hr_zones, "get_heart_rate_zones", "self"), m.Athlete)
    assert row["max_hr"] == 188
    assert row["resting_hr"] == 48
    assert row["hr_zones"] == [94, 113, 132, 150, 169]


def test_devices_and_last_used() -> None:
    devices = rows(run_parser(p.parse_devices, "get_devices", "self"), m.Device)
    assert [d["device_id"] for d in devices] == [3400000001, 3400000002]
    assert devices[0]["product_name"] == "Forerunner Demo"
    assert devices[0]["software_version"] == "21.19"
    assert [d["is_primary"] for d in devices] == [True, False]
    (op,) = run_parser(p.parse_device_last_used, "get_device_last_used", "self")
    assert isinstance(op, Patch) and op.overwrite
    assert op.key == {"device_id": 3400000001}
    assert op.values == {"last_used_at": utc(2024, 5, 1, 12)}


def test_gear_and_stats() -> None:
    gear = rows(run_parser(p.parse_gear, "get_gear", "self"), m.Gear)
    shoe, bike = gear
    assert shoe["gear_type"] == "shoes"
    assert shoe["status"] == "active"
    assert shoe["make"] == "Demo Shoes"
    assert shoe["display_name"] == "Trainer 3 (pair 1)"
    assert shoe["date_begin"] == date(2024, 1, 10)
    assert shoe["max_distance_m"] == 800000.0
    assert (bike["gear_type"], bike["status"], bike["date_end"]) == (
        "bike",
        "retired",
        date(2024, 2, 1),
    )
    assert bike["max_distance_m"] is None
    (op,) = run_parser(p.parse_gear_stats, "get_gear_stats", shoe["uuid"])
    assert isinstance(op, Patch)
    assert op.values == {"total_distance_m": 412345.0, "total_activities": 52}


# --- activities --------------------------------------------------------------------------------


def test_activity_list_items() -> None:
    run_item, ride_item, strength_item = load("get_activities")
    run = only(p.parse_activity(run_item, ParseContext("activity", RUN)), m.Activity)
    assert run["activity_id"] == 1234567890
    assert (run["sport_type"], run["sport_group"]) == ("running", "run")
    assert run["start_time_utc"] == utc(2024, 5, 1, 7)
    assert run["start_time_local"] == datetime(2024, 5, 1, 9)
    assert (run["distance_m"], run["duration_s"], run["moving_s"]) == (10050.0, 3015.5, 3000.0)
    assert (run["avg_hr"], run["max_hr"]) == (152, 171)
    assert (run["avg_cadence"], run["max_cadence"]) == (172.5, 186.0)
    assert run["avg_stride_length_m"] == 1.162
    assert run["avg_vertical_oscillation_cm"] == 8.9
    assert run["training_load"] == 112.0
    assert (run["calories"], run["bmr_calories"]) == (690.0, 70.0)
    assert (run["start_lat"], run["start_lon"]) == (45.0012, 7.0021)
    assert run["is_manual"] is False
    assert "has_samples" not in run and "trimp" not in run
    ride = only(p.parse_activity(ride_item, ParseContext("activity", "1")), m.Activity)
    assert (ride["sport_group"], ride["avg_cadence"], ride["normalized_power_w"]) == (
        "ride",
        86.0,
        212.0,
    )
    assert (ride["training_stress_score"], ride["intensity_factor"], ride["is_favorite"]) == (
        96.0,
        0.8,
        True,
    )
    strength = only(p.parse_activity(strength_item, ParseContext("activity", "2")), m.Activity)
    assert (strength["sport_group"], strength["total_sets"], strength["total_reps"]) == (
        "strength",
        18,
        180,
    )
    assert strength["start_lat"] is None


def test_activity_shape_errors_name_no_values() -> None:
    with pytest.raises(ShapeError, match="activityId"):
        p.parse_activity({"activityName": "Secret Name"}, ParseContext("activity", "1"))
    with pytest.raises(ShapeError) as info:
        p.parse_activity([1, 2], ParseContext("activity", "1"))
    assert "Secret" not in str(info.value)


def test_activity_summary_fills_gaps_only() -> None:
    (op,) = run_parser(p.parse_activity_summary, "get_activity", RUN)
    assert isinstance(op, Patch) and not op.overwrite
    assert op.key == {"activity_id": 1234567890}
    assert op.values["avg_temperature_c"] == 18.5
    assert op.values["description"] == "Easy tempo loop"
    assert op.values["device_id"] == 3400000001
    assert op.values["lap_count"] == 2


def test_activity_splits_become_laps() -> None:
    ops = run_parser(p.parse_activity_splits, "get_activity_splits", RUN)
    assert isinstance(ops[0], Replace) and ops[0].where == {"activity_id": 1234567890}
    laps = rows(ops, m.ActivityLap)
    assert [lap["lap_index"] for lap in laps] == [1, 2]
    assert [lap["distance_m"] for lap in laps] == [5000.0, 5050.0]
    assert laps[0]["start_time_utc"] == utc(2024, 5, 1, 7)
    assert (laps[0]["avg_cadence"], laps[0]["avg_power_w"], laps[0]["intensity"]) == (
        171.0,
        285.0,
        "active",
    )


def test_activity_hr_zones() -> None:
    ops = run_parser(p.parse_activity_hr_zones, "get_activity_hr_in_timezones", RUN)
    assert isinstance(ops[0], Replace) and ops[0].where == {"activity_id": 1234567890, "kind": "hr"}
    zones = rows(ops, m.ActivityZone)
    assert [z["zone"] for z in zones] == [1, 2, 3, 4, 5]
    assert zones[2] == {
        "activity_id": 1234567890,
        "kind": "hr",
        "zone": 3,
        "seconds": 1250.0,
        "low_value": 132.0,
    }
    assert sum(z["seconds"] for z in zones) == pytest.approx(3015.5)


def test_activity_weather_converts_imperial_units() -> None:
    row = only(run_parser(p.parse_activity_weather, "get_activity_weather", RUN), m.ActivityWeather)
    assert row["temperature_c"] == 16.1
    assert row["dew_point_c"] == 8.9
    assert row["wind_speed_mps"] == 3.13
    assert row["wind_gust_mps"] == 5.36
    assert (row["humidity_pct"], row["wind_direction_deg"]) == (62.0, 220.0)
    assert row["condition"] == "Partly Cloudy"
    assert row["issued_at"] == utc(2024, 5, 1, 7)


def test_activity_gear_links_and_fills_gear() -> None:
    ops = run_parser(p.parse_activity_gear, "get_activity_gear", RUN)
    gear_op, link_op = ops
    assert isinstance(gear_op, Upsert) and gear_op.fill_all
    assert isinstance(link_op, Replace)
    assert link_op.rows == [
        {"activity_id": 1234567890, "gear_uuid": "0a1b2c3d4e5f60718293a4b5c6d7e8f9"}
    ]


# --- daily -----------------------------------------------------------------------------------


def test_user_summary() -> None:
    ops = run_parser(p.parse_user_summary, "get_user_summary")
    assert isinstance(ops[0], Upsert) and "avg_spo2" in ops[0].prefer_new
    row = only(ops, m.DailySummary)
    assert row["day"] == date(2024, 5, 1)
    assert (row["steps"], row["step_goal"], row["distance_m"]) == (12450, 10000, 9876.0)
    assert (row["resting_hr"], row["min_hr"], row["max_hr"]) == (48, 45, 172)
    assert (row["avg_stress"], row["stress_high_s"]) == (28, 900)
    assert (row["body_battery_high"], row["body_battery_low"], row["body_battery_at_wake"]) == (
        92,
        21,
        88,
    )
    assert (row["moderate_intensity_min"], row["vigorous_intensity_min"]) == (20, 45)
    assert row["avg_spo2"] is None
    assert row["avg_waking_respiration"] == 15.0
    assert row["sleeping_s"] == 27000


def test_hydration_and_intensity_minutes() -> None:
    hydration = only(run_parser(p.parse_hydration, "get_hydration_data"), m.DailySummary)
    assert (hydration["hydration_ml"], hydration["hydration_goal_ml"]) == (1800.0, 2500.0)
    (op,) = run_parser(p.parse_intensity_minutes, "get_intensity_minutes_data")
    assert isinstance(op, Upsert)
    assert op.keep_old == {"moderate_intensity_min", "vigorous_intensity_min"}
    assert op.rows == [
        {"day": date(2024, 5, 1), "moderate_intensity_min": 20, "vigorous_intensity_min": 45}
    ]


def test_sleep_and_stages() -> None:
    ops = run_parser(p.parse_sleep, "get_sleep_data")
    night = only(ops, m.Sleep)
    assert night["day"] == date(2024, 5, 1)
    assert night["start_utc"] == utc(2024, 4, 30, 21, 15)
    assert night["end_utc"] == utc(2024, 5, 1, 5)
    assert (
        night["duration_s"],
        night["deep_s"],
        night["light_s"],
        night["rem_s"],
        night["awake_s"],
    ) == (
        27000,
        4500,
        16200,
        6300,
        900,
    )
    assert (night["score"], night["score_quality"], night["score_rem"]) == (84, "GOOD", 23)
    assert (night["avg_hr"], night["lowest_hr"]) == (50.4, 47)
    assert (night["avg_spo2"], night["lowest_spo2"]) == (95.0, 89.0)
    assert (night["avg_overnight_hrv"], night["restless_moments"], night["sleep_need_min"]) == (
        62.0,
        31,
        480,
    )
    assert night["body_battery_change"] == 58
    stages = rows(ops, m.SleepStage)
    assert len(stages) == 6
    seconds: dict[str, float] = {}
    for s in stages:
        seconds[s["stage"]] = (
            seconds.get(s["stage"], 0) + (s["end_utc"] - s["start_utc"]).total_seconds()
        )
    assert seconds == {"light": 16200, "deep": 4500, "awake": 900, "rem": 6300}


def test_no_sleep_means_no_rows() -> None:
    empty = {"dailySleepDTO": {"calendarDate": DAY, "sleepTimeSeconds": None}}
    assert run_parser(p.parse_sleep, None, payload=empty) == []


def test_hrv() -> None:
    row = only(run_parser(p.parse_hrv, "get_hrv_data"), m.HrvDaily)
    assert (row["last_night_avg_ms"], row["last_night_5min_high_ms"], row["weekly_avg_ms"]) == (
        62.0,
        85.0,
        58.0,
    )
    assert (
        row["baseline_low_ms"],
        row["baseline_balanced_low_ms"],
        row["baseline_balanced_upper_ms"],
    ) == (
        48.0,
        52.0,
        68.0,
    )
    assert (row["status"], row["feedback"]) == ("BALANCED", "HRV_BALANCED_2")


def test_heart_rates() -> None:
    samples = rows(run_parser(p.parse_heart_rates, "get_heart_rates"), m.HrSample)
    assert samples[0] == {"ts": utc(2024, 5, 1, 0, 0), "bpm": 52}
    assert [s["bpm"] for s in samples] == [52, 51, 64, 70]


def test_stress_and_body_battery() -> None:
    ops = run_parser(p.parse_stress, "get_stress_data")
    assert [s["level"] for s in rows(ops, m.StressSample)] == [25, -1, 40, -2]
    bb = rows(ops, m.BodyBatterySample)
    assert bb == [
        {"ts": utc(2024, 5, 1, 8, 0), "level": 55},
        {"ts": utc(2024, 5, 1, 8, 3), "level": 54},
    ]


def test_respiration_and_spo2() -> None:
    ops = run_parser(p.parse_respiration, "get_respiration_data")
    assert [s["breaths_per_min"] for s in rows(ops, m.RespirationSample)] == [14.0, 13.5]
    fill = [op for op in ops if op.model is m.DailySummary]
    assert isinstance(fill[0], Upsert) and fill[0].keep_old == {"avg_waking_respiration"}
    ops = run_parser(p.parse_spo2, "get_spo2_data")
    assert rows(ops, m.Spo2Sample) == [
        {"ts": utc(2024, 5, 1, 1, 0), "spo2_pct": 95.0},
        {"ts": utc(2024, 5, 1, 1, 1), "spo2_pct": 94.0},
    ]
    assert only(ops, m.DailySummary) == {
        "day": date(2024, 5, 1),
        "avg_spo2": 95.0,
        "lowest_spo2": 89.0,
    }


def test_steps() -> None:
    steps = rows(run_parser(p.parse_steps, "get_steps_data"), m.StepsInterval)
    assert [(s["steps"], s["activity_level"]) for s in steps] == [
        (0, "sleeping"),
        (450, "active"),
        (1600, "highlyActive"),
    ]
    assert steps[1]["start_utc"] == utc(2024, 5, 1, 6) and steps[1]["end_utc"] == utc(
        2024, 5, 1, 6, 15
    )


# --- training and performance ----------------------------------------------------------------


def test_training_readiness_uses_the_morning_snapshot() -> None:
    row = only(
        run_parser(p.parse_training_readiness, "get_training_readiness"), m.TrainingReadiness
    )
    assert (row["score"], row["level"], row["recovery_time_min"]) == (78, "HIGH", 240)
    assert (row["sleep_score_factor"], row["hrv_factor"], row["sleep_history_factor"]) == (
        85,
        95,
        82,
    )
    assert row["feedback"] == "WELL_RECOVERED"


def test_training_status() -> None:
    row = only(run_parser(p.parse_training_status, "get_training_status"), m.TrainingStatus)
    assert row["day"] == date(2024, 5, 1)
    assert row["status"] == "PRODUCTIVE"
    assert (row["acute_load"], row["chronic_load"], row["acwr"], row["acwr_status"]) == (
        512.0,
        455.0,
        1.1,
        "OPTIMAL",
    )
    assert (row["load_low_aerobic"], row["load_high_aerobic"], row["load_anaerobic"]) == (
        410.5,
        520.0,
        95.0,
    )
    assert (row["target_anaerobic_min"], row["target_anaerobic_max"]) == (80.0, 250.0)
    assert row["load_balance_feedback"] == "BALANCED"
    assert (row["heat_acclimation_pct"], row["altitude_acclimation_m"]) == (35.0, 0.0)


def test_max_metrics() -> None:
    row = only(run_parser(p.parse_max_metrics, "get_max_metrics"), m.MaxMetric)
    assert row == {
        "day": date(2024, 5, 1),
        "vo2max_running": 52.4,
        "vo2max_cycling": 49.1,
        "fitness_age": 31.0,
    }


def test_race_predictions() -> None:
    preds = rows(
        run_parser(p.parse_race_predictions, "get_race_predictions", "2024-05"), m.RacePrediction
    )
    assert preds[0] == {
        "day": date(2024, 5, 1),
        "time_5k_s": 1165.0,
        "time_10k_s": 2420.0,
        "time_half_s": 5360.0,
        "time_marathon_s": 11250.0,
    }
    assert len(preds) == 2


def test_endurance_score_with_classification_limits() -> None:
    scores = rows(
        run_parser(p.parse_endurance_score, "get_endurance_score", "2024-05"), m.EnduranceScore
    )
    assert scores == [
        {"day": date(2024, 5, 1), "score": 6100.0, "classification": "TRAINED"},
        {"day": date(2024, 5, 2), "score": 6125.0, "classification": "TRAINED"},
    ]


def test_hill_score() -> None:
    row = only(run_parser(p.parse_hill_score, "get_hill_score", "2024-05"), m.HillScore)
    assert row == {"day": date(2024, 5, 1), "score": 55.0, "endurance": 60.0, "strength": 48.0}


# --- body, records, badges, goals ----------------------------------------------------------


def test_body_composition_converts_grams() -> None:
    row = only(
        run_parser(p.parse_body_composition, "get_body_composition", "2024-05"), m.BodyComposition
    )
    assert row["measured_at"] == utc(2024, 5, 1, 5)
    assert (row["weight_kg"], row["muscle_mass_kg"], row["bone_mass_kg"]) == (72.4, 34.5, 3.3)
    assert (row["bmi"], row["body_fat_pct"], row["body_water_pct"]) == (22.8, 15.2, 58.1)
    assert (row["visceral_fat"], row["metabolic_age"], row["source"]) == (6.0, 30.0, "INDEX_SCALE")


def test_body_composition_zero_readings_are_missing() -> None:
    """A weigh-in without a composition reading reports 0s: weight kept, the rest None."""
    payload = {
        "dateWeightList": [
            {
                "timestampGMT": 1714539600000,
                "weight": 72400.0,
                "bmi": 0.0,
                "bodyFat": 0.0,
                "bodyWater": 0,
                "muscleMass": 0,
                "boneMass": 0,
                "visceralFat": 0.0,
                "metabolicAge": 0,
                "sourceType": "MANUAL",
            }
        ]
    }
    row = only(run_parser(p.parse_body_composition, None, payload=payload), m.BodyComposition)
    assert row["weight_kg"] == 72.4
    composition = ("bmi", "body_fat_pct", "body_water_pct", "muscle_mass_kg", "bone_mass_kg")
    assert {k: row[k] for k in (*composition, "visceral_fat", "metabolic_age")} == dict.fromkeys(
        (*composition, "visceral_fat", "metabolic_age")
    )


def test_blood_pressure() -> None:
    row = only(run_parser(p.parse_blood_pressure, "get_blood_pressure", "2024-05"), m.BloodPressure)
    assert row == {
        "measured_at": utc(2024, 5, 1, 6),
        "systolic": 118,
        "diastolic": 76,
        "pulse": 52,
        "category": "NORMAL",
    }


def test_personal_records_replace_the_set() -> None:
    ops = run_parser(p.parse_personal_records, "get_personal_record", "self")
    assert isinstance(ops[0], Replace) and ops[0].where == {}
    prs = {r["record_id"]: r for r in rows(ops, m.PersonalRecord)}
    assert {k: v["type_key"] for k, v in prs.items()} == {
        9001: "run_5k",
        9002: "longest_run",
        9003: "most_steps_day",
        9004: "pr_type_99",
    }
    assert prs[9001]["value"] == 1185.3
    assert prs[9001]["activity_id"] == 1234567890
    assert prs[9001]["achieved_at"] == utc(2024, 5, 1, 7, 20)
    assert run_parser(p.parse_personal_records, None, "self", None) == []


def test_badges_and_goals() -> None:
    badges = rows(run_parser(p.parse_badges, "get_earned_badges", "self"), m.Badge)
    assert badges[0] == {
        "badge_id": 101,
        "name": "5K Finisher",
        "category": "4",
        "points": 2,
        "earned_at": utc(2024, 5, 1, 7, 30),
        "earned_count": 1,
    }
    goal = only(run_parser(p.parse_goals, "get_goals", "active"), m.Goal)
    assert goal == {
        "goal_id": 501,
        "goal_type": "weekly_running_distance",
        "target_value": 40000.0,
        "start_day": date(2024, 1, 1),
        "end_day": None,
        "status": "active",
    }


@pytest.mark.parametrize("ds", REGISTRY, ids=lambda d: d.name)
@pytest.mark.parametrize("payload", [None, {}, [], "unexpected", 42])
def test_parsers_survive_empty_and_unknown_shapes(ds: Any, payload: Any) -> None:
    """Empty → no rows; a foreign shape → ShapeError at worst (never a crash of another kind)."""
    key = {"daily": DAY, "range": "2024-05", "detail": RUN, "activity": RUN}.get(ds.scope, "self")
    try:
        ops = ds.parser(payload, ParseContext(ds.name, key))
    except ShapeError:
        return
    assert isinstance(ops, list)
    if payload in (None, {}, []):
        assert all(not rows([op], op.model) for op in ops if not isinstance(op, Replace))


# --- writer semantics (database) -------------------------------------------------------------


def _summary(db: Session) -> m.DailySummary:
    db.expire_all()
    row = db.get(m.DailySummary, date(2024, 5, 1))
    assert row is not None
    return row


def test_shared_daily_columns_merge_by_source(db: Session) -> None:
    summary = run_parser(p.parse_user_summary, "get_user_summary")
    spo2 = run_parser(p.parse_spo2, "get_spo2_data")
    store.apply(db, summary)
    assert _summary(db).avg_spo2 is None
    store.apply(db, spo2)
    assert _summary(db).avg_spo2 == 95.0
    store.apply(db, summary)  # the summary has no SpO2: keeps the stored one
    assert _summary(db).avg_spo2 == 95.0
    with_spo2 = load("get_user_summary") | {"averageSpo2": 96.0}
    store.apply(db, p.parse_user_summary(with_spo2, ParseContext("user_summary", DAY)))
    assert _summary(db).avg_spo2 == 96.0  # primary source wins when it has a value
    store.apply(db, spo2)
    assert _summary(db).avg_spo2 == 96.0  # secondary source only fills gaps
    assert _summary(db).steps == 12450


def test_replace_and_patch(db: Session) -> None:
    activity = p.parse_activity(load("get_activities")[0], ParseContext("activity", RUN))
    store.apply(db, activity)
    splits = run_parser(p.parse_activity_splits, "get_activity_splits", RUN)
    store.apply(db, splits)
    store.apply(db, splits)
    count = select(func.count()).select_from(m.ActivityLap)
    assert db.scalar(count) == 2
    one_lap = load("get_activity_splits")
    one_lap["lapDTOs"] = one_lap["lapDTOs"][:1]
    store.apply(db, p.parse_activity_splits(one_lap, ParseContext("activity_splits", RUN)))
    assert db.scalar(count) == 1
    store.apply(db, run_parser(p.parse_activity_summary, "get_activity", RUN))
    db.expire_all()
    a = db.get(m.Activity, 1234567890)
    assert a is not None
    assert a.avg_temperature_c == 18.5  # filled
    assert a.distance_m == 10050.0  # list value untouched
    store.apply(db, [Patch(m.Activity, {"activity_id": 1234567890}, {"name": "Changed"})])
    db.expire_all()
    assert db.get(m.Activity, 1234567890).name == "Morning Run"  # type: ignore[union-attr]
    store.apply(
        db, [Patch(m.Activity, {"activity_id": 1234567890}, {"name": "Changed"}, overwrite=True)]
    )
    db.expire_all()
    assert db.get(m.Activity, 1234567890).name == "Changed"  # type: ignore[union-attr]


def test_raw_payload_change_detection(db: Session) -> None:
    first = store.store_raw(db, "sleep", DAY, "get_sleep_data", {"a": 1, "b": [1, 2]})
    assert first.changed and not first.parsed
    store.mark_parsed(db, "sleep", DAY)
    same = store.store_raw(db, "sleep", DAY, "get_sleep_data", {"b": [1, 2], "a": 1})
    assert not same.changed and same.parsed
    changed = store.store_raw(db, "sleep", DAY, "get_sleep_data", {"a": 2})
    assert changed.changed and not changed.parsed
    raw = db.scalar(select(m.RawPayload).where(m.RawPayload.dataset == "sleep"))
    assert raw is not None and raw.parsed_at is None and raw.payload == {"a": 2}
    store.store_raw(db, "hrv", DAY, "get_hrv_data", None)
    db.expire_all()
    empty = db.scalar(select(m.RawPayload).where(m.RawPayload.dataset == "hrv"))
    assert empty is not None and empty.payload is None


# --- FIT -----------------------------------------------------------------------------------


T0 = utc(2024, 5, 1, 7)


def test_record_rows_convert_fit_units() -> None:
    frames: list[dict[str, Any]] = [
        {
            "timestamp": T0,
            "position_lat": 536870912,  # 45.0 degrees in semicircles
            "position_long": 83513253,
            "enhanced_altitude": 230.4,
            "altitude": 999.0,
            "distance": 0.0,
            "enhanced_speed": 3.31,
            "speed": 9.9,
            "heart_rate": 141,
            "cadence": 85,
            "fractional_cadence": 0.5,
            "power": 281,
            "temperature": 18,
            "vertical_oscillation": 89.0,
            "stance_time": 248.0,
            "step_length": 1162.0,
            "enhanced_respiration_rate": 34.5,
        },
        {
            "timestamp": T0 + timedelta(seconds=1),
            "position_lat": None,
            "position_long": 83513253,
            "heart_rate": 142,
        },
        {"timestamp": T0 + timedelta(seconds=1, milliseconds=500), "distance": 3.3},
        {"heart_rate": 150},  # no timestamp: skipped
    ]
    first, second = fit.record_rows(frames, activity_id=7, sport_group="run", start=T0)
    assert first["t_s"] == 0 and first["ts"] == T0
    assert (first["lat"], first["lon"]) == (pytest.approx(45.0), pytest.approx(7.0, abs=1e-6))
    assert (first["altitude_m"], first["speed_mps"]) == (230.4, 3.31)
    assert (first["hr"], first["cadence"], first["power_w"]) == (141, 171, 281)
    assert (
        first["vertical_oscillation_cm"],
        first["ground_contact_ms"],
        first["stride_length_m"],
    ) == (
        8.9,
        248.0,
        1.162,
    )
    assert (first["temperature_c"], first["respiration_rate"]) == (18.0, 34.5)
    assert second["t_s"] == 1
    assert (second["lat"], second["lon"]) == (None, None)
    assert (second["hr"], second["distance_m"]) == (142, 3.3)  # same-second records merge
    ride = fit.record_rows([{"timestamp": T0, "cadence": 88}], activity_id=7, sport_group="ride")
    assert ride[0]["cadence"] == 88


def test_extract_fit_from_zips() -> None:
    raw = make_fit(fit_points(T0, 3))
    assert fit.is_fit(raw)
    assert fit.extract_fit(zip_of("123_ACTIVITY.fit", raw)) == raw
    assert fit.extract_fit(raw) == raw
    assert fit.extract_fit(zip_of("123.gpx", b"<gpx/>")) is None
    assert fit.extract_fit(b"not a zip") is None
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("folder/", b"")
        zf.writestr("folder/A.FIT", raw)
    assert fit.extract_fit(buf.getvalue()) == raw


def test_decode_a_synthetic_fit_file() -> None:
    records = fit.read_records(make_fit(fit_points(T0, 60)))
    assert len(records) == 60
    out = fit.record_rows(records, activity_id=7, sport_group="run", start=T0)
    assert [r["t_s"] for r in out] == list(range(60))
    assert out[10]["lat"] == pytest.approx(45.0003, abs=1e-6)
    assert out[10]["distance_m"] == 33.0
    assert out[10]["cadence"] == 172
    assert out[10]["speed_mps"] == 3.3
    assert fit.read_records(b"\x0e\x10garbage") == []
