"""All ORM models (importing this module registers every table on `Base.metadata`)."""

from garminizer.models.activity import (
    Activity,
    ActivityFile,
    ActivityLap,
    ActivitySample,
    ActivitySplit,
    ActivityWeather,
    ActivityZone,
)
from garminizer.models.analytics import (
    ActivityBestDistance,
    ActivityBestEffort,
    ActivityTile,
    ActivityTrack,
    DailyLoad,
)
from garminizer.models.body import Badge, BloodPressure, BodyComposition, Goal, PersonalRecord
from garminizer.models.core import ActivityGear, AppSetting, Athlete, Device, Gear, RawPayload
from garminizer.models.nutrition import Meal, MealItem
from garminizer.models.performance import (
    EnduranceScore,
    HillScore,
    MaxMetric,
    RacePrediction,
    TrainingReadiness,
    TrainingStatus,
)
from garminizer.models.sync import SyncCursor, SyncError, SyncRun
from garminizer.models.wellness import (
    BodyBatterySample,
    DailySummary,
    HrSample,
    HrvDaily,
    RespirationSample,
    Sleep,
    SleepStage,
    Spo2Sample,
    StepsInterval,
    StressSample,
)

__all__ = [
    "Activity",
    "ActivityBestDistance",
    "ActivityBestEffort",
    "ActivityFile",
    "ActivityGear",
    "ActivityLap",
    "ActivitySample",
    "ActivitySplit",
    "ActivityTile",
    "ActivityTrack",
    "ActivityWeather",
    "ActivityZone",
    "AppSetting",
    "Athlete",
    "Badge",
    "BloodPressure",
    "BodyBatterySample",
    "BodyComposition",
    "DailyLoad",
    "DailySummary",
    "Device",
    "EnduranceScore",
    "Gear",
    "Goal",
    "HillScore",
    "HrSample",
    "HrvDaily",
    "MaxMetric",
    "Meal",
    "MealItem",
    "PersonalRecord",
    "RacePrediction",
    "RawPayload",
    "RespirationSample",
    "Sleep",
    "SleepStage",
    "Spo2Sample",
    "StepsInterval",
    "StressSample",
    "SyncCursor",
    "SyncError",
    "SyncRun",
    "TrainingReadiness",
    "TrainingStatus",
]
