"""Garmin login, MFA and the local token store.

Mechanism (garminconnect 0.3.20, `Garmin.login` / `Garmin.resume_login`):

* `login()` builds `Garmin(email, password, return_on_mfa=True)` and calls `.login()` without a
  token store. The library then runs its credential strategy chain and returns
  `("needs_mfa", client_state)` when Garmin asks for a code, or `(None, None)` on success.
  In return-on-MFA mode the library neither loads the profile nor writes tokens, so on success
  the DI tokens are written with the library's own `client.dump()` (0600 file, 0700 dir) and
  the session is reopened from those tokens (`resume()`), which loads the profile.
* `complete_mfa()` calls `.resume_login(client_state, code)` on the *same* `Garmin` instance
  (it holds the pending SSO session; the state lives in memory only and is never written to
  disk or the database), then dumps the tokens.
* `resume()` builds `Garmin()` and calls `.login(token_dir)`: the library loads the tokens,
  refreshes them when they are about to expire (and writes them back) and loads the profile.

The password is only passed to the library and dropped right after the login.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from garminconnect import GarminConnectAuthenticationError, GarminConnectTooManyRequestsError

from garminizer.config import Settings, get_settings
from garminizer.garmin.client import (
    GarminAuthError,
    GarminClient,
    GarminConnectionError,
    GarminError,
    GarminRateLimitError,
)

TOKEN_FILE = "garmin_tokens.json"  # noqa: S105 - a file name, not a secret
MFA_TTL_S = 600.0
MAX_TOKEN_FILE_BYTES = 64 * 1024

GarminFactory = Callable[..., Any]


def default_factory() -> GarminFactory:
    from garminconnect import Garmin  # noqa: PLC0415 - keep imports light for the API

    return Garmin


@dataclass
class PendingMfa:
    """A login waiting for its MFA code. Holds the SSO session: memory only, never persisted."""

    api: Any = field(repr=False)
    client_state: Any = field(repr=False)
    created_at: float = field(default_factory=time.monotonic)

    def expired(self, now: float | None = None) -> bool:
        return ((now if now is not None else time.monotonic()) - self.created_at) > MFA_TTL_S


@dataclass(frozen=True)
class LoginResult:
    status: Literal["ok", "needs_mfa"]
    state: PendingMfa | None = None
    client: GarminClient | None = None


def token_file(settings: Settings) -> Path:
    return settings.token_dir / TOKEN_FILE


def ensure_token_dir(settings: Settings) -> Path:
    path = settings.token_dir
    path.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError):
        path.chmod(0o700)
    return path


def has_tokens(settings: Settings | None = None) -> bool:
    """True when a token file exists and looks valid (both DI tokens present)."""
    path = token_file(settings or get_settings())
    try:
        if path.is_symlink() or not path.is_file():
            return False
        if path.stat().st_size > MAX_TOKEN_FILE_BYTES:
            return False
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and all(
        isinstance(data.get(k), str) and bool(data.get(k)) for k in ("di_token", "di_refresh_token")
    )


def make_client(api: Any, settings: Settings) -> GarminClient:
    return GarminClient(api, delay_s=settings.sync_request_delay_s)


def _translate(exc: Exception) -> GarminError:
    """A login failure as a GarminError, without the library's message (no account details)."""
    if isinstance(exc, GarminError):
        return exc
    if isinstance(exc, GarminConnectAuthenticationError):
        return GarminAuthError("Garmin rejected the login (check e-mail, password or MFA code)")
    if isinstance(exc, GarminConnectTooManyRequestsError):
        return GarminRateLimitError("Garmin is limiting login attempts; wait a few minutes")
    return GarminConnectionError(f"Garmin login failed ({type(exc).__name__})")


def _save_tokens(api: Any, settings: Settings) -> None:
    directory = ensure_token_dir(settings)
    api.client.dump(str(directory))
    with contextlib.suppress(OSError):
        token_file(settings).chmod(0o600)


def login(
    email: str,
    password: str,
    *,
    settings: Settings | None = None,
    factory: GarminFactory | None = None,
) -> LoginResult:
    """Start a credential login; returns status ok (tokens saved) or needs_mfa (+ state)."""
    settings = settings or get_settings()
    factory = factory or default_factory()
    if not email or not password:
        raise GarminAuthError("e-mail and password are required")
    try:
        api = factory(email=email, password=password, return_on_mfa=True, retry_attempts=0)
        status, client_state = api.login()
    except Exception as exc:
        raise _translate(exc) from None
    if status == "needs_mfa":
        return LoginResult(status="needs_mfa", state=PendingMfa(api, client_state))
    _save_tokens(api, settings)
    api.password = None
    return LoginResult(status="ok", client=resume(settings, factory))


def complete_mfa(
    state: PendingMfa,
    code: str,
    *,
    settings: Settings | None = None,
) -> GarminClient:
    """Finish a pending login with the MFA code; saves the tokens."""
    settings = settings or get_settings()
    if state.expired():
        raise GarminAuthError("the MFA code request expired; start the login again")
    code = code.strip()
    if not code:
        raise GarminAuthError("MFA code is empty")
    try:
        state.api.resume_login(state.client_state, code)
    except Exception as exc:
        raise _translate(exc) from None
    _save_tokens(state.api, settings)
    state.api.password = None
    state.client_state = None
    return make_client(state.api, settings)


def resume(settings: Settings | None = None, factory: GarminFactory | None = None) -> GarminClient:
    """A client from the saved tokens (refreshed by the library when needed)."""
    settings = settings or get_settings()
    factory = factory or default_factory()
    if not has_tokens(settings):
        raise GarminAuthError(
            "not connected to Garmin: run `garminizer login` or use Connect Garmin in the app"
        )
    try:
        api = factory(retry_attempts=0)
        api.login(str(settings.token_dir))
    except GarminConnectAuthenticationError:
        raise GarminAuthError(
            "the saved Garmin tokens were rejected or expired; log in again"
        ) from None
    except Exception as exc:
        raise _translate(exc) from None
    return make_client(api, settings)


def disconnect(settings: Settings | None = None) -> bool:
    """Delete the local token file(s). Returns True when something was deleted."""
    settings = settings or get_settings()
    directory = settings.token_dir
    deleted = False
    if not directory.is_dir():
        return False
    for path in directory.iterdir():
        name = path.name
        if name == TOKEN_FILE or (name.startswith(f".{TOKEN_FILE}.") and name.endswith(".tmp")):
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)  # noqa: PTH107 - explicit, works for read-only files on Windows
                deleted = True
    return deleted
