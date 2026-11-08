"""A3: the Garmin wrapper is read-only. A5 (client part): throttle, backoff, error mapping.

Also the login/MFA/token-store flow (garminizer.garmin.auth) against the fake library object.
"""

from __future__ import annotations

import inspect
import json
import logging
import os
from pathlib import Path
from typing import Any

import pytest
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectNotFoundError,
    GarminConnectTooManyRequestsError,
)

from garminizer.config import Settings
from garminizer.garmin import auth
from garminizer.garmin.client import (
    READ_METHODS,
    GarminAuthError,
    GarminClient,
    GarminConnectionError,
    GarminNotFoundError,
    GarminRateLimitError,
    GarminRequestError,
    MethodNotAllowedError,
)
from tests.garmin_fake import FAKE_EMAIL, FAKE_PASSWORD, MFA_CODE, FakeGarmin, factory_for

WRITE_PREFIXES = (
    "add_",
    "set_",
    "update_",
    "delete_",
    "upload_",
    "create_",
    "schedule_",
    "import_",
    "push_",
    "request_",
)
WRITE_MARKERS = (".post(", ".put(", ".delete(", ".patch(", "upload(")


class Flaky:
    """Raises the queued exceptions, then answers."""

    def __init__(self, errors: list[Exception], result: Any = None) -> None:
        self.errors = errors
        self.result = result if result is not None else {"ok": True}
        self.calls = 0

    def get_user_summary(self, cdate: str) -> Any:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return self.result


def _client(api: Any, **kwargs: Any) -> tuple[GarminClient, list[float]]:
    sleeps: list[float] = []
    kwargs.setdefault("delay_s", 0.0)
    return GarminClient(api, sleep=sleeps.append, **kwargs), sleeps


def _network_error() -> GarminConnectConnectionError:
    err = GarminConnectConnectionError("Request failed")
    err.__cause__ = ConnectionResetError("reset by peer")
    return err


# --- A3: read-only surface -----------------------------------------------------------------


def test_every_whitelisted_method_exists_on_the_library() -> None:
    missing = [name for name in READ_METHODS if not callable(getattr(Garmin, name, None))]
    assert missing == []


def test_whitelist_contains_no_write_or_session_methods() -> None:
    bad = [
        name
        for name in READ_METHODS
        if name.startswith(WRITE_PREFIXES)
        or name.startswith("_")
        or name in {"login", "logout", "resume_login", "connectapi", "connectwebproxy", "download"}
    ]
    assert bad == []


def test_whitelisted_methods_only_issue_get_requests() -> None:
    """Library source of each whitelisted method: no POST/PUT/DELETE/PATCH or uploads."""
    offenders = {
        name: marker
        for name in sorted(READ_METHODS)
        for marker in WRITE_MARKERS
        if marker in inspect.getsource(getattr(Garmin, name))
    }
    assert offenders == {}


@pytest.mark.parametrize(
    "name",
    ["add_weigh_in", "delete_activity", "connectapi", "client", "login", "_hit", "upload_activity"],
)
def test_call_refuses_anything_not_whitelisted(name: str) -> None:
    fake = FakeGarmin()
    client, _ = _client(fake)
    with pytest.raises(MethodNotAllowedError):
        client.call(name)
    assert fake.calls == []
    assert client.request_count == 0


def test_wrapper_exposes_no_other_path_to_the_library() -> None:
    fake = FakeGarmin()
    client, _ = _client(fake)
    public = {n for n in dir(client) if not n.startswith("_")}
    assert public == {"call", "identity", "request_count"}
    for name in dir(client):
        assert getattr(client, name, None) is not fake, name
    assert not hasattr(client, "__dict__")
    with pytest.raises(TypeError):
        vars(client)
    assert client.identity.display_name == "demo-athlete"
    assert client.identity.profile_id == 1234567890


# --- A5: throttle, backoff, error mapping --------------------------------------------------


def test_rate_limits_are_retried_with_exponential_backoff() -> None:
    api = Flaky(
        [GarminConnectTooManyRequestsError("429"), GarminConnectTooManyRequestsError("429")]
    )
    client, sleeps = _client(api, rate_limit_base_s=30.0, backoff_max_s=300.0)
    assert client.call("get_user_summary", "2024-05-01") == {"ok": True}
    assert api.calls == 3
    assert client.request_count == 3
    assert len(sleeps) == 2
    assert 15.0 <= sleeps[0] <= 30.0  # 30 s base, 50-100 % jitter
    assert 30.0 <= sleeps[1] <= 60.0  # doubled


def test_transient_server_and_network_errors_are_retried() -> None:
    api = Flaky([GarminConnectConnectionError("API Error 503 - unavailable"), _network_error()])
    client, sleeps = _client(api, backoff_base_s=2.0)
    assert client.call("get_user_summary", "2024-05-01") == {"ok": True}
    assert api.calls == 3
    assert 1.0 <= sleeps[0] <= 2.0
    assert 2.0 <= sleeps[1] <= 4.0


def test_retries_are_bounded() -> None:
    client, sleeps = _client(
        Flaky([GarminConnectTooManyRequestsError("429") for _ in range(10)]), max_retries=2
    )
    with pytest.raises(GarminRateLimitError):
        client.call("get_user_summary", "2024-05-01")
    assert client.request_count == 3
    assert len(sleeps) == 2

    client, _ = _client(Flaky([_network_error() for _ in range(10)]), max_retries=1)
    with pytest.raises(GarminConnectionError):
        client.call("get_user_summary", "2024-05-01")
    assert client.request_count == 2


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (GarminConnectAuthenticationError("401"), GarminAuthError),
        (GarminConnectConnectionError("API Error 401 - Unauthorized"), GarminAuthError),
        (GarminConnectNotFoundError("API Error 404"), GarminNotFoundError),
        (GarminConnectConnectionError("API Error 400 - bad date"), GarminRequestError),
        (GarminConnectConnectionError("No data received from server"), GarminRequestError),
        (ValueError("cdate must be YYYY-MM-DD"), GarminRequestError),
    ],
)
def test_non_retryable_errors_fail_fast(error: Exception, expected: type[Exception]) -> None:
    client, sleeps = _client(Flaky([error]))
    with pytest.raises(expected):
        client.call("get_user_summary", "2024-05-01")
    assert client.request_count == 1
    assert sleeps == []


def test_requests_are_throttled() -> None:
    now = [100.0]
    sleeps: list[float] = []

    def sleep(s: float) -> None:
        sleeps.append(s)
        now[0] += s

    client = GarminClient(Flaky([]), delay_s=1.5, sleep=sleep, clock=lambda: now[0])
    client.call("get_user_summary", "2024-05-01")
    client.call("get_user_summary", "2024-05-02")
    assert sleeps == [1.5]
    now[0] += 10
    client.call("get_user_summary", "2024-05-03")
    assert sleeps == [1.5]
    assert client.request_count == 3


def test_log_lines_carry_no_arguments(caplog: pytest.LogCaptureFixture) -> None:
    client, _ = _client(Flaky([GarminConnectConnectionError("API Error 502")]))
    with caplog.at_level(logging.DEBUG):
        client.call("get_user_summary", "2031-12-24")
    assert "get_user_summary" in caplog.text
    assert "2031-12-24" not in caplog.text


# --- login, MFA, token store ---------------------------------------------------------------


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", sync_request_delay_s=0, _env_file=None)


def test_login_saves_tokens_and_drops_the_password(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    factory = factory_for()
    result = auth.login(FAKE_EMAIL, FAKE_PASSWORD, settings=settings, factory=factory)
    assert result.status == "ok"
    assert result.client is not None
    assert result.client.identity.display_name == "demo-athlete"
    assert auth.has_tokens(settings)
    first: FakeGarmin = factory.created[0]  # type: ignore[attr-defined]
    assert first.password is None
    token_file = auth.token_file(settings)
    if os.name == "posix":
        assert token_file.stat().st_mode & 0o777 == 0o600
        assert settings.token_dir.stat().st_mode & 0o777 == 0o700
    assert auth.resume(settings, factory).identity.profile_id == 1234567890


def test_wrong_credentials_are_a_typed_auth_error(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    with pytest.raises(GarminAuthError) as info:
        auth.login(FAKE_EMAIL, "wrong", settings=settings, factory=factory_for())
    assert "wrong" not in str(info.value)
    assert not auth.has_tokens(settings)


def test_mfa_flow_keeps_the_pending_state_in_memory_only(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = auth.login(
        FAKE_EMAIL, FAKE_PASSWORD, settings=settings, factory=factory_for(mfa_required=True)
    )
    assert result.status == "needs_mfa"
    assert result.state is not None
    assert not auth.has_tokens(settings)
    assert not settings.data_dir.exists() or not any(settings.data_dir.rglob("*.json"))
    with pytest.raises(GarminAuthError):
        auth.complete_mfa(result.state, "000000", settings=settings)
    client = auth.complete_mfa(result.state, MFA_CODE, settings=settings)
    assert client.identity.display_name == "demo-athlete"
    assert auth.has_tokens(settings)
    assert [p.name for p in settings.token_dir.iterdir()] == [auth.TOKEN_FILE]


def test_mfa_state_expires(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    result = auth.login(
        FAKE_EMAIL, FAKE_PASSWORD, settings=settings, factory=factory_for(mfa_required=True)
    )
    assert result.state is not None
    result.state.created_at -= auth.MFA_TTL_S + 1
    with pytest.raises(GarminAuthError):
        auth.complete_mfa(result.state, MFA_CODE, settings=settings)


def test_resume_without_tokens_is_an_auth_error(tmp_path: Path) -> None:
    with pytest.raises(GarminAuthError):
        auth.resume(_settings(tmp_path), factory_for())


def test_token_files_must_look_valid(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    auth.ensure_token_dir(settings)
    path = auth.token_file(settings)
    path.write_text("not json", encoding="utf-8")
    assert not auth.has_tokens(settings)
    path.write_text(json.dumps({"di_token": "x"}), encoding="utf-8")
    assert not auth.has_tokens(settings)
    path.write_text(json.dumps({"di_token": "x", "di_refresh_token": "y"}), encoding="utf-8")
    assert auth.has_tokens(settings)


def test_disconnect_deletes_local_tokens(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    auth.login(FAKE_EMAIL, FAKE_PASSWORD, settings=settings, factory=factory_for())
    assert auth.disconnect(settings) is True
    assert not auth.has_tokens(settings)
    assert auth.disconnect(settings) is False
