"""Test double for `garminconnect.Garmin`, built from the synthetic fixtures. Never networked.

* Daily/range methods return the fixture shifted from its base day (2024-05-01) to the
  requested day/month (every date string and epoch-ms value inside is moved).
* The activity list is generated: `n_activities` copies of the fixture run/ride/strength,
  one per day going back from `last_activity_day`.
* Failures are injected per call: `fail_with[method]` holds exceptions raised in order;
  `crash_after` raises Crash (a BaseException, like a killed process) after N calls.
* Auth: `login()` / `resume_login()` / `client.dump()` mimic the 0.3.20 flow.
"""

from __future__ import annotations

import copy
import io
import json
import re
import struct
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectAuthenticationError

FIXTURES = Path(__file__).parent / "fixtures" / "garmin"
BASE_DAY = date(2024, 5, 1)
BASE_MS = 1714521600000
DAY_MS = 86_400_000
MFA_CODE = "123456"
# assembled at runtime so the tracked file holds no e-mail/password-looking literals
FAKE_EMAIL = "@".join(("athlete", "example.com"))
FAKE_PASSWORD = "-".join(("correct", "horse", "battery"))
_DATE_PREFIX = re.compile(r"^(\d{4}-\d{2}-\d{2})")


class Crash(BaseException):
    """Raised by the fake to simulate the process dying mid-run."""


def load(name: str) -> Any:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def shift(obj: Any, days: int) -> Any:
    """Move every date string / epoch-ms value in a payload by `days` days."""
    if days == 0:
        return copy.deepcopy(obj)
    if isinstance(obj, dict):
        return {shift(k, days) if isinstance(k, str) else k: shift(v, days) for k, v in obj.items()}
    if isinstance(obj, list):
        return [shift(v, days) for v in obj]
    if isinstance(obj, str):
        match = _DATE_PREFIX.match(obj)
        if match:
            try:
                d = date.fromisoformat(match.group(1))
            except ValueError:
                return obj
            return (d + timedelta(days=days)).isoformat() + obj[10:]
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        if abs(obj - BASE_MS) < 400 * DAY_MS:
            return obj + days * DAY_MS
        return obj
    return obj


# --- a minimal FIT encoder (file_id + record messages) --------------------------------------

_CRC_TABLE = (
    0x0000,
    0xCC01,
    0xD801,
    0x1400,
    0xF001,
    0x3C00,
    0x2800,
    0xE401,
    0xA001,
    0x6C00,
    0x7800,
    0xB401,
    0x5000,
    0x9C01,
    0x8801,
    0x4400,
)
FIT_EPOCH = datetime(1989, 12, 31, tzinfo=UTC)
# (field number, size, base type, struct format, scale, offset) of the record message
_RECORD_FIELDS = {
    "timestamp": (253, 4, 0x86, "I", 1, 0),
    "position_lat": (0, 4, 0x85, "i", 1, 0),
    "position_long": (1, 4, 0x85, "i", 1, 0),
    "distance": (5, 4, 0x86, "I", 100, 0),
    "heart_rate": (3, 1, 0x02, "B", 1, 0),
    "cadence": (4, 1, 0x02, "B", 1, 0),
    "power": (7, 2, 0x84, "H", 1, 0),
    "enhanced_speed": (73, 4, 0x86, "I", 1000, 0),
    "enhanced_altitude": (78, 4, 0x86, "I", 5, 500),
}


def _crc(data: bytes) -> int:
    crc = 0
    for byte in data:
        for nibble in (byte & 0xF, (byte >> 4) & 0xF):
            tmp = _CRC_TABLE[crc & 0xF]
            crc = (crc >> 4) & 0x0FFF
            crc = crc ^ tmp ^ _CRC_TABLE[nibble]
    return crc


def make_fit(points: list[dict[str, Any]]) -> bytes:
    """A valid FIT activity file with one record per point (values in SI units/degrees)."""
    body = bytearray()
    # file_id definition (local 0, global 0): type (enum) = 4 (activity)
    body += struct.pack("<BBBHB", 0x40, 0, 0, 0, 1) + bytes([0, 1, 0x00])
    body += struct.pack("<BB", 0x00, 4)
    names = list(_RECORD_FIELDS)
    body += struct.pack("<BBBHB", 0x41, 0, 0, 20, len(names))
    for name in names:
        num, size, base, *_ = _RECORD_FIELDS[name]
        body += bytes([num, size, base])
    for p in points:
        body += bytes([0x01])
        for name in names:
            _, _, _, fmt, scale, offset = _RECORD_FIELDS[name]
            value = p[name]
            if name == "timestamp":
                raw = int((value - FIT_EPOCH).total_seconds())
            elif name.startswith("position"):
                raw = round(value / 180.0 * 2**31)
            else:
                raw = round((value + offset) * scale)
            body += struct.pack("<" + fmt, raw)
    header = struct.pack("<BBHI4s", 14, 0x20, 2132, len(body), b".FIT")
    header += struct.pack("<H", _crc(header))
    data = header + bytes(body)
    return data + struct.pack("<H", _crc(data))


def fit_points(start: datetime, n: int = 120) -> list[dict[str, Any]]:
    """n seconds of a steady synthetic run near 45.0/7.0 (3.3 m/s, 86 strides/min)."""
    return [
        {
            "timestamp": start + timedelta(seconds=i),
            "position_lat": 45.0 + i * 0.00003,
            "position_long": 7.0 + i * 0.00002,
            "distance": round(3.3 * i, 2),
            "heart_rate": 140 + i % 10,
            "cadence": 86,
            "power": 280,
            "enhanced_speed": 3.3,
            "enhanced_altitude": 230.0 + (i % 20) * 0.2,
        }
        for i in range(n)
    ]


def zip_of(name: str, content: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(name, content)
    return buf.getvalue()


# --- the fake -----------------------------------------------------------------------------


class _FakeTokenClient:
    def __init__(self) -> None:
        self.tokens: dict[str, str] | None = None

    def dump(self, path: str) -> None:
        target = Path(path)
        target.mkdir(parents=True, exist_ok=True)
        (target / "garmin_tokens.json").write_text(
            json.dumps(self.tokens or {}), encoding="utf-8", newline="\n"
        )


class FakeGarmin:
    display_name: str | None = "demo-athlete"
    full_name: str | None = "Demo Athlete"
    profile_id: int | None = 1234567890

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        return_on_mfa: bool = False,
        retry_attempts: int = 3,
        n_activities: int = 3,
        last_activity_day: date = BASE_DAY,
        first_day: date | None = None,
        mfa_required: bool = False,
        with_fit: bool = True,
        **_: Any,
    ) -> None:
        self.username = email
        self.password = password
        self.return_on_mfa = return_on_mfa
        self.retry_attempts = retry_attempts
        self.mfa_required = mfa_required
        self.client = _FakeTokenClient()
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fail_with: dict[str, list[BaseException]] = {}
        self.crash_after: int | None = None
        self.with_fit = with_fit
        self.first_day = first_day or (last_activity_day - timedelta(days=n_activities + 1))
        self.activities = self._make_activities(n_activities, last_activity_day)

    # -- plumbing
    def _hit(self, name: str, *args: Any) -> None:
        self.calls.append((name, args))
        if self.crash_after is not None and len(self.calls) > self.crash_after:
            raise Crash(name)
        queue = self.fail_with.get(name)
        if queue:
            raise queue.pop(0)

    def _make_activities(self, n: int, last: date) -> list[dict[str, Any]]:
        templates = load("get_activities")
        out = []
        for i in range(n):
            t = templates[i % len(templates)]
            base_day = date.fromisoformat(t["startTimeLocal"][:10])
            item = shift(t, ((last - timedelta(days=i)) - base_day).days)
            item["activityId"] = 1234567890 + i
            out.append(item)
        return out

    def _activity(self, activity_id: str) -> dict[str, Any]:
        for a in self.activities:
            if str(a["activityId"]) == str(activity_id):
                return a
        raise KeyError(activity_id)

    def _daily(self, name: str, cdate: str) -> Any:
        day = date.fromisoformat(cdate)
        if day < self.first_day:
            return None
        return shift(load(name), (day - BASE_DAY).days)

    def _monthly(self, name: str, start: str) -> Any:
        month = date.fromisoformat(start).replace(day=1)
        return shift(load(name), (month - BASE_DAY.replace(day=1)).days)

    # -- auth (garminconnect 0.3.20 semantics)
    def login(self, tokenstore: str | None = None) -> tuple[str | None, Any]:
        if tokenstore:
            path = Path(tokenstore) / "garmin_tokens.json"
            if not path.is_file():
                raise GarminConnectAuthenticationError("Username and password are required")
            self.client.tokens = json.loads(path.read_text(encoding="utf-8"))
            return None, None
        if self.username != FAKE_EMAIL or self.password != FAKE_PASSWORD:
            raise GarminConnectAuthenticationError("Authentication failed")
        if self.mfa_required and self.return_on_mfa:
            return "needs_mfa", {"flow": "portal", "cookies": []}
        self.client.tokens = {"di_token": "fake-access", "di_refresh_token": "fake-refresh"}
        return None, None

    def resume_login(self, client_state: Any, mfa_code: str) -> tuple[Any, Any]:
        if mfa_code != MFA_CODE:
            raise GarminConnectAuthenticationError("MFA verification failed")
        self.client.tokens = {"di_token": "fake-access", "di_refresh_token": "fake-refresh"}
        return None, None

    # -- write methods (must never be reachable through GarminClient)
    def add_weigh_in(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("write method called")

    def delete_activity(self, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("write method called")

    # -- profile, devices, gear
    def get_user_profile(self) -> Any:
        self._hit("get_user_profile")
        return load("get_user_profile")

    def get_personal_information(self) -> Any:
        self._hit("get_personal_information")
        return load("get_personal_information")

    def get_user_profile_base(self) -> Any:
        self._hit("get_user_profile_base")
        base = load("get_user_profile_base")
        base["createDate"] = f"{self.first_day.isoformat()}T10:00:00.0"
        return base

    def get_heart_rate_zones(self) -> Any:
        self._hit("get_heart_rate_zones")
        return load("get_heart_rate_zones")

    def get_devices(self) -> Any:
        self._hit("get_devices")
        return load("get_devices")

    def get_device_last_used(self) -> Any:
        self._hit("get_device_last_used")
        return load("get_device_last_used")

    def get_gear(self, user_profile_number: str) -> Any:
        self._hit("get_gear", user_profile_number)
        return load("get_gear")

    def get_gear_stats(self, gear_uuid: str) -> Any:
        self._hit("get_gear_stats", gear_uuid)
        return {**load("get_gear_stats"), "uuid": gear_uuid}

    def get_personal_record(self) -> Any:
        self._hit("get_personal_record")
        return load("get_personal_record")

    def get_earned_badges(self) -> Any:
        self._hit("get_earned_badges")
        return load("get_earned_badges")

    def get_goals(self, status: str = "active", start: int = 1, limit: int = 30) -> Any:
        self._hit("get_goals", status)
        return load("get_goals") if status == "active" else []

    # -- activities
    def count_activities(self) -> int:
        self._hit("count_activities")
        return len(self.activities)

    def get_activities(self, start: int = 0, limit: int = 20) -> Any:
        self._hit("get_activities", start, limit)
        return copy.deepcopy(self.activities[start : start + limit])

    def get_activity(self, activity_id: str) -> Any:
        self._hit("get_activity", activity_id)
        a = self._activity(activity_id)
        detail = load("get_activity")
        detail["activityId"] = a["activityId"]
        detail["summaryDTO"]["distance"] = a.get("distance")
        detail["summaryDTO"]["duration"] = a.get("duration")
        return detail

    def get_activity_splits(self, activity_id: str) -> Any:
        self._hit("get_activity_splits", activity_id)
        return {**load("get_activity_splits"), "activityId": int(activity_id)}

    def get_activity_hr_in_timezones(self, activity_id: str) -> Any:
        self._hit("get_activity_hr_in_timezones", activity_id)
        return load("get_activity_hr_in_timezones")

    def get_activity_weather(self, activity_id: str) -> Any:
        self._hit("get_activity_weather", activity_id)
        return load("get_activity_weather")

    def get_activity_gear(self, activity_id: str) -> Any:
        self._hit("get_activity_gear", activity_id)
        return load("get_activity_gear")

    def download_activity(self, activity_id: str, dl_fmt: Any = None) -> bytes:
        self._hit("download_activity", activity_id)
        a = self._activity(activity_id)
        if not self.with_fit or a["activityType"]["typeKey"] != "running":
            return zip_of(f"{activity_id}.gpx", b"<gpx/>")
        start = datetime.fromisoformat(a["startTimeGMT"].replace(" ", "T")).replace(tzinfo=UTC)
        return zip_of(f"{activity_id}_ACTIVITY.fit", make_fit(fit_points(start, 400)))

    # -- daily
    def get_user_summary(self, cdate: str) -> Any:
        self._hit("get_user_summary", cdate)
        return self._daily("get_user_summary", cdate)

    def get_hydration_data(self, cdate: str) -> Any:
        self._hit("get_hydration_data", cdate)
        return self._daily("get_hydration_data", cdate)

    def get_intensity_minutes_data(self, cdate: str) -> Any:
        self._hit("get_intensity_minutes_data", cdate)
        return self._daily("get_intensity_minutes_data", cdate)

    def get_sleep_data(self, cdate: str) -> Any:
        self._hit("get_sleep_data", cdate)
        return self._daily("get_sleep_data", cdate)

    def get_hrv_data(self, cdate: str) -> Any:
        self._hit("get_hrv_data", cdate)
        return self._daily("get_hrv_data", cdate)

    def get_heart_rates(self, cdate: str) -> Any:
        self._hit("get_heart_rates", cdate)
        return self._daily("get_heart_rates", cdate)

    def get_stress_data(self, cdate: str) -> Any:
        self._hit("get_stress_data", cdate)
        return self._daily("get_stress_data", cdate)

    def get_respiration_data(self, cdate: str) -> Any:
        self._hit("get_respiration_data", cdate)
        return self._daily("get_respiration_data", cdate)

    def get_spo2_data(self, cdate: str) -> Any:
        self._hit("get_spo2_data", cdate)
        return self._daily("get_spo2_data", cdate)

    def get_steps_data(self, cdate: str) -> Any:
        self._hit("get_steps_data", cdate)
        return self._daily("get_steps_data", cdate)

    def get_training_readiness(self, cdate: str) -> Any:
        self._hit("get_training_readiness", cdate)
        return self._daily("get_training_readiness", cdate)

    def get_training_status(self, cdate: str) -> Any:
        self._hit("get_training_status", cdate)
        return self._daily("get_training_status", cdate)

    def get_max_metrics(self, cdate: str) -> Any:
        self._hit("get_max_metrics", cdate)
        return self._daily("get_max_metrics", cdate)

    # -- monthly ranges
    def get_body_composition(self, startdate: str, enddate: str | None = None) -> Any:
        self._hit("get_body_composition", startdate)
        return self._monthly("get_body_composition", startdate)

    def get_blood_pressure(self, startdate: str, enddate: str | None = None) -> Any:
        self._hit("get_blood_pressure", startdate)
        return self._monthly("get_blood_pressure", startdate)

    def get_race_predictions(
        self, startdate: str | None = None, enddate: str | None = None, _type: str | None = None
    ) -> Any:
        self._hit("get_race_predictions", startdate)
        assert _type == "daily" and startdate is not None
        return self._monthly("get_race_predictions", startdate)

    def get_endurance_score(
        self, startdate: str, enddate: str | None = None, aggregation: str = "weekly"
    ) -> Any:
        self._hit("get_endurance_score", startdate)
        assert aggregation == "daily"
        return self._monthly("get_endurance_score", startdate)

    def get_hill_score(self, startdate: str, enddate: str | None = None) -> Any:
        self._hit("get_hill_score", startdate)
        return self._monthly("get_hill_score", startdate)


def factory_for(**config: Any) -> Callable[..., FakeGarmin]:
    """A `garminconnect.Garmin` stand-in constructor with fixed fake configuration."""
    created: list[FakeGarmin] = []

    def make(**kwargs: Any) -> FakeGarmin:
        fake = FakeGarmin(**{**config, **kwargs})
        created.append(fake)
        return fake

    make.created = created  # type: ignore[attr-defined]
    return make
