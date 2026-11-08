"""`garminizer demo seed`: fill the database with a synthetic, coherent athlete.

Simulates day by day: morning physiology (VO2max, resting HR, HRV, sleep) depends on the
training load history; workouts come from a periodised calendar; an all-day minute timeline
produces intraday series and daily summaries. Refuses to touch a database with real data.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.analytics.curves import best_distance_times
from garminizer.analytics.physio import normalized_power, trimp_banister
from garminizer.analytics.series import elevation_gain_loss
from garminizer.db.base import SCHEMA, Base
from garminizer.db.bulk import copy_rows
from garminizer.demo import physiology as phys
from garminizer.demo.calendar import Calendar, Workout, build_calendar
from garminizer.demo.daily import build_daily_rows
from garminizer.demo.streams import AthleteState, Places, Synth, synthesize
from garminizer.sports import sport_group

TZ_NAME = "Europe/Berlin"
# Synthetic places (public landmarks' surroundings; routes are random curves, not real tracks).
PLACES = Places(
    home=(48.1520, 11.5920),
    track=(48.1736, 11.5465),
    trailhead=(47.7090, 11.4280),
    mountains=(47.4750, 11.0620),
    race_venue=(48.1374, 11.5755),
)
DEMO_ACTIVITY_ID_BASE = 9_000_000_000_000
DEVICE_ID = 3_400_000_001
HR_MAX, HR_REST_BASE, LTHR, AGE, HEIGHT_CM = 188.0, 52.0, 170.0, 35.0, 178.0
HR_ZONE_FLOORS = [94, 113, 132, 150, 169]  # 50/60/70/80/90 % of max HR


class RealDataError(RuntimeError):
    """Raised when the target database already holds a real (non-demo) athlete."""


@dataclass
class SeedReport:
    days: int
    activities: int
    rows: dict[str, int] = field(default_factory=dict)
    seconds: float = 0.0


@dataclass
class _DayState:
    day: date
    vo2max: float
    rhr: float
    hrv: float
    ctl: float
    atl: float
    weight: float
    sick: bool
    load: float = 0.0


def _seasonal_temp(day: date, hour: float, rng: np.random.Generator) -> float:
    doy = day.timetuple().tm_yday
    base = 9.5 - 10.5 * math.cos(2 * math.pi * (doy - 20) / 365.25)
    diurnal = 4.0 * math.sin(2 * math.pi * (hour - 9) / 24)
    return round(base + diurnal + float(rng.normal(0, 2.5)), 1)


def _weight(i: int, days: int, day: date) -> float:
    doy = day.timetuple().tm_yday
    return 74.6 - 3.0 * (i / max(days, 1)) + 0.7 * math.cos(2 * math.pi * (doy - 5) / 365.25)


def _guard_and_wipe(session: Session) -> None:
    athlete = session.scalar(select(m.Athlete))
    if athlete is not None and not athlete.is_demo:
        raise RealDataError(
            "This database contains real Garmin data; `demo seed` only runs on an empty or "
            "demo database. Point DATABASE_URL at a separate database for the demo."
        )
    names = ", ".join(f'"{SCHEMA}"."{t.name}"' for t in Base.metadata.sorted_tables)
    session.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))


def _minute_view(s: Synth, st: AthleteState) -> phys.ActivityMinutes:
    n_min = max(math.ceil(s.n / 60), 1)
    pad = n_min * 60 - s.n

    def per_min(a: np.ndarray[Any, Any], fill: float = np.nan) -> np.ndarray[Any, Any]:
        b = np.concatenate([a, np.full(pad, fill)]).reshape(n_min, 60)
        valid = np.isfinite(b)
        counts = valid.sum(axis=1)
        sums = np.where(valid, b, 0.0).sum(axis=1)
        out: np.ndarray[Any, Any] = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
        return out

    hr = per_min(s.hr)
    foot = sport_group(s.workout.sport_type) in {"run", "walk", "hike"}
    steps = per_min(np.nan_to_num(s.cadence)) if foot else np.zeros(n_min)
    frac = np.clip(
        (np.nan_to_num(hr, nan=st.hr_rest) - st.hr_rest) / (st.hr_max - st.hr_rest), 0, 1
    )
    return phys.ActivityMinutes(s.start_utc, hr, steps, per_min(s.resp), frac)


def _finite(a: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    out: np.ndarray[Any, Any] = a[np.isfinite(a)]
    return out


def _stat(a: np.ndarray[Any, Any], fn: str, ndigits: int | None = 1) -> float | None:
    f = _finite(a)
    if f.size == 0:
        return None
    v = float(getattr(np, fn)(f))
    return round(v, ndigits) if ndigits is not None else v


def _te_label(aero: float, anaero: float) -> str:
    if anaero >= 3.0:
        return "ANAEROBIC_CAPACITY"
    if anaero >= 2.0:
        return "VO2MAX"
    if aero >= 4.0:
        return "LACTATE_THRESHOLD"
    if aero >= 3.0:
        return "TEMPO"
    if aero >= 2.0:
        return "AEROBIC_BASE"
    return "RECOVERY"


def _summarize(
    s: Synth, st: AthleteState, activity_id: int, rng: np.random.Generator
) -> dict[str, Any]:
    w = s.workout
    group = sport_group(w.sport_type)
    moving = s.speed > 0.3 if group not in {"strength", "cardio"} else np.ones(s.n, dtype=bool)
    hr = s.hr
    trimp = trimp_banister(hr, 1.0, st.hr_rest, st.hr_max)
    above = float(np.sum(_finite(hr) >= LTHR)) / 60
    hard = float(np.sum(s.effort >= 1.0)) / 60
    aero = float(np.clip(0.8 + trimp / 42, 0, 5.0))
    anaero = float(np.clip(0.06 * above + 0.32 * hard, 0, 4.0))
    load = trimp * float(rng.uniform(0.92, 1.12)) + 10 * anaero
    kcal_per_s = (
        (
            -55.0969
            + 0.6309 * np.nan_to_num(hr, nan=st.hr_rest + 30)
            + 0.1988 * st.weight_kg
            + 0.2017 * st.age
        )
        / 4.184
        / 60
    )
    has_alt = bool(np.isfinite(s.alt).any())
    gain, loss = elevation_gain_loss(s.alt) if has_alt else (None, None)
    has_gps = bool(np.isfinite(s.lat).any())
    has_dist = group in {"run", "ride", "swim", "walk", "hike", "winter"}
    np_w = normalized_power(s.power) if group == "ride" else None
    frac = np.clip(
        (np.nan_to_num(hr, nan=st.hr_rest) - st.hr_rest) / (st.hr_max - st.hr_rest), 0, 1
    )
    duration = float(s.n)
    row: dict[str, Any] = {
        "activity_id": activity_id,
        "name": w.name,
        "sport_type": w.sport_type,
        "sport_group": group,
        "start_time_utc": s.start_utc,
        "start_time_local": s.start_utc.astimezone(ZoneInfo(TZ_NAME)).replace(tzinfo=None),
        "duration_s": duration,
        "elapsed_s": duration,
        "moving_s": float(np.sum(moving)),
        "distance_m": round(float(s.dist[-1]), 1) if has_dist else None,
        "elevation_gain_m": round(gain, 1) if gain is not None else None,
        "elevation_loss_m": round(loss, 1) if loss is not None else None,
        "min_elevation_m": _stat(s.alt, "min"),
        "max_elevation_m": _stat(s.alt, "max"),
        "avg_speed_mps": round(float(s.dist[-1]) / max(float(np.sum(moving)), 1), 3)
        if has_dist
        else None,
        "max_speed_mps": _stat(np.convolve(s.speed, np.ones(5) / 5, "same"), "max", 3)
        if has_dist
        else None,
        "avg_hr": round(_stat(hr, "mean") or 0) or None,
        "max_hr": int(_stat(hr, "max") or 0) or None,
        "avg_cadence": _stat(np.where(s.cadence > 0, s.cadence, np.nan), "mean"),
        "max_cadence": _stat(s.cadence, "max"),
        "avg_power_w": _stat(s.power, "mean"),
        "max_power_w": _stat(s.power, "max"),
        "normalized_power_w": round(np_w, 1) if np_w else None,
        "training_stress_score": round(duration * np_w * (np_w / st.ftp_w) / (st.ftp_w * 36), 1)
        if np_w
        else None,
        "intensity_factor": round(np_w / st.ftp_w, 3) if np_w else None,
        "calories": round(float(np.sum(kcal_per_s)), 0),
        "aerobic_te": round(aero, 1),
        "anaerobic_te": round(anaero, 1),
        "training_effect_label": _te_label(aero, anaero),
        "training_load": round(load, 1),
        "vo2max": round(st.vo2max) if group == "run" else None,
        "avg_temperature_c": _stat(s.temp, "mean"),
        "min_temperature_c": _stat(s.temp, "min"),
        "max_temperature_c": _stat(s.temp, "max"),
        "avg_respiration": _stat(s.resp, "mean"),
        "avg_stride_length_m": _stat(s.stride, "mean", 3),
        "avg_vertical_oscillation_cm": _stat(s.vo, "mean"),
        "avg_ground_contact_ms": _stat(s.gct, "mean", 0),
        "avg_vertical_ratio": round(
            (_stat(s.vo, "mean") or 0) / max((_stat(s.stride, "mean", 3) or 1) * 100, 1) * 100, 1
        )
        if group == "run" and w.sport_type != "cross_country_skiing_ws"
        else None,
        "steps": int(np.nansum(s.cadence) / 60) if group in {"run", "walk", "hike"} else None,
        "lap_count": len(s.lap_marks),
        "moderate_intensity_min": int(np.sum((frac >= 0.5) & (frac < 0.7)) / 60),
        "vigorous_intensity_min": int(np.sum(frac >= 0.7) / 60),
        "body_battery_delta": -round(load / 7),
        "water_estimated_ml": round(
            duration / 3600 * 550 * (1 + 0.03 * max(st.temperature_c - 15, 0))
        ),
        "start_lat": float(s.lat[0]) if has_gps else None,
        "start_lon": float(s.lon[0]) if has_gps else None,
        "end_lat": float(s.lat[-1]) if has_gps else None,
        "end_lon": float(s.lon[-1]) if has_gps else None,
        "location_name": "Demo City" if has_gps else None,
        "device_id": DEVICE_ID,
        "has_samples": True,
        "updated_at": datetime.now(UTC),
    }
    row.update({k: v for k, v in s.extra.items() if k in m.Activity.__table__.c})
    return row


def _laps(s: Synth, activity_id: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    marks = [*s.lap_marks, (s.n, "end")]
    for i in range(len(marks) - 1):
        a, b = marks[i][0], max(marks[i + 1][0], marks[i][0] + 1)
        seg = slice(a, b)
        d0 = float(s.dist[a - 1]) if a > 0 else 0.0
        dist = float(s.dist[b - 1]) - d0
        dur = float(b - a)
        alt = s.alt[seg]
        gain, loss = elevation_gain_loss(alt) if np.isfinite(alt).any() else (None, None)
        out.append(
            {
                "activity_id": activity_id,
                "lap_index": i,
                "start_time_utc": s.start_utc + timedelta(seconds=a),
                "duration_s": dur,
                "moving_s": float(np.sum(s.speed[seg] > 0.3)) or dur,
                "distance_m": round(dist, 1),
                "avg_speed_mps": round(dist / dur, 3) if dur else None,
                "max_speed_mps": _stat(s.speed[seg], "max", 3),
                "avg_hr": round(_stat(s.hr[seg], "mean") or 0) or None,
                "max_hr": int(_stat(s.hr[seg], "max") or 0) or None,
                "avg_cadence": _stat(np.where(s.cadence[seg] > 0, s.cadence[seg], np.nan), "mean"),
                "avg_power_w": _stat(s.power[seg], "mean"),
                "max_power_w": _stat(s.power[seg], "max"),
                "elevation_gain_m": round(gain, 1) if gain is not None else None,
                "elevation_loss_m": round(loss, 1) if loss is not None else None,
                "intensity": marks[i][1],
            }
        )
    return out


def _int_or_none(v: float) -> int | None:
    return None if math.isnan(v) else round(v)


def _sample_rows(s: Synth, activity_id: int) -> list[tuple[Any, ...]]:
    def fl(a: np.ndarray[Any, Any], nd: int) -> list[float | None]:
        return [None if math.isnan(x) else round(x, nd) for x in a.tolist()]

    def it(a: np.ndarray[Any, Any]) -> list[int | None]:
        return [_int_or_none(x) for x in a.tolist()]

    lat, lon = fl(s.lat, 6), fl(s.lon, 6)
    alt, dist, spd = fl(s.alt, 1), fl(s.dist, 1), fl(s.speed, 3)
    hr, cad, pw = it(s.hr), it(s.cadence), it(s.power)
    temp, vo, gct = fl(s.temp, 1), fl(s.vo, 1), fl(s.gct, 0)
    stride, resp = fl(s.stride, 3), fl(s.resp, 1)
    t0 = s.start_utc
    return [
        (
            activity_id,
            i,
            t0 + timedelta(seconds=i),
            lat[i],
            lon[i],
            alt[i],
            dist[i],
            spd[i],
            hr[i],
            cad[i],
            pw[i],
            temp[i],
            vo[i],
            gct[i],
            stride[i],
            resp[i],
        )
        for i in range(s.n)
    ]


SAMPLE_COLUMNS = (
    "activity_id",
    "t_s",
    "ts",
    "lat",
    "lon",
    "altitude_m",
    "distance_m",
    "speed_mps",
    "hr",
    "cadence",
    "power_w",
    "temperature_c",
    "vertical_oscillation_cm",
    "ground_contact_ms",
    "stride_length_m",
    "respiration_rate",
)


def _gear_for(w: Workout, day_index: int) -> str | None:
    if w.kind in {"endurance_ride"}:
        return "demo-bike-road"
    if w.kind == "gravel":
        return "demo-bike-gravel"
    if w.kind in {"trail", "hills"}:
        return "demo-shoe-trail"
    if w.kind in {"race", "intervals"}:
        return "demo-shoe-racer"
    if sport_group(w.sport_type) == "run":
        return ("demo-shoe-a", "demo-shoe-b", "demo-shoe-c")[min(day_index // 250, 2)]
    return None


GEAR = [
    ("demo-shoe-a", "shoes", "Road Trainer (pair 1)", "retired", 800_000.0),
    ("demo-shoe-b", "shoes", "Road Trainer (pair 2)", "retired", 800_000.0),
    ("demo-shoe-c", "shoes", "Road Trainer (pair 3)", "active", 800_000.0),
    ("demo-shoe-trail", "shoes", "Trail Shoe", "active", 700_000.0),
    ("demo-shoe-racer", "shoes", "Carbon Racer", "active", 400_000.0),
    ("demo-bike-road", "bike", "Road Bike", "active", None),
    ("demo-bike-gravel", "bike", "Gravel Bike", "active", None),
]


@dataclass
class _Sim:
    """Accumulates everything the day-by-day simulation produces."""

    session: Session
    rng: np.random.Generator
    tz: ZoneInfo
    cal: Calendar
    report: SeedReport
    states: list[_DayState] = field(default_factory=list)
    nights: list[phys.Night] = field(default_factory=list)
    minute_views: list[phys.ActivityMinutes] = field(default_factory=list)
    act_rows: list[dict[str, Any]] = field(default_factory=list)
    lap_rows: list[dict[str, Any]] = field(default_factory=list)
    weather_rows: list[dict[str, Any]] = field(default_factory=list)
    gear_rows: list[dict[str, Any]] = field(default_factory=list)
    best_runs: dict[float, tuple[float, int, datetime]] = field(default_factory=dict)
    ctl: float = 32.0
    atl: float = 30.0
    vo2_noise: float = 0.0
    act_seq: int = 0

    def morning(self, i: int, day: date) -> _DayState:
        rng, sick = self.rng, day in self.cal.sick_days
        self.vo2_noise = 0.9 * self.vo2_noise + float(rng.normal(0, 0.12))
        vo2 = 50.4 + 0.045 * self.ctl + self.vo2_noise - (0.6 if sick else 0.0)
        tired = max(self.atl - self.ctl, 0.0)
        rhr = HR_REST_BASE - 0.09 * (self.ctl - 35) + 0.12 * tired + (6 if sick else 0)
        hrv = 60 + 0.13 * (self.ctl - 35) - 0.32 * tired - (20 if sick else 0)
        rhr += float(rng.normal(0, 1.1))
        hrv += float(rng.normal(0, 4.2))
        if rng.random() < 0.06:  # a late night out
            hrv, rhr = hrv - 9, rhr + 3
        race_tomorrow = (day + timedelta(days=1)) in self.cal.race_days
        self.nights.append(
            phys.make_night(day, self.tz, rng, sick=sick, race_tomorrow=race_tomorrow)
        )
        weight = _weight(i, self.cal.days, day)
        return _DayState(day, vo2, rhr, hrv, self.ctl, self.atl, weight, sick)

    def workout(self, i: int, ds: _DayState, w: Workout) -> None:
        rng = self.rng
        temp = _seasonal_temp(ds.day, w.start_hour, rng)
        ftp = 3.4 * ds.weight * ds.vo2max / 52
        st = AthleteState(ds.vo2max, ds.rhr, HR_MAX, ds.weight, ftp, self.ctl - self.atl, temp, AGE)
        start_utc = phys.local_dt(ds.day, w.start_hour, self.tz).astimezone(UTC)
        s = synthesize(w, start_utc, st, PLACES, rng)
        self.act_seq += 1
        aid = DEMO_ACTIVITY_ID_BASE + self.act_seq
        row = _summarize(s, st, aid, rng)
        self.act_rows.append(row)
        self.session.execute(insert(m.Activity), [row])  # samples reference it (FK)
        self.lap_rows.extend(_laps(s, aid))
        ds.load += row["training_load"]
        self.minute_views.append(_minute_view(s, st))
        written = copy_rows(self.session, m.ActivitySample, SAMPLE_COLUMNS, _sample_rows(s, aid))
        self.report.rows["activity_sample"] = self.report.rows.get("activity_sample", 0) + written
        if np.isfinite(s.lat).any():
            self.weather_rows.append(_weather(aid, start_utc, temp, ds.day, rng))
        gear = _gear_for(w, i)
        if gear:
            self.gear_rows.append({"activity_id": aid, "gear_uuid": gear})
        if row["sport_group"] == "run" and row["distance_m"]:
            times = best_distance_times(np.arange(s.n, dtype=float), s.dist)
            for dist, secs in times.items():
                if dist not in self.best_runs or secs < self.best_runs[dist][0]:
                    self.best_runs[dist] = (secs, aid, start_utc)

    def evening(self, ds: _DayState) -> None:
        self.ctl += (ds.load - self.ctl) * (1 - math.exp(-1 / 42))
        self.atl += (ds.load - self.atl) * (1 - math.exp(-1 / 7))
        self.states.append(ds)


def seed_demo(
    session: Session, *, end: date | None = None, days: int = 730, seed: int = 42
) -> SeedReport:
    t_start = time.perf_counter()
    rng = np.random.default_rng(seed)
    tz = ZoneInfo(TZ_NAME)
    end = end or datetime.now(tz).date()
    start = end - timedelta(days=days - 1)
    _guard_and_wipe(session)

    sim = _Sim(session, rng, tz, build_calendar(start, days, rng), SeedReport(days, 0))
    for i in range(days):
        day = start + timedelta(days=i)
        ds = sim.morning(i, day)
        for w in sim.cal.on(day):
            sim.workout(i, ds, w)
        sim.evening(ds)

    report = sim.report
    report.activities = sim.act_seq
    _write_core(session, sim.act_rows, sim.lap_rows, sim.weather_rows, sim.gear_rows, report)
    tl = _timeline(start, end, sim.nights, sim.minute_views, sim.states, tz, rng)
    _write_intraday(session, tl, report)
    rows = build_daily_rows(tl, sim.cal, sim.states, sim.nights, sim.act_rows, tz, rng)
    for table, values in rows.items():
        if values:
            session.execute(insert(table), values)
        report.rows[table.__tablename__] = len(values)
    _write_profile(session, sim.states, sim.act_rows, sim.best_runs, rng, report)
    session.add(
        m.SyncRun(
            kind="demo",
            status="ok",
            finished_at=datetime.now(UTC),
            items_written=sum(report.rows.values()),
            message=f"seed={seed}",
        )
    )
    session.flush()
    report.seconds = round(time.perf_counter() - t_start, 1)
    return report


def _weather(
    aid: int, start_utc: datetime, temp: float, day: date, rng: np.random.Generator
) -> dict[str, Any]:
    wet = day.month in (3, 4, 5, 10, 11)
    condition = str(
        rng.choice(
            ["Sunny", "Partly cloudy", "Cloudy", "Light rain", "Rain"],
            p=[0.25, 0.3, 0.25, 0.12, 0.08] if wet else [0.4, 0.3, 0.2, 0.07, 0.03],
        )
    )
    humidity = float(np.clip(rng.normal(68 if wet else 58, 12), 25, 100))
    wind = float(abs(rng.normal(3.0, 1.8)))
    return {
        "activity_id": aid,
        "issued_at": start_utc,
        "temperature_c": temp,
        "apparent_temperature_c": round(
            temp - 0.7 * wind + (0.05 * (humidity - 50) if temp > 20 else 0), 1
        ),
        "dew_point_c": round(temp - (100 - humidity) / 5, 1),
        "humidity_pct": round(humidity),
        "wind_speed_mps": round(wind, 1),
        "wind_gust_mps": round(wind * float(rng.uniform(1.3, 1.9)), 1),
        "wind_direction_deg": float(rng.integers(0, 360)),
        "condition": condition,
    }


def _write_core(
    session: Session,
    act_rows: list[dict[str, Any]],
    lap_rows: list[dict[str, Any]],
    weather_rows: list[dict[str, Any]],
    gear_rows: list[dict[str, Any]],
    report: SeedReport,
) -> None:
    session.execute(
        insert(m.Device),
        [
            {
                "device_id": DEVICE_ID,
                "product_name": "Demo Watch 9",
                "display_name": "Demo Watch",
                "software_version": "21.18",
                "is_primary": True,
                "last_used_at": act_rows[-1]["start_time_utc"] if act_rows else None,
            }
        ],
    )
    gear_dist: dict[str, float] = {}
    gear_count: dict[str, int] = {}
    first_use: dict[str, date] = {}
    last_use: dict[str, date] = {}
    by_id = {r["activity_id"]: r for r in act_rows}
    for g in gear_rows:
        a = by_id[g["activity_id"]]
        gear_dist[g["gear_uuid"]] = gear_dist.get(g["gear_uuid"], 0.0) + (a["distance_m"] or 0)
        gear_count[g["gear_uuid"]] = gear_count.get(g["gear_uuid"], 0) + 1
        d = a["start_time_utc"].date()
        first_use.setdefault(g["gear_uuid"], d)
        last_use[g["gear_uuid"]] = d
    session.execute(
        insert(m.Gear),
        [
            {
                "uuid": uuid,
                "gear_type": gtype,
                "display_name": name,
                "make": "Demo",
                "model": name,
                "status": status,
                "date_begin": first_use.get(uuid),
                "date_end": last_use.get(uuid) if status == "retired" else None,
                "max_distance_m": max_d,
                "total_distance_m": round(gear_dist.get(uuid, 0.0), 1),
                "total_activities": gear_count.get(uuid, 0),
            }
            for uuid, gtype, name, status, max_d in GEAR
        ],
    )
    report.rows["activity"] = len(act_rows)
    for table, rows in (
        (m.ActivityLap, lap_rows),
        (m.ActivityWeather, weather_rows),
        (m.ActivityGear, gear_rows),
    ):
        if rows:
            session.execute(insert(table), rows)
        report.rows[table.__tablename__] = len(rows)


def _timeline(
    start: date,
    end: date,
    nights: list[phys.Night],
    views: list[phys.ActivityMinutes],
    states: list[_DayState],
    tz: ZoneInfo,
    rng: np.random.Generator,
) -> phys.Timeline:
    t0 = phys.local_dt(start, 0, tz).astimezone(UTC)
    t1 = phys.local_dt(end + timedelta(days=1), 0, tz).astimezone(UTC)
    minutes = int((t1 - t0).total_seconds() // 60)
    return phys.build_timeline(
        t0,
        minutes,
        nights,
        views,
        daily_rhr={s.day: s.rhr for s in states},
        daily_hrv={s.day: s.hrv for s in states},
        tz=tz,
        rng=rng,
        bb_start=65.0,
    )


def _write_intraday(session: Session, tl: phys.Timeline, report: SeedReport) -> None:
    n = len(tl.hr)
    ts = [tl.t0 + timedelta(minutes=i) for i in range(n)]
    hr, st, bb = tl.hr.tolist(), tl.stress.tolist(), tl.body_battery.tolist()
    resp, spo2, steps = tl.resp.tolist(), tl.spo2.tolist(), tl.steps.tolist()
    asleep, in_act = tl.asleep.tolist(), tl.in_activity.tolist()
    report.rows["hr_sample"] = copy_rows(
        session, m.HrSample, ("ts", "bpm"), ((ts[i], int(hr[i])) for i in range(0, n, 2))
    )
    report.rows["stress_sample"] = copy_rows(
        session,
        m.StressSample,
        ("ts", "level"),
        ((ts[i], int(st[i])) for i in range(0, n, 3)),
    )
    report.rows["body_battery_sample"] = copy_rows(
        session,
        m.BodyBatterySample,
        ("ts", "level"),
        ((ts[i], int(bb[i])) for i in range(0, n, 3)),
    )
    report.rows["respiration_sample"] = copy_rows(
        session,
        m.RespirationSample,
        ("ts", "breaths_per_min"),
        ((ts[i], round(resp[i], 1)) for i in range(0, n, 2)),
    )
    report.rows["spo2_sample"] = copy_rows(
        session,
        m.Spo2Sample,
        ("ts", "spo2_pct"),
        ((ts[i], spo2[i]) for i in range(n) if asleep[i] and not math.isnan(spo2[i])),
    )

    def level(a: int) -> str:
        window = range(a, min(a + 15, n))
        if sum(asleep[i] for i in window) > 7:
            return "sleeping"
        if any(in_act[i] for i in window):
            return "highlyActive"
        total = sum(steps[i] for i in window)
        return "highlyActive" if total > 1200 else ("active" if total > 150 else "sedentary")

    report.rows["steps_interval"] = copy_rows(
        session,
        m.StepsInterval,
        ("start_utc", "end_utc", "steps", "activity_level"),
        (
            (ts[a], ts[a] + timedelta(minutes=15), int(sum(steps[a : a + 15])), level(a))
            for a in range(0, n - 14, 15)
        ),
    )


def _write_profile(
    session: Session,
    states: list[_DayState],
    act_rows: list[dict[str, Any]],
    best_runs: dict[float, tuple[float, int, datetime]],
    rng: np.random.Generator,
    report: SeedReport,
) -> None:
    last = states[-1]
    session.execute(
        insert(m.Athlete),
        [
            {
                "id": 1,
                "profile_id": 1,
                "display_name": "Demo Athlete",
                "full_name": "Demo Athlete",
                "gender": "MALE",
                "birth_date": date(last.day.year - int(AGE), 6, 15),
                "height_cm": HEIGHT_CM,
                "weight_kg": round(last.weight, 1),
                "max_hr": int(HR_MAX),
                "resting_hr": round(last.rhr),
                "lactate_threshold_hr": int(LTHR),
                "lactate_threshold_speed_mps": None,
                "ftp_w": round(3.4 * last.weight * last.vo2max / 52),
                "vo2max_running": round(last.vo2max, 1),
                "vo2max_cycling": round(last.vo2max - 2.5, 1),
                "unit_system": "metric",
                "time_zone": TZ_NAME,
                "hr_zones": HR_ZONE_FLOORS,
                "power_zones": None,
                "is_demo": True,
            }
        ],
    )
    names = {
        400.0: "run_400m",
        1000.0: "run_1k",
        1609.344: "run_mile",
        5000.0: "run_5k",
        10000.0: "run_10k",
        21097.5: "run_half_marathon",
        42195.0: "run_marathon",
    }
    prs: list[dict[str, Any]] = []
    for i, (dist, key) in enumerate(names.items(), start=1):
        if dist in best_runs:
            secs, aid, when = best_runs[dist]
            prs.append(
                {
                    "record_id": i,
                    "type_id": i,
                    "type_key": key,
                    "value": round(secs, 1),
                    "activity_id": aid,
                    "achieved_at": when,
                }
            )
    for j, group in enumerate(("run", "ride"), start=20):
        cands = [r for r in act_rows if r["sport_group"] == group and r["distance_m"]]
        if cands:
            best = max(cands, key=lambda r: r["distance_m"])
            prs.append(
                {
                    "record_id": j,
                    "type_id": j,
                    "type_key": f"longest_{group}",
                    "value": best["distance_m"],
                    "activity_id": best["activity_id"],
                    "achieved_at": best["start_time_utc"],
                }
            )
    if prs:
        session.execute(insert(m.PersonalRecord), prs)
    badges = [
        ("Half Marathon Finisher", "race", 2),
        ("Marathon Finisher", "race", 8),
        ("10K Finisher", "race", 2),
        ("Early Bird", "habit", 1),
        ("Summit Seeker", "hike", 4),
        ("Streak Starter", "habit", 1),
        ("Century Club", "ride", 4),
    ]
    session.execute(
        insert(m.Badge),
        [
            {
                "badge_id": 100 + k,
                "name": name,
                "category": cat,
                "points": pts,
                "earned_at": datetime.combine(
                    states[int(rng.integers(min(30, len(states) - 1), len(states)))].day,
                    datetime.min.time(),
                    UTC,
                ),
                "earned_count": 1,
            }
            for k, (name, cat, pts) in enumerate(badges)
        ],
    )
    session.execute(
        insert(m.Goal),
        [
            {
                "goal_id": 1,
                "goal_type": "weekly_running_distance_m",
                "target_value": 40_000.0,
                "start_day": states[0].day,
                "end_day": None,
                "status": "active",
            }
        ],
    )
    report.rows.update({"personal_record": len(prs), "badge": len(badges), "athlete": 1})
