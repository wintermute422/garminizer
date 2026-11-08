"""Demo physiology: sleep, a minute-level all-day timeline and Garmin-style daily metrics.

Everything is driven by training load so the dashboards show real relationships: hard weeks
suppress HRV and raise resting HR, good sleep charges Body Battery, fitness lifts VO2max.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]

STAGE_DEEP, STAGE_LIGHT, STAGE_REM, STAGE_AWAKE = "deep", "light", "rem", "awake"


@dataclass(frozen=True)
class Night:
    """Sleep that ends on the morning of `day` (Garmin keys sleep by the wake-up day)."""

    day: date
    bed_utc: datetime
    wake_utc: datetime
    stages: list[tuple[datetime, datetime, str]]

    @property
    def duration_s(self) -> int:
        return int((self.wake_utc - self.bed_utc).total_seconds())

    def seconds_in(self, stage: str) -> int:
        return int(sum((e - s).total_seconds() for s, e, st in self.stages if st == stage))


def local_dt(day: date, hour: float, tz: ZoneInfo) -> datetime:
    base = datetime(day.year, day.month, day.day, tzinfo=tz)
    return base + timedelta(hours=hour)


def make_night(
    day: date, tz: ZoneInfo, rng: np.random.Generator, *, sick: bool, race_tomorrow: bool
) -> Night:
    prev = day - timedelta(days=1)
    weekend_night = prev.weekday() in (4, 5)
    bed_h = 23.0 + (0.9 if weekend_night else 0.0) - (0.6 if race_tomorrow else 0.0)
    bed_h += float(rng.normal(0, 0.45))
    wake_h = (8.1 if day.weekday() >= 5 else 6.7) + float(rng.normal(0, 0.25))
    if race_tomorrow:
        wake_h = 6.0 + float(rng.normal(0, 0.1))
    if sick:
        wake_h += 1.0
    bed = local_dt(prev, bed_h, tz).astimezone(ZoneInfo("UTC"))
    wake = local_dt(day, wake_h, tz).astimezone(ZoneInfo("UTC"))
    return Night(day, bed, wake, _hypnogram(bed, wake, rng))


def _hypnogram(
    bed: datetime, wake: datetime, rng: np.random.Generator
) -> list[tuple[datetime, datetime, str]]:
    """~90-minute cycles: deep sleep early in the night, REM late, short awakenings."""
    out: list[tuple[datetime, datetime, str]] = []
    t = bed
    onset = timedelta(minutes=float(rng.uniform(6, 18)))
    out.append((t, t + onset, STAGE_AWAKE))
    t += onset
    cycle = 0
    while t < wake:
        deep = max(30 - 7 * cycle + rng.normal(0, 4), 3)
        rem = min(4 + 5 * cycle + rng.normal(0, 3), 28)
        light1 = rng.uniform(18, 30)
        light2 = rng.uniform(12, 22)
        for minutes, stage in (
            (light1, STAGE_LIGHT),
            (deep, STAGE_DEEP),
            (light2, STAGE_LIGHT),
            (rem, STAGE_REM),
        ):
            end = min(t + timedelta(minutes=float(max(minutes, 1))), wake)
            if end > t:
                out.append((t, end, stage))
            t = end
            if t >= wake:
                break
        if t < wake and rng.random() < 0.55:
            end = min(t + timedelta(minutes=float(rng.uniform(1, 6))), wake)
            out.append((t, end, STAGE_AWAKE))
            t = end
        cycle += 1
    return out


def sleep_score(night: Night, hrv_ratio: float, stress: float) -> dict[str, int]:
    """Garmin-like sub-scores (0-100) and overall score."""
    hours = night.duration_s / 3600
    total = max(night.duration_s, 1)
    deep = night.seconds_in(STAGE_DEEP) / total
    rem = night.seconds_in(STAGE_REM) / total
    awake = night.seconds_in(STAGE_AWAKE) / total
    s_duration = int(np.clip(100 - 22 * abs(hours - 8.0) ** 1.3, 20, 100))
    s_deep = int(np.clip(100 - 400 * abs(deep - 0.2), 25, 100))
    s_rem = int(np.clip(100 - 380 * abs(rem - 0.23), 25, 100))
    s_light = int(np.clip(100 - 150 * abs(1 - deep - rem - awake - 0.55), 30, 100))
    s_awake = int(np.clip(100 - 900 * max(awake - 0.03, 0), 20, 100))
    s_stress = int(np.clip(100 - 2.5 * max(stress - 12, 0), 20, 100))
    overall = (
        0.32 * s_duration
        + 0.16 * s_deep
        + 0.16 * s_rem
        + 0.08 * s_light
        + 0.14 * s_awake
        + 0.14 * s_stress
        + 12 * (hrv_ratio - 1)
    )
    return {
        "score": int(np.clip(round(overall * 0.88 + 2), 25, 99)),
        "score_duration": s_duration,
        "score_deep": s_deep,
        "score_rem": s_rem,
        "score_light": s_light,
        "score_awakenings": s_awake,
        "score_stress": s_stress,
    }


def sleep_quality(score: int) -> str:
    if score >= 90:
        return "EXCELLENT"
    if score >= 80:
        return "GOOD"
    if score >= 60:
        return "FAIR"
    return "POOR"


@dataclass
class ActivityMinutes:
    """Per-minute view of one activity for the all-day timeline."""

    start_utc: datetime
    hr: FloatArray  # mean HR per minute
    steps: FloatArray  # steps per minute
    resp: FloatArray
    hr_frac: FloatArray  # fraction of HR reserve per minute


@dataclass
class Timeline:
    """Minute-resolution all-day series in UTC from `t0`."""

    t0: datetime
    hr: FloatArray
    stress: FloatArray
    body_battery: FloatArray
    resp: FloatArray
    spo2: FloatArray
    steps: FloatArray
    asleep: npt.NDArray[np.bool_]
    in_activity: npt.NDArray[np.bool_]
    hr_frac: FloatArray = field(default_factory=lambda: np.zeros(0))

    def index(self, t: datetime) -> int:
        return int((t - self.t0).total_seconds() // 60)


@dataclass
class _Layers:
    asleep: npt.NDArray[np.bool_]
    in_act: npt.NDArray[np.bool_]
    act_hr: FloatArray
    act_steps: FloatArray
    act_resp: FloatArray
    hr_frac: FloatArray


def _layers(
    t0: datetime, minutes: int, nights: list[Night], activities: list[ActivityMinutes]
) -> _Layers:
    lay = _Layers(
        np.zeros(minutes, dtype=bool),
        np.zeros(minutes, dtype=bool),
        np.full(minutes, np.nan),
        np.zeros(minutes),
        np.full(minutes, np.nan),
        np.zeros(minutes),
    )

    def idx(t: datetime) -> int:
        return int((t - t0).total_seconds() // 60)

    for n in nights:
        a, b = max(idx(n.bed_utc), 0), min(idx(n.wake_utc), minutes)
        if b > a:
            lay.asleep[a:b] = True
    for act in activities:
        a = idx(act.start_utc)
        b = min(a + len(act.hr), minutes)
        if a < 0 or b <= a:
            continue
        k = b - a
        lay.in_act[a:b] = True
        lay.act_hr[a:b] = act.hr[:k]
        lay.act_steps[a:b] = act.steps[:k]
        lay.act_resp[a:b] = act.resp[:k]
        lay.hr_frac[a:b] = act.hr_frac[:k]
    lay.asleep &= ~lay.in_act
    return lay


def per_minute_local(
    t0: datetime, minutes: int, tz: ZoneInfo
) -> tuple[FloatArray, npt.NDArray[np.object_]]:
    """Local hour and local date for every minute (computed hourly, then repeated)."""
    hours = [t0 + timedelta(minutes=i) for i in range(0, minutes, 60)]
    local = [t.astimezone(tz) for t in hours]
    local_hours = np.repeat(np.array([t.hour for t in local], dtype=np.float64), 60)[:minutes]
    local_days = np.repeat(np.array([t.date() for t in local], dtype=object), 60)[:minutes]
    return local_hours, local_days


def _background_walking(
    lay: _Layers, local_hours: FloatArray, workday: npt.NDArray[np.bool_], rng: np.random.Generator
) -> FloatArray:
    """Commute on workdays, lunch and errands, plus random short bouts (1 = walking)."""
    minutes = len(local_hours)
    free = ~lay.asleep & ~lay.in_act
    walk = np.zeros(minutes)
    for hour, length in ((7, 18), (12, 12), (17, 20)):
        mask = workday & (local_hours == hour) & free
        walk[mask] = rng.random(int(mask.sum())) < length / 60
    walk[free & (rng.random(minutes) < 0.025)] = 1.0
    return walk


def _body_battery(lay: _Layers, stress: FloatArray, hrv: FloatArray, start: float) -> FloatArray:
    """Charges in sleep (faster with good HRV), drains with stress and exercise."""
    out = np.empty(len(stress))
    cur = start
    charge = (0.17 + 0.003 * (hrv - 55)).tolist()
    asleep, in_act = lay.asleep.tolist(), lay.in_act.tolist()
    stress_l, frac = stress.tolist(), lay.hr_frac.tolist()
    for i in range(len(stress_l)):
        if asleep[i]:
            cur += max(charge[i], 0.05) * (1.05 - cur / 100)
        elif in_act[i]:
            cur -= 0.03 + 0.28 * frac[i] ** 3
        else:
            s = stress_l[i]
            cur += 0.012 if s < 20 else -(0.016 + 0.0013 * s)
        cur = min(max(cur, 5.0), 100.0)
        out[i] = cur
    return out


def build_timeline(
    t0: datetime,
    minutes: int,
    nights: list[Night],
    activities: list[ActivityMinutes],
    *,
    daily_rhr: dict[date, float],
    daily_hrv: dict[date, float],
    tz: ZoneInfo,
    rng: np.random.Generator,
    bb_start: float = 70.0,
) -> Timeline:
    lay = _layers(t0, minutes, nights, activities)
    local_hours, local_days = per_minute_local(t0, minutes, tz)
    workday = np.array([d.weekday() < 5 for d in local_days])
    rhr = np.array([daily_rhr.get(d, 52.0) for d in local_days])
    hrv = np.array([daily_hrv.get(d, 60.0) for d in local_days])
    free = ~lay.asleep & ~lay.in_act

    walk = _background_walking(lay, local_hours, workday, rng)
    bg_steps = walk * rng.uniform(70, 115, minutes) + free * rng.poisson(2.0, minutes)
    steps = np.where(lay.in_act, lay.act_steps, np.where(lay.asleep, 0.0, bg_steps))

    cycle = np.sin(2 * math.pi * np.arange(minutes) / 92.0)
    hr_sleep = rhr + 2.5 + 3 * cycle + rng.normal(0, 1.5, minutes)
    hr_awake = rhr + 17 + 22 * walk + rng.normal(0, 4, minutes)
    hr = np.where(lay.in_act, lay.act_hr, np.where(lay.asleep, hr_sleep, hr_awake))
    hr = np.where(np.isnan(hr), hr_awake, hr)

    # Stress: workday load, calmer weekends/evenings, elevated after hard sessions.
    after = np.convolve(lay.hr_frac, np.ones(45), mode="full")[:minutes] / 45
    office = workday & (local_hours >= 9) & (local_hours < 18)
    awake_stress = np.where(office, 34.0, 22.0) + 25 * after + 6 * np.sin(local_hours / 3)
    awake_stress += rng.normal(0, 9, minutes) - 0.25 * (hrv - 60) + 6 * walk
    # Occasional stressful blocks (deadlines, meetings, commutes): 30-120 min of elevated stress.
    starts = np.flatnonzero(office & (rng.random(minutes) < 1 / 600))
    for s0 in starts:
        span = int(rng.integers(30, 120))
        awake_stress[s0 : s0 + span] += float(rng.uniform(20, 45))
    stress = np.where(lay.asleep, np.clip(14 + rng.normal(0, 5, minutes), 2, 40), awake_stress)
    stress = np.where(lay.in_act, -2.0, np.clip(np.round(stress), 0, 99))

    bb = _body_battery(lay, stress, hrv, bb_start)
    resting_resp = np.where(
        lay.asleep, 13.8 + rng.normal(0, 0.6, minutes), 15.6 + rng.normal(0, 0.9, minutes)
    )
    resp = np.where(lay.in_act, lay.act_resp, resting_resp)
    resp = np.where(np.isnan(resp), 15.6, resp)
    spo2 = np.where(lay.asleep, np.clip(95.6 + rng.normal(0, 1.2, minutes), 86, 100), np.nan)
    return Timeline(
        t0=t0,
        hr=np.round(hr),
        stress=stress,
        body_battery=np.round(bb),
        resp=resp,
        spo2=np.round(spo2),
        steps=np.round(steps),
        asleep=lay.asleep,
        in_activity=lay.in_act,
        hr_frac=lay.hr_frac,
    )


# --------------------------------------------------------------------------- daily metrics


def readiness(
    sleep_score_v: int,
    hrv_ratio: float,
    acwr: float,
    recovery_h: float,
    stress_3d: float,
    sleep_3d: float,
) -> dict[str, int | str]:
    f_sleep = sleep_score_v
    f_hrv = int(np.clip(72 + 260 * (hrv_ratio - 1), 5, 100))
    f_acwr = int(np.clip(100 - 120 * max(acwr - 1.0, 0) - 60 * max(0.8 - acwr, 0), 5, 100))
    f_recovery = int(np.clip(100 - 2.2 * recovery_h, 5, 100))
    f_stress = int(np.clip(110 - 2.0 * stress_3d, 5, 100))
    f_sleep_hist = int(np.clip(sleep_3d, 5, 100))
    score = (
        0.25 * f_sleep
        + 0.22 * f_hrv
        + 0.13 * f_acwr
        + 0.2 * f_recovery
        + 0.1 * f_stress
        + 0.1 * f_sleep_hist
    )
    s = int(np.clip(round(50 + (score - 62) * 1.7), 1, 100))  # spread like Garmin
    level = (
        "PRIME"
        if s >= 95
        else "HIGH"
        if s >= 75
        else "MODERATE"
        if s >= 50
        else "LOW"
        if s >= 25
        else "POOR"
    )
    return {
        "score": s,
        "level": level,
        "sleep_score_factor": f_sleep,
        "hrv_factor": f_hrv,
        "acwr_factor": f_acwr,
        "recovery_factor": f_recovery,
        "recovery_time_min": int(recovery_h * 60),
        "stress_history_factor": f_stress,
        "sleep_history_factor": f_sleep_hist,
    }


def training_status(
    acwr: float, vo2_trend_14d: float, tsb: float, recently_raced: bool, sick: bool
) -> str:
    if sick:
        return "RECOVERY"
    if acwr > 1.5:
        return "OVERREACHING"
    if recently_raced and tsb > 5:
        return "PEAKING"
    if acwr < 0.65:
        return "DETRAINING" if vo2_trend_14d < 0 else "RECOVERY"
    if vo2_trend_14d > 0.25:
        return "PRODUCTIVE"
    if vo2_trend_14d < -0.25 and acwr >= 1.0:
        return "UNPRODUCTIVE"
    return "MAINTAINING"


def daniels_time_s(vdot: float, distance_m: float) -> float:
    """Race time for a VDOT via Daniels & Gilbert (bisection on duration)."""
    lo, hi = distance_m / 600.0, distance_m / 100.0  # minutes
    for _ in range(60):
        t = (lo + hi) / 2
        v = distance_m / t
        vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
        pct = 0.8 + 0.1894393 * math.exp(-0.012778 * t) + 0.2989558 * math.exp(-0.1932605 * t)
        if vo2 / pct > vdot:
            lo = t
        else:
            hi = t
    return (lo + hi) / 2 * 60


def endurance_class(score: float) -> str:
    for limit, name in (
        (3000, "UNTRAINED"),
        (4500, "RECREATIONAL"),
        (5500, "INTERMEDIATE"),
        (6500, "TRAINED"),
        (7500, "WELL_TRAINED"),
        (8500, "EXPERT"),
        (9500, "SUPERIOR"),
    ):
        if score < limit:
            return name
    return "ELITE"
