"""Sport classification shared by the sync parsers, the demo generator and the API."""

from __future__ import annotations

SPORT_GROUPS = (
    "run",
    "ride",
    "swim",
    "walk",
    "hike",
    "strength",
    "cardio",
    "winter",
    "water",
    "other",
)

_EXACT: dict[str, str] = {
    "running": "run",
    "trail_running": "run",
    "track_running": "run",
    "treadmill_running": "run",
    "indoor_running": "run",
    "street_running": "run",
    "ultra_run": "run",
    "virtual_run": "run",
    "obstacle_run": "run",
    "cycling": "ride",
    "road_biking": "ride",
    "gravel_cycling": "ride",
    "mountain_biking": "ride",
    "indoor_cycling": "ride",
    "virtual_ride": "ride",
    "e_bike_fitness": "ride",
    "e_bike_mountain": "ride",
    "cyclocross": "ride",
    "track_cycling": "ride",
    "lap_swimming": "swim",
    "open_water_swimming": "swim",
    "walking": "walk",
    "casual_walking": "walk",
    "speed_walking": "walk",
    "indoor_walking": "walk",
    "hiking": "hike",
    "mountaineering": "hike",
    "strength_training": "strength",
    "indoor_cardio": "cardio",
    "hiit": "cardio",
    "yoga": "cardio",
    "pilates": "cardio",
    "elliptical": "cardio",
    "stair_climbing": "cardio",
    "indoor_rowing": "cardio",
    "breathwork": "other",
    "cross_country_skiing_ws": "winter",
    "skate_skiing_ws": "winter",
    "resort_skiing_snowboarding_ws": "winter",
    "backcountry_skiing_snowboarding_ws": "winter",
    "snow_shoe_ws": "winter",
    "rowing": "water",
    "stand_up_paddleboarding": "water",
    "kayaking": "water",
    "surfing": "water",
}

_FRAGMENTS: tuple[tuple[str, str], ...] = (
    ("swim", "swim"),
    ("run", "run"),
    ("cycl", "ride"),
    ("bik", "ride"),
    ("ride", "ride"),
    ("walk", "walk"),
    ("hik", "hike"),
    ("strength", "strength"),
    ("ski", "winter"),
    ("snow", "winter"),
    ("paddl", "water"),
    ("row", "water"),
    ("kayak", "water"),
    ("cardio", "cardio"),
    ("fitness", "cardio"),
)


def sport_group(type_key: str | None) -> str:
    """Map a Garmin activity typeKey to one of SPORT_GROUPS."""
    if not type_key:
        return "other"
    key = type_key.lower()
    if key in _EXACT:
        return _EXACT[key]
    for fragment, group in _FRAGMENTS:
        if fragment in key:
            return group
    return "other"


# Sport groups whose activities cover a distance (pace/speed, distance curves).
DISTANCE_GROUPS = frozenset({"run", "ride", "swim", "walk", "hike", "winter", "water"})
# On foot: cadence is steps per minute, steps are counted.
FOOT_GROUPS = frozenset({"run", "walk", "hike"})
