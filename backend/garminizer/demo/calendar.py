"""A periodised training calendar for the demo athlete.

Four-week blocks (3 build + 1 recovery) with a slow overall progression, three goal races with
taper and recovery, two short illnesses, a summer hiking vacation and seasonal sport choices.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

import numpy as np

# kind -> (Garmin typeKey, default name)
KINDS: dict[str, tuple[str, str]] = {
    "easy": ("running", "Easy Run"),
    "recovery": ("running", "Recovery Run"),
    "long": ("running", "Long Run"),
    "tempo": ("running", "Tempo Run"),
    "intervals": ("track_running", "Intervals 6x800 m"),
    "hills": ("trail_running", "Hill Repeats"),
    "trail": ("trail_running", "Trail Run"),
    "race": ("running", "Race"),
    "endurance_ride": ("road_biking", "Endurance Ride"),
    "gravel": ("gravel_cycling", "Gravel Ride"),
    "indoor_ride": ("indoor_cycling", "Indoor Cycling Intervals"),
    "swim": ("lap_swimming", "Pool Swim"),
    "strength": ("strength_training", "Strength"),
    "hike": ("hiking", "Mountain Hike"),
    "walk": ("walking", "Walk"),
    "xc_ski": ("cross_country_skiing_ws", "Cross-Country Ski"),
}

RACES: tuple[tuple[int, str, float], ...] = (
    (150, "City 10K", 10_000.0),
    (300, "Spring Half Marathon", 21_097.5),
    (660, "Autumn Marathon", 42_195.0),
)


@dataclass(frozen=True)
class Workout:
    day: date
    kind: str
    duration_min: float
    start_hour: float
    race_distance_m: float | None = None
    race_name: str | None = None

    @property
    def sport_type(self) -> str:
        return KINDS[self.kind][0]

    @property
    def name(self) -> str:
        if self.race_name:
            return self.race_name
        base = KINDS[self.kind][1]
        if self.kind in {"easy", "recovery", "walk"}:
            part = (
                "Morning"
                if self.start_hour < 11
                else ("Lunch" if self.start_hour < 14 else "Evening")
            )
            return f"{part} {base.split()[-1]}" if self.kind == "walk" else f"{part} {base}"
        return base


@dataclass
class Calendar:
    start: date
    days: int
    workouts: list[Workout] = field(default_factory=list)
    sick_days: set[date] = field(default_factory=set)
    vacation_days: set[date] = field(default_factory=set)
    race_days: dict[date, tuple[str, float]] = field(default_factory=dict)

    def on(self, day: date) -> list[Workout]:
        return [w for w in self.workouts if w.day == day]


def _next_sunday(d: date) -> date:
    return d + timedelta(days=(6 - d.weekday()) % 7)


def _season(d: date) -> str:
    if d.month in (12, 1, 2):
        return "winter"
    if d.month in (6, 7, 8, 9):
        return "summer"
    return "shoulder"


def build_calendar(start: date, days: int, rng: np.random.Generator) -> Calendar:
    cal = Calendar(start=start, days=days)
    end = start + timedelta(days=days - 1)

    for offset, name, dist in RACES:
        race_day = _next_sunday(start + timedelta(days=offset))
        if race_day <= end:
            cal.race_days[race_day] = (name, dist)

    # Two short illnesses, away from races.
    for _ in range(2):
        for _attempt in range(50):
            s = start + timedelta(days=int(rng.integers(20, max(days - 10, 21))))
            if all(abs((s - r).days) > 30 for r in cal.race_days):
                cal.sick_days.update(s + timedelta(days=i) for i in range(int(rng.integers(5, 8))))
                break

    # A hiking vacation starting on the first Saturday of August each year.
    for year in range(start.year, end.year + 1):
        first = date(year, 8, 1)
        sat = first + timedelta(days=(5 - first.weekday()) % 7)
        cal.vacation_days.update(sat + timedelta(days=i) for i in range(9))

    for i in range(days):
        day = start + timedelta(days=i)
        cal.workouts.extend(_plan_day(cal, day, i, rng))
    return cal


def _volume_factor(cal: Calendar, day: date, i: int) -> float:
    progression = 0.72 + 0.48 * (i / max(cal.days - 1, 1))
    week = i // 7
    block = (0.88, 0.96, 1.06, 0.66)[week % 4]
    factor = progression * block
    for race_day in cal.race_days:
        delta = (race_day - day).days
        if 0 < delta <= 7:
            factor *= 0.5
        elif 7 < delta <= 14:
            factor *= 0.7
        elif -10 <= delta < 0:
            factor *= 0.45
    return factor


@dataclass
class _Day:
    """Planning context for one day; `add` appends a workout with a little start-time jitter."""

    day: date
    vf: float
    season: str
    rng: np.random.Generator
    out: list[Workout] = field(default_factory=list)

    def add(self, kind: str, minutes: float, hour: float) -> None:
        jitter = float(self.rng.normal(0, 0.4))
        self.out.append(Workout(self.day, kind, max(float(minutes), 15.0), hour + jitter))

    def chance(self, p: float) -> bool:
        return bool(self.rng.random() < p)

    def u(self, low: float, high: float) -> float:
        return float(self.rng.uniform(low, high))


def _monday(c: _Day) -> None:
    if c.chance(0.6):
        c.add("strength", c.u(35, 50), 18.5)


def _tuesday(c: _Day) -> None:
    if c.season == "winter" and c.chance(0.35):
        c.add("indoor_ride", c.u(55, 70), 18.0)
    else:
        c.add("intervals", 58 * min(c.vf, 1.15) + c.u(-4, 6), 18.0)


def _wednesday(c: _Day) -> None:
    if c.chance(0.35):
        c.add("swim", c.u(40, 55), 7.0)
    else:
        c.add("easy", 48 * c.vf + c.u(-5, 8), 7.0)


def _thursday(c: _Day) -> None:
    if c.season == "summer" and c.chance(0.35):
        c.add("endurance_ride", c.u(70, 100), 18.0)
    elif c.chance(0.25):
        c.add("hills", 55 * min(c.vf, 1.1) + c.u(-5, 5), 18.0)
    else:
        c.add("tempo", 52 * min(c.vf, 1.15) + c.u(-4, 6), 18.0)


def _friday(c: _Day) -> None:
    r = c.u(0, 1)
    if r < 0.35:
        c.add("recovery", c.u(28, 36), 7.0)
    elif r < 0.55:
        c.add("strength", c.u(30, 45), 18.0)


def _saturday(c: _Day) -> None:
    if c.season == "winter" and c.chance(0.3):
        c.add("xc_ski", c.u(70, 130), 10.0)
    else:
        c.add("long", 95 * c.vf + c.u(-8, 12), 8.5)


def _sunday(c: _Day) -> None:
    r = c.u(0, 1)
    if c.season == "summer" and r < 0.55:
        kind = "gravel" if c.chance(0.4) else "endurance_ride"
        c.add(kind, 150 * c.vf + c.u(-20, 40), 9.0)
    elif c.season == "winter" and r < 0.35:
        c.add("xc_ski", c.u(60, 110), 10.5)
    elif r < 0.25:
        c.add("hike", c.u(150, 260), 9.0)
    elif r < 0.6:
        c.add("easy", 45 * c.vf + c.u(-5, 10), 9.5)
    elif r < 0.75:
        c.add("trail", 60 * c.vf + c.u(-5, 10), 9.0)


def _vacation(c: _Day) -> None:
    if c.chance(0.7):
        c.add("hike", c.u(190, 330), 8.5)
    elif c.chance(0.5):
        c.add("swim", c.u(35, 50), 17.0)
    else:
        c.add("trail", c.u(45, 70), 7.5)


_WEEKDAYS = (_monday, _tuesday, _wednesday, _thursday, _friday, _saturday, _sunday)


def _plan_day(cal: Calendar, day: date, i: int, rng: np.random.Generator) -> list[Workout]:
    if day in cal.race_days:
        name, dist = cal.race_days[day]
        return [Workout(day, "race", dist / 1000 * 4.6, 9.0, dist, name)]
    c = _Day(day, _volume_factor(cal, day, i), _season(day), rng)
    if day in cal.sick_days:
        if c.chance(0.3):
            c.add("walk", c.u(20, 35), c.u(11, 16))
        return c.out
    if day in cal.vacation_days:
        _vacation(c)
        return c.out
    life_happens = c.chance(0.08) and day.weekday() != 4
    if not life_happens:
        _WEEKDAYS[day.weekday()](c)
    if c.chance(0.45 if day.weekday() < 5 else 0.3):
        c.add("walk", c.u(25, 55), float(rng.choice([12.5, 17.5, 19.5])))
    return c.out
