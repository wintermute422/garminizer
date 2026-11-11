"""Apply the analytics to stored data: per-activity derived tables and the daily load series.

Idempotent: re-running replaces an activity's derived rows. Activities are (re)processed when
their `analytics_version` is older than ANALYTICS_VERSION, or when forced.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import numpy as np
from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session

from garminizer import models as m
from garminizer.analytics import FloatArray, curves, geo, load, physio, series
from garminizer.sports import DISTANCE_GROUPS

ANALYTICS_VERSION = 1
TILE_ZOOM = 14
TRACK_MAX_POINTS = 600
_SAMPLE_COLS = (
    "t_s",
    "hr",
    "speed_mps",
    "distance_m",
    "altitude_m",
    "power_w",
    "lat",
    "lon",
    "cadence",
)


@dataclass(frozen=True)
class AthleteParams:
    hr_rest: float
    hr_max: float
    hr_floors: tuple[float, ...]
    ftp_w: float | None
    sex: str

    @classmethod
    def from_db(cls, session: Session) -> AthleteParams:
        a = session.scalar(select(m.Athlete))
        observed_max = session.scalar(select(func.max(m.Activity.max_hr)))
        median_rhr = session.scalar(
            select(func.percentile_cont(0.5).within_group(m.DailySummary.resting_hr))
        )
        hr_max = float((a.max_hr if a and a.max_hr else None) or observed_max or 190)
        hr_rest = float((a.resting_hr if a and a.resting_hr else None) or median_rhr or 60)
        floors: tuple[float, ...]
        if a and a.hr_zones and len(a.hr_zones) >= 5:
            floors = tuple(float(x) for x in a.hr_zones[:5])
        else:
            floors = tuple(round(hr_max * p) for p in (0.5, 0.6, 0.7, 0.8, 0.9))
        sex = "female" if a and (a.gender or "").upper().startswith("F") else "male"
        return cls(
            hr_rest=hr_rest,
            hr_max=max(hr_max, hr_rest + 20),
            hr_floors=floors,
            ftp_w=float(a.ftp_w) if a and a.ftp_w else None,
            sex=sex,
        )


@dataclass
class PipelineReport:
    activities: int = 0
    daily_rows: int = 0
    rows: dict[str, int] = field(default_factory=dict)

    def add(self, table: str, n: int) -> None:
        self.rows[table] = self.rows.get(table, 0) + n


def _samples(session: Session, activity_id: int) -> dict[str, FloatArray]:
    cols = [getattr(m.ActivitySample, c) for c in _SAMPLE_COLS]
    rows = session.execute(
        select(*cols)
        .where(m.ActivitySample.activity_id == activity_id)
        .order_by(m.ActivitySample.t_s)
    ).all()
    if not rows:
        return {}
    arr = np.array([[np.nan if v is None else v for v in r] for r in rows], dtype=np.float64)
    return {name: arr[:, i] for i, name in enumerate(_SAMPLE_COLS)}


def _has(a: FloatArray, min_count: int = 10) -> bool:
    return int(np.isfinite(a).sum()) >= min_count


def _dt(t: FloatArray) -> FloatArray:
    """Seconds each sample represents (time to the next sample, capped for pauses)."""
    if len(t) < 2:
        return np.ones_like(t)
    d = np.diff(t, append=t[-1] + 1)
    return np.clip(np.nan_to_num(d, nan=1.0), 0, 10)


def _best_efforts(aid: int, s: dict[str, FloatArray], group: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    metrics: list[tuple[str, FloatArray]] = []
    if _has(s["hr"]):
        metrics.append(("hr", s["hr"]))
    if group in DISTANCE_GROUPS and _has(s["speed_mps"]):
        metrics.append(("speed", s["speed_mps"]))
    if _has(s["power_w"]) and np.nanmax(s["power_w"]) > 0:
        metrics.append(("power", s["power_w"]))
    for name, values in metrics:
        resampled = curves.resample_1hz(s["t_s"], values)
        for duration, value in curves.mean_max(resampled).items():
            if math.isfinite(value):
                out.append(
                    {"activity_id": aid, "metric": name, "duration_s": duration, "value": value}
                )
    return out


def _track(lat: FloatArray, lon: FloatArray) -> dict[str, Any] | None:
    ok = np.isfinite(lat) & np.isfinite(lon)
    if ok.sum() < 2:
        return None
    la, lo = lat[ok], lon[ok]
    eps = 5.0
    idx = geo.simplify_track(la, lo, eps)
    while len(idx) > TRACK_MAX_POINTS:
        eps *= 1.6
        idx = geo.simplify_track(la, lo, eps)
    points = [[round(float(la[i]), 5), round(float(lo[i]), 5)] for i in idx]
    return {
        "points": points,
        "min_lat": float(la.min()),
        "max_lat": float(la.max()),
        "min_lon": float(lo.min()),
        "max_lon": float(lo.max()),
    }


def _splits(aid: int, s: dict[str, FloatArray]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    extras = {"hr": s["hr"], "cadence": s["cadence"], "power": s["power_w"]}
    for unit, length in (("km", 1000.0), ("mi", 1609.344)):
        for sp in series.even_splits(s["t_s"], s["distance_m"], length, extras, s["altitude_m"]):
            out.append(
                {
                    "activity_id": aid,
                    "unit": unit,
                    "split_index": sp.index,
                    "distance_m": sp.distance_m,
                    "duration_s": sp.duration_s,
                    "avg_hr": sp.averages.get("hr"),
                    "avg_cadence": sp.averages.get("cadence"),
                    "avg_power_w": sp.averages.get("power"),
                    "elevation_gain_m": sp.elevation_gain_m,
                    "elevation_loss_m": sp.elevation_loss_m,
                }
            )
    return out


def _zones(
    session: Session, aid: int, s: dict[str, FloatArray], p: AthleteParams, group: str
) -> list[dict[str, Any]]:
    existing = set(
        session.scalars(select(m.ActivityZone.kind).where(m.ActivityZone.activity_id == aid))
    )
    rows: list[dict[str, Any]] = []
    dt = _dt(s["t_s"])
    if "hr" not in existing and _has(s["hr"]):
        secs = physio.hr_zone_seconds(s["hr"], dt, p.hr_floors)
        secs[1] += secs[0]  # time below zone 1 counts as zone 1 (Garmin shows 5 zones)
        for zone, (sec, low) in enumerate(zip(secs[1:], p.hr_floors, strict=True), start=1):
            rows.append(
                {"activity_id": aid, "kind": "hr", "zone": zone, "seconds": sec, "low_value": low}
            )
    if "power" not in existing and p.ftp_w and group == "ride" and _has(s["power_w"]):
        floors = [p.ftp_w * f for f in (0.0001, 0.55, 0.75, 0.90, 1.05, 1.20, 1.50)]
        secs = physio.hr_zone_seconds(s["power_w"], dt, floors)
        for zone, (sec, low) in enumerate(zip(secs[1:], floors, strict=True), start=1):
            rows.append(
                {
                    "activity_id": aid,
                    "kind": "power",
                    "zone": zone,
                    "seconds": sec,
                    "low_value": round(low),
                }
            )
    return rows


def process_activity(
    session: Session, activity: m.Activity, p: AthleteParams, report: PipelineReport
) -> None:
    aid = activity.activity_id
    s = _samples(session, aid)
    for table in (
        m.ActivityBestEffort,
        m.ActivityBestDistance,
        m.ActivityTrack,
        m.ActivityTile,
        m.ActivitySplit,
    ):
        session.execute(delete(table).where(table.activity_id == aid))
    values: dict[str, Any] = {"analytics_version": ANALYTICS_VERSION}
    group = activity.sport_group
    if s:
        rows: dict[type[Any], list[dict[str, Any]]] = {
            m.ActivityBestEffort: _best_efforts(aid, s, group),
            m.ActivityZone: _zones(session, aid, s, p, group),
        }
        if _has(s["hr"]):
            values["trimp"] = round(
                physio.trimp_banister(s["hr"], _dt(s["t_s"]), p.hr_rest, p.hr_max, p.sex), 1
            )
        if group in DISTANCE_GROUPS and _has(s["distance_m"]) and np.nanmax(s["distance_m"]) > 500:
            rows[m.ActivitySplit] = _splits(aid, s)
        if group == "run" and _has(s["distance_m"]):
            rows[m.ActivityBestDistance] = [
                {"activity_id": aid, "distance_m": d, "seconds": secs}
                for d, secs in curves.best_distance_times(s["t_s"], s["distance_m"]).items()
            ]
        track = _track(s["lat"], s["lon"])
        if track:
            rows[m.ActivityTrack] = [{"activity_id": aid, **track}]
            tiles = geo.tiles_for_track(s["lat"], s["lon"], TILE_ZOOM)
            rows[m.ActivityTile] = [
                {"activity_id": aid, "zoom": TILE_ZOOM, "x": x, "y": y} for x, y in sorted(tiles)
            ]
        output = s["power_w"] if group == "ride" else s["speed_mps"] * 60
        if group in {"run", "ride"} and _has(s["hr"]) and _has(output):
            ef = physio.efficiency_factor(output, s["hr"])
            dec = physio.aerobic_decoupling(output, s["hr"])
            values["efficiency_factor"] = round(ef, 3) if ef is not None else None
            values["aerobic_decoupling_pct"] = round(dec, 2) if dec is not None else None
        for table, table_rows in rows.items():
            if table_rows:
                session.execute(insert(table), table_rows)
                report.add(table.__tablename__, len(table_rows))
    session.execute(update(m.Activity).where(m.Activity.activity_id == aid).values(**values))
    report.activities += 1


def refresh_daily_load(session: Session, p: AthleteParams, today: date) -> int:
    """Rebuild daily_load from the first activity day to today (rest days count as 0)."""
    rows = session.execute(
        select(
            func.date(m.Activity.start_time_local),
            func.coalesce(func.sum(func.coalesce(m.Activity.training_load, m.Activity.trimp)), 0),
            func.coalesce(func.sum(m.Activity.trimp), 0),
            func.count(),
        ).group_by(func.date(m.Activity.start_time_local))
    ).all()
    session.execute(delete(m.DailyLoad))
    if not rows:
        return 0
    by_day = {r[0]: (float(r[1]), float(r[2]), int(r[3])) for r in rows}
    first = min(by_day)
    last = max([*by_day, today])
    days = [first + timedelta(days=i) for i in range((last - first).days + 1)]
    loads = np.array([by_day.get(d, (0.0, 0.0, 0))[0] for d in days])
    ctl, atl, tsb = load.pmc(loads)
    ratio = load.acwr(loads)
    mono, strain = load.monotony_strain(loads)

    def fin(v: float) -> float | None:
        return None if not math.isfinite(v) else round(v, 3)

    session.execute(
        insert(m.DailyLoad),
        [
            {
                "day": d,
                "load": round(float(loads[i]), 1),
                "trimp": round(by_day.get(d, (0.0, 0.0, 0))[1], 1),
                "activities": by_day.get(d, (0.0, 0.0, 0))[2],
                "ctl": round(float(ctl[i]), 2),
                "atl": round(float(atl[i]), 2),
                "tsb": round(float(tsb[i]), 2),
                "acwr": fin(float(ratio[i])),
                "monotony": fin(float(mono[i])),
                "strain": fin(float(strain[i])),
            }
            for i, d in enumerate(days)
        ],
    )
    return len(days)


def run(
    session: Session,
    *,
    activity_ids: Sequence[int] | None = None,
    force: bool = False,
    today: date,
) -> PipelineReport:
    """Process pending (or the given / all, when forced) activities, then rebuild daily load.

    ``today`` (the athlete's, see garminizer.athlete) is the last day of the load series.
    """
    p = AthleteParams.from_db(session)
    report = PipelineReport()
    query = select(m.Activity).order_by(m.Activity.start_time_utc)
    if activity_ids is not None:
        query = query.where(m.Activity.activity_id.in_(list(activity_ids)))
    elif not force:
        query = query.where(m.Activity.analytics_version < ANALYTICS_VERSION)
    for activity in _iter(session, query):
        process_activity(session, activity, p, report)
    report.daily_rows = refresh_daily_load(session, p, today)
    return report


def _iter(session: Session, query: Any) -> Iterable[m.Activity]:
    return list(session.scalars(query))
