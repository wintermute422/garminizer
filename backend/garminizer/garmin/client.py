"""Read-only wrapper around `garminconnect.Garmin`.

Only the library methods named in READ_METHODS can be called (`GarminClient.call`). Every call
is throttled (minimum delay between requests), retried with exponential backoff and jitter on
rate limits (HTTP 429) and transient failures (5xx, network errors), and counted. Failures are
translated into the small exception hierarchy below. Arguments, responses, credentials and
tokens are never logged; log lines carry the method name, attempt and delay only.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from garminconnect import (
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

log = logging.getLogger(__name__)

# Every Garmin method this application may call. All of them are HTTP GETs (data reads or the
# original-file download). A test asserts each name exists on `garminconnect.Garmin` and that
# none is a write (add_/set_/update_/delete_/upload_/... or login/logout).
READ_METHODS: Final[frozenset[str]] = frozenset(
    {
        # profile, settings, devices, gear
        "get_user_profile",
        "get_personal_information",
        "get_user_profile_base",
        "get_heart_rate_zones",
        "get_devices",
        "get_device_last_used",
        "get_gear",
        "get_gear_stats",
        # activities
        "count_activities",
        "get_activities",
        "get_activity",
        "get_activity_splits",
        "get_activity_hr_in_timezones",
        "get_activity_weather",
        "get_activity_gear",
        "download_activity",
        # daily wellness
        "get_user_summary",
        "get_sleep_data",
        "get_hrv_data",
        "get_heart_rates",
        "get_stress_data",
        "get_respiration_data",
        "get_spo2_data",
        "get_steps_data",
        "get_hydration_data",
        "get_intensity_minutes_data",
        # training and performance
        "get_training_readiness",
        "get_training_status",
        "get_max_metrics",
        "get_race_predictions",
        "get_endurance_score",
        "get_hill_score",
        # body
        "get_body_composition",
        "get_blood_pressure",
        # records, badges, goals
        "get_personal_record",
        "get_earned_badges",
        "get_goals",
    }
)

_STATUS_RE = re.compile(r"\b(?:API Error|HTTP|status[ =:]*)\s*(\d{3})\b", re.IGNORECASE)
_NETWORK_HINTS = ("connection", "timeout", "timed out", "reset", "refused", "unreachable")


class GarminError(RuntimeError):
    """Base class for everything the wrapper raises."""


class GarminAuthError(GarminError):
    """Not logged in, tokens missing/expired, or credentials rejected."""


class GarminRateLimitError(GarminError):
    """Garmin kept answering 429 after all retries."""


class GarminConnectionError(GarminError):
    """Transient failure (5xx, network) that persisted after all retries."""


class GarminRequestError(GarminError):
    """A request Garmin refused or answered unusably (4xx, empty body); not retried."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GarminNotFoundError(GarminRequestError):
    """HTTP 404: the resource does not exist (treated as "no data")."""


class MethodNotAllowedError(GarminError):
    """The method is not on the read whitelist."""


@dataclass(frozen=True)
class Identity:
    """Who is logged in (copied from the library's profile at login)."""

    display_name: str | None
    full_name: str | None
    profile_id: int | None


def _status_of(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int):
        return status
    match = _STATUS_RE.search(str(exc))
    return int(match.group(1)) if match else None


def _is_network(exc: BaseException) -> bool:
    """True when a raw network error (socket, requests, urllib3, curl) is in the cause chain."""
    seen: set[int] = set()
    cur: BaseException | None = exc
    while cur is not None and id(cur) not in seen:
        seen.add(id(cur))
        if isinstance(cur, ConnectionError | TimeoutError):
            return True
        module = type(cur).__module__
        name = type(cur).__name__.lower()
        if module.startswith(("requests", "urllib3", "curl_cffi", "socket", "ssl")) and any(
            hint in name for hint in ("connection", "timeout", "ssl", "protocol")
        ):
            return True
        cur = cur.__cause__ or cur.__context__
    return False


def classify(exc: Exception) -> tuple[str, int | None]:
    """Map a library exception to (kind, status); kind is auth|rate|transient|notfound|request."""
    if isinstance(exc, GarminConnectAuthenticationError):
        return "auth", 401
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return "rate", 429
    if isinstance(exc, GarminConnectNotFoundError):
        return "notfound", 404
    status = _status_of(exc)
    if isinstance(exc, GarminConnectConnectionError):
        if status == 401:
            return "auth", status
        if status == 429:
            return "rate", status
        if status == 404:
            return "notfound", status
        if status is not None and status >= 500:
            return "transient", status
        if status is None and (
            _is_network(exc) or any(h in str(exc).lower() for h in _NETWORK_HINTS)
        ):
            return "transient", None
        return "request", status
    if _is_network(exc):
        return "transient", None
    return "request", status


class GarminClient:
    """Throttled, retrying, read-only access to one logged-in `garminconnect.Garmin`.

    The underlying library object is captured in a closure and not stored as an attribute,
    so `call()` with a whitelisted name is the only way to reach Garmin through this object.
    """

    __slots__ = (
        "_backoff_base_s",
        "_backoff_max_s",
        "_clock",
        "_delay_s",
        "_invoke",
        "_last_call",
        "_max_retries",
        "_rate_base_s",
        "_requests",
        "_sleep",
        "identity",
    )

    def __init__(
        self,
        api: Any,
        *,
        delay_s: float = 1.0,
        max_retries: int = 5,
        backoff_base_s: float = 2.0,
        rate_limit_base_s: float = 30.0,
        backoff_max_s: float = 300.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.identity = Identity(
            display_name=_str_or_none(getattr(api, "display_name", None)),
            full_name=_str_or_none(getattr(api, "full_name", None)),
            profile_id=_int_or_none(getattr(api, "profile_id", None)),
        )

        def invoke(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
            return getattr(api, name)(*args, **kwargs)

        self._invoke = invoke
        self._delay_s = max(0.0, delay_s)
        self._max_retries = max(0, max_retries)
        self._backoff_base_s = backoff_base_s
        self._rate_base_s = rate_limit_base_s
        self._backoff_max_s = backoff_max_s
        self._sleep = sleep
        self._clock = clock
        self._last_call: float | None = None
        self._requests = 0

    @property
    def request_count(self) -> int:
        """HTTP requests attempted so far (retries included)."""
        return self._requests

    def call(self, name: str, *args: Any, **kwargs: Any) -> Any:
        """Call a whitelisted read method; raises a GarminError subclass on failure."""
        if name not in READ_METHODS:
            raise MethodNotAllowedError(f"{name!r} is not a whitelisted Garmin read method")
        attempt = 0
        while True:
            self._throttle()
            self._requests += 1
            try:
                return self._invoke(name, args, kwargs)
            except (GarminError, ValueError, TypeError) as exc:
                if isinstance(exc, GarminError):
                    raise
                raise GarminRequestError(f"{name}: invalid request ({type(exc).__name__})") from exc
            except Exception as exc:
                kind, status = classify(exc)
                if kind == "auth":
                    raise GarminAuthError(
                        "Garmin rejected the session; log in again (garminizer login)"
                    ) from exc
                if kind == "notfound":
                    raise GarminNotFoundError(f"{name}: not found", 404) from exc
                if kind == "request":
                    raise GarminRequestError(
                        f"{name}: request failed ({type(exc).__name__}, status {status})", status
                    ) from exc
                if attempt >= self._max_retries:
                    if kind == "rate":
                        raise GarminRateLimitError(
                            f"{name}: still rate limited after {attempt} retries"
                        ) from exc
                    raise GarminConnectionError(
                        f"{name}: failed after {attempt} retries (status {status})"
                    ) from exc
                delay = self._backoff(attempt, rate=kind == "rate")
                log.warning(
                    "Garmin %s: %s (status %s), retry %d/%d in %.1fs",
                    name,
                    "rate limited" if kind == "rate" else "transient error",
                    status,
                    attempt + 1,
                    self._max_retries,
                    delay,
                )
                self._sleep(delay)
                attempt += 1

    def _throttle(self) -> None:
        now = self._clock()
        if self._last_call is not None:
            wait = self._last_call + self._delay_s - now
            if wait > 0:
                self._sleep(wait)
                now = self._clock()
        self._last_call = now

    def _backoff(self, attempt: int, *, rate: bool) -> float:
        base = self._rate_base_s if rate else self._backoff_base_s
        capped: float = min(self._backoff_max_s, base * 2.0**attempt)
        return capped * (0.5 + random.random() * 0.5)  # noqa: S311 - jitter, not crypto


def _str_or_none(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_or_none(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
