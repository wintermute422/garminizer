"""Daily demo rows: summaries, sleep, HRV, readiness, training status and performance metrics."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo

import numpy as np

from garminizer import models as m
from garminizer.db.base import Base
from garminizer.demo import physiology as phys
from garminizer.demo.calendar import Calendar
from garminizer.sports import FOOT_GROUPS

AGE, HEIGHT_CM = 35.0, 178.0
Rows = dict[type[Base], list[dict[str, Any]]]


class DayLike(Protocol):
    day: date
    vo2max: float
    rhr: float
    hrv: float
    ctl: float
    atl: float
    weight: float
    sick: bool
    load: float


def _day_slices(tl: phys.Timeline, tz: ZoneInfo) -> dict[date, slice]:
    _, local_days = phys.per_minute_local(tl.t0, len(tl.hr), tz)
    out: dict[date, slice] = {}
    start = 0
    for i in range(1, len(local_days) + 1):
        if i == len(local_days) or local_days[i] != local_days[start]:
            out[local_days[start]] = slice(start, i)
            start = i
    return out


def _mean(a: np.ndarray[Any, Any]) -> float | None:
    f = a[np.isfinite(a)]
    return round(float(np.mean(f)), 1) if f.size else None


def _te_bucket(row: dict[str, Any]) -> str:
    if (row["anaerobic_te"] or 0) >= 2.0:
        return "anaerobic"
    if (row["aerobic_te"] or 0) >= 3.5:
        return "high_aerobic"
    return "low_aerobic"


def _summary_row(
    day: date,
    st: DayLike,
    tl: phys.Timeline,
    sl: slice,
    acts: list[dict[str, Any]],
    rng: np.random.Generator,
    wake_idx: int | None,
    step_goal: int,
) -> dict[str, Any]:
    asleep, in_act = tl.asleep[sl], tl.in_activity[sl]
    awake_free = ~asleep & ~in_act
    stress = tl.stress[sl]
    valid = (stress >= 0) & awake_free
    bb = tl.body_battery[sl]
    diffs = np.diff(bb)
    frac = tl.hr_frac[sl]
    steps = float(np.sum(tl.steps[sl]))
    act_steps = sum(a["steps"] or 0 for a in acts)
    foot_dist = sum(a["distance_m"] or 0 for a in acts if a["sport_group"] in FOOT_GROUPS)
    gain = sum(a["elevation_gain_m"] or 0 for a in acts if a["sport_group"] in FOOT_GROUPS)
    bmr = 10 * st.weight + 6.25 * HEIGHT_CM - 5 * AGE + 5
    active = sum(a["calories"] or 0 for a in acts) + max(steps - act_steps, 0) * 0.04
    cats = np.where(valid, stress, -1)
    sweat = sum(a["water_estimated_ml"] or 0 for a in acts)
    logged = rng.random() < 0.65
    return {
        "day": day,
        "steps": int(steps),
        "step_goal": step_goal,
        "distance_m": round(max(steps - act_steps, 0) * 0.76 + foot_dist, 1),
        "floors_up": round(gain / 3 + float(rng.uniform(3, 12)), 1),
        "floors_down": round(gain / 3 + float(rng.uniform(3, 11)), 1),
        "floors_goal": 10.0,
        "total_kcal": round(bmr + active),
        "active_kcal": round(active),
        "bmr_kcal": round(bmr),
        "resting_hr": round(st.rhr),
        "min_hr": int(np.nanmin(tl.hr[sl])),
        "max_hr": int(np.nanmax(tl.hr[sl])),
        "avg_stress": round(float(np.mean(stress[valid]))) if valid.any() else None,
        "max_stress": int(np.max(stress[valid])) if valid.any() else None,
        "stress_rest_s": int(np.sum((cats >= 0) & (cats <= 25))) * 60,
        "stress_low_s": int(np.sum((cats > 25) & (cats <= 50))) * 60,
        "stress_medium_s": int(np.sum((cats > 50) & (cats <= 75))) * 60,
        "stress_high_s": int(np.sum(cats > 75)) * 60,
        "body_battery_high": int(np.max(bb)),
        "body_battery_low": int(np.min(bb)),
        "body_battery_charged": int(np.sum(diffs[diffs > 0])),
        "body_battery_drained": int(-np.sum(diffs[diffs < 0])),
        "body_battery_at_wake": int(tl.body_battery[wake_idx]) if wake_idx is not None else None,
        "moderate_intensity_min": int(np.sum(in_act & (frac >= 0.5) & (frac < 0.7))),
        "vigorous_intensity_min": int(np.sum(in_act & (frac >= 0.7))),
        "intensity_goal_min": 150,
        "avg_spo2": None,
        "lowest_spo2": None,
        "avg_waking_respiration": _mean(tl.resp[sl][awake_free]),
        "hydration_ml": round(float(rng.uniform(1800, 3200)) + sweat * 0.5) if logged else None,
        "hydration_goal_ml": round(2500 + sweat),
        "sedentary_s": int(np.sum(awake_free & (tl.steps[sl] < 30))) * 60,
        "active_s": int(np.sum(awake_free & (tl.steps[sl] >= 30))) * 60,
        "highly_active_s": int(np.sum(in_act)) * 60,
        "sleeping_s": int(np.sum(asleep)) * 60,
    }


def _sleep_row(
    night: phys.Night, st: DayLike, tl: phys.Timeline, hrv_ratio: float, rng: np.random.Generator
) -> dict[str, Any]:
    a, b = max(tl.index(night.bed_utc), 0), min(tl.index(night.wake_utc), len(tl.hr) - 1)
    win = slice(a, b)
    asleep = tl.asleep[win]
    hr = tl.hr[win][asleep]
    resp = tl.resp[win][asleep]
    spo2 = tl.spo2[win][asleep]
    stress = tl.stress[win][asleep]
    avg_stress = float(np.mean(stress[stress >= 0])) if (stress >= 0).any() else 15.0
    scores = phys.sleep_score(night, hrv_ratio, avg_stress)
    awakenings = sum(1 for _, _, s in night.stages[1:] if s == phys.STAGE_AWAKE)
    quality = phys.sleep_quality(scores["score"])
    feedback = {
        "EXCELLENT": "POSITIVE_RESTFUL",
        "GOOD": "POSITIVE_LONG_AND_DEEP",
        "FAIR": "NEUTRAL",
        "POOR": "NEGATIVE_SHORT_AND_POOR",
    }[quality]
    return {
        "day": night.day,
        "start_utc": night.bed_utc,
        "end_utc": night.wake_utc,
        "duration_s": night.duration_s - night.seconds_in(phys.STAGE_AWAKE),
        "deep_s": night.seconds_in(phys.STAGE_DEEP),
        "light_s": night.seconds_in(phys.STAGE_LIGHT),
        "rem_s": night.seconds_in(phys.STAGE_REM),
        "awake_s": night.seconds_in(phys.STAGE_AWAKE),
        "unmeasurable_s": 0,
        **scores,
        "score_quality": quality,
        "avg_hr": _mean(hr),
        "lowest_hr": int(np.nanmin(hr)) if hr.size else None,
        "avg_respiration": _mean(resp),
        "lowest_respiration": round(float(np.nanmin(resp)), 1) if resp.size else None,
        "highest_respiration": round(float(np.nanmax(resp)), 1) if resp.size else None,
        "avg_spo2": _mean(spo2),
        "lowest_spo2": float(np.nanmin(spo2)) if np.isfinite(spo2).any() else None,
        "avg_stress": round(avg_stress, 1),
        "avg_overnight_hrv": round(st.hrv, 1),
        "restless_moments": int(awakenings * 7 + rng.integers(8, 30)),
        "awake_count": awakenings,
        "body_battery_change": int(tl.body_battery[b] - tl.body_battery[a]),
        "sleep_need_min": int(480 + min(st.load, 300) / 10 + (30 if st.sick else 0)),
        "feedback": feedback,
    }


def _hrv_rows(states: list[DayLike]) -> tuple[list[dict[str, Any]], list[float]]:
    values = [s.hrv for s in states]
    rows, baselines = [], []
    for i, s in enumerate(states):
        week = values[max(0, i - 6) : i + 1]
        hist = values[max(0, i - 27) : i + 1]
        mean, sd = float(np.mean(hist)), float(np.std(hist)) if len(hist) > 1 else 5.0
        half = max(0.8 * sd, 4.0)
        weekly = float(np.mean(week))
        lo, hi, floor = mean - half, mean + half, mean - half - 7
        status = None
        if i >= 20:
            if lo <= weekly <= hi:
                status = "BALANCED"
            elif weekly < floor:
                status = "LOW"
            else:
                status = "UNBALANCED"
        baselines.append(mean)
        rows.append(
            {
                "day": s.day,
                "last_night_avg_ms": round(s.hrv, 1),
                "last_night_5min_high_ms": round(s.hrv * 1.34, 1),
                "weekly_avg_ms": round(weekly, 1),
                "baseline_low_ms": round(floor, 1) if i >= 20 else None,
                "baseline_balanced_low_ms": round(lo, 1) if i >= 20 else None,
                "baseline_balanced_upper_ms": round(hi, 1) if i >= 20 else None,
                "status": status,
                "feedback": None if status is None else f"HRV_{status}",
            }
        )
    return rows, baselines


def _load_focus(acts: list[dict[str, Any]], ctl: float) -> dict[str, Any]:
    buckets: dict[str, float] = defaultdict(float)
    for a in acts:
        buckets[_te_bucket(a)] += a["training_load"] or 0.0
    optimal = max(ctl, 20) * 28
    targets = {"low_aerobic": (0.35, 0.55), "high_aerobic": (0.30, 0.50), "anaerobic": (0.08, 0.20)}
    feedback = "BALANCED"
    for key, (lo, _) in targets.items():
        if buckets[key] < lo * optimal * 0.8:
            feedback = f"{key.upper()}_SHORTAGE"
            break
    row: dict[str, Any] = {f"load_{k}": round(buckets[k], 1) for k in targets}
    for key, (lo, hi) in targets.items():
        row[f"target_{key}_min"] = round(lo * optimal, 1)
        row[f"target_{key}_max"] = round(hi * optimal, 1)
    row["load_balance_feedback"] = feedback
    return row


def build_daily_rows(
    tl: phys.Timeline,
    cal: Calendar,
    states: list[Any],
    nights: list[phys.Night],
    act_rows: list[dict[str, Any]],
    tz: ZoneInfo,
    rng: np.random.Generator,
) -> Rows:
    slices = _day_slices(tl, tz)
    acts_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for a in act_rows:
        acts_by_day[a["start_time_local"].date()].append(a)
    nights_by_day = {n.day: n for n in nights}
    hrv_rows, baselines = _hrv_rows(states)
    rows: Rows = defaultdict(list)
    rows[m.HrvDaily] = hrv_rows

    sleep_scores: list[int] = []
    daily_stress: list[float] = []
    heat = 0.0
    step_hist: list[int] = []
    for i, st in enumerate(states):
        day: date = st.day
        night = nights_by_day[day]
        hrv_ratio = st.hrv / baselines[i] if baselines[i] else 1.0
        sleep = _sleep_row(night, st, tl, hrv_ratio, rng)
        rows[m.Sleep].append(sleep)
        rows[m.SleepStage].extend(
            {"day": day, "start_utc": a, "end_utc": b, "stage": s} for a, b, s in night.stages
        )
        sleep_scores.append(sleep["score"])
        wake_idx = min(tl.index(night.wake_utc), len(tl.hr) - 1)
        goal = max(7500, int(round(np.mean(step_hist[-7:]) / 100) * 100)) if step_hist else 8000
        summary = _summary_row(day, st, tl, slices[day], acts_by_day[day], rng, wake_idx, goal)
        summary["avg_spo2"], summary["lowest_spo2"] = sleep["avg_spo2"], sleep["lowest_spo2"]
        rows[m.DailySummary].append(summary)
        step_hist.append(summary["steps"])
        daily_stress.append(float(summary["avg_stress"] or 25))

        acwr = st.atl / st.ctl if st.ctl > 0 else 1.0
        recovery_h = 0.0
        for k in (1, 2, 3):
            if i - k >= 0:
                recovery_h = max(recovery_h, states[i - k].load * 0.25 - 24 * (k - 1) - 8)
        rd = phys.readiness(
            sleep["score"],
            hrv_ratio,
            acwr,
            float(np.clip(recovery_h, 0, 96)),
            float(np.mean(daily_stress[-4:-1] or [25])),
            float(np.mean(sleep_scores[-4:-1] or [75])),
        )
        rows[m.TrainingReadiness].append({"day": day, **rd, "feedback": f"READINESS_{rd['level']}"})

        window = [
            a for d in (day - timedelta(days=k) for k in range(28)) for a in acts_by_day.get(d, [])
        ]
        hot = any((a["avg_temperature_c"] or 0) > 26 for a in acts_by_day[day])
        heat = min(100.0, heat + 9) if hot else max(0.0, heat - 2.5)
        vo2_trend = st.vo2max - states[max(0, i - 14)].vo2max
        days_to_race = min(((r - day).days for r in cal.race_days if r >= day), default=99)
        status = phys.training_status(
            acwr, vo2_trend, st.ctl - st.atl, 0 <= days_to_race <= 7, st.sick
        )
        acwr_status = (
            "LOW"
            if acwr < 0.8
            else "OPTIMAL"
            if acwr <= 1.3
            else "HIGH"
            if acwr <= 1.5
            else "VERY_HIGH"
        )
        rows[m.TrainingStatus].append(
            {
                "day": day,
                "status": status,
                "acute_load": round(st.atl * 7, 0),
                "chronic_load": round(st.ctl * 7, 0),
                "acwr": round(acwr, 2),
                "acwr_status": acwr_status,
                **_load_focus(window, st.ctl),
                "heat_acclimation_pct": round(heat),
                "altitude_acclimation_m": 0.0,
            }
        )
        for table, row in _performance_rows(st, window).items():
            rows[table].append(row)
        if rng.random() < 4 / 7:
            rows[m.BodyComposition].append(_weigh_in(st, night, i, len(states), rng))
        if i % 14 == int(rng.integers(0, 3)):
            sys_bp, dia_bp = int(rng.normal(118, 6)), int(rng.normal(76, 5))
            rows[m.BloodPressure].append(
                {
                    "measured_at": night.wake_utc + timedelta(minutes=30),
                    "systolic": sys_bp,
                    "diastolic": dia_bp,
                    "pulse": round(st.rhr + 8),
                    "category": bp_category(sys_bp, dia_bp),
                }
            )
    return rows


def bp_category(systolic: int, diastolic: int) -> str:
    """AHA blood pressure category."""
    if systolic >= 140 or diastolic >= 90:
        return "STAGE_2_HIGH"
    if systolic >= 130 or diastolic >= 80:
        return "STAGE_1_HIGH"
    if systolic >= 120:
        return "ELEVATED"
    return "NORMAL"


def _weigh_in(
    st: DayLike, night: phys.Night, i: int, days: int, rng: np.random.Generator
) -> dict[str, Any]:
    w = round(st.weight + float(rng.normal(0, 0.35)), 1)
    fat = 17.5 - 3.5 * i / max(days, 1) + float(rng.normal(0, 0.4))
    return {
        "measured_at": night.wake_utc + timedelta(minutes=12),
        "weight_kg": w,
        "bmi": round(w / (HEIGHT_CM / 100) ** 2, 1),
        "body_fat_pct": round(fat, 1),
        "body_water_pct": round(60.5 - 0.45 * (fat - 15), 1),
        "muscle_mass_kg": round(w * (0.455 + 0.002 * (17.5 - fat)), 1),
        "bone_mass_kg": round(3.2 + float(rng.normal(0, 0.03)), 2),
        "visceral_fat": round(7 - 0.15 * (17.5 - fat), 1),
        "metabolic_age": round(AGE - 4 + 0.6 * (fat - 15)),
        "source": "demo_scale",
    }


def _performance_rows(
    st: DayLike, window: list[dict[str, Any]]
) -> dict[type[Base], dict[str, Any]]:
    """VO2max, race predictions, endurance and hill score for one day (28-day activity window)."""
    day = st.day
    rode = any(a["sport_group"] == "ride" for a in window)
    vdot = st.vo2max * 0.98
    longest_h = max((a["duration_s"] / 3600 for a in window), default=0.0)
    endurance = 2400 + 40 * st.ctl + 550 * min(longest_h, 3)
    trail = sum(1 for a in window if a["sport_type"] in {"trail_running", "hiking"})
    strength = 35 + 0.3 * st.ctl + 2.5 * min(trail, 6)
    endur = 40 + 0.35 * st.ctl
    return {
        m.MaxMetric: {
            "day": day,
            "vo2max_running": round(st.vo2max, 1),
            "vo2max_cycling": round(st.vo2max - 2.5, 1) if rode else None,
            "fitness_age": round(AGE - (st.vo2max - 45) * 0.8, 1),
        },
        m.RacePrediction: {
            "day": day,
            "time_5k_s": round(phys.daniels_time_s(vdot, 5000)),
            "time_10k_s": round(phys.daniels_time_s(vdot, 10000)),
            "time_half_s": round(phys.daniels_time_s(vdot, 21097.5)),
            "time_marathon_s": round(phys.daniels_time_s(vdot, 42195)),
        },
        m.EnduranceScore: {
            "day": day,
            "score": round(endurance),
            "classification": phys.endurance_class(endurance),
        },
        m.HillScore: {
            "day": day,
            "score": round((strength + endur) / 2),
            "endurance": round(endur),
            "strength": round(strength),
        },
    }
