"""Optional single-user password protection.

Without APP_PASSWORD the app only listens on loopback (enforced at startup) and needs no login.
With APP_PASSWORD every /api route except health and auth requires a signed session cookie.
State-changing requests must carry `X-Requested-With: garminizer` (CSRF guard; the cookie is
also SameSite=Strict).
"""

from __future__ import annotations

import hmac
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from itsdangerous import BadSignature, SignatureExpired, TimestampSigner
from pydantic import BaseModel
from sqlalchemy.orm import Session

from garminizer.config import Settings
from garminizer.models import AppSetting

COOKIE = "garminizer_session"
MAX_AGE_S = 30 * 24 * 3600
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "garminizer"
PUBLIC_PATHS = ("/api/health", "/api/auth/")
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
LOGIN_ATTEMPTS, LOGIN_WINDOW_S = 5, 60.0


def secret_key(settings: Settings, session: Session) -> str:
    """APP_SECRET_KEY, or a random key generated once and kept in app_setting."""
    if settings.app_secret_key is not None:
        return settings.app_secret_key.get_secret_value()
    row = session.get(AppSetting, "secret_key")
    if row is None:
        row = AppSetting(key="secret_key", value={"key": secrets.token_urlsafe(48)})
        session.add(row)
        session.commit()
    return str(row.value["key"])


class _RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > LOGIN_WINDOW_S:
            hits.popleft()
        if len(hits) >= LOGIN_ATTEMPTS:
            return False
        hits.append(now)
        return True


class LoginBody(BaseModel):
    password: str


class AuthStatus(BaseModel):
    required: bool
    authenticated: bool


router = APIRouter(prefix="/api/auth", tags=["auth"])
_limiter = _RateLimiter()


def _signer(request: Request) -> TimestampSigner:
    return TimestampSigner(request.app.state.secret_key, salt="session")


def is_authenticated(request: Request) -> bool:
    settings: Settings = request.app.state.settings
    if settings.app_password is None:
        return True
    token = request.cookies.get(COOKIE)
    if not token:
        return False
    try:
        _signer(request).unsign(token, max_age=MAX_AGE_S)
    except (BadSignature, SignatureExpired):
        return False
    return True


@router.get("/status", response_model=AuthStatus)
def auth_status(request: Request) -> AuthStatus:
    required = request.app.state.settings.app_password is not None
    return AuthStatus(required=required, authenticated=is_authenticated(request))


@router.post("/login", response_model=AuthStatus)
def login(body: LoginBody, request: Request, response: Response) -> AuthStatus:
    settings: Settings = request.app.state.settings
    if settings.app_password is None:
        return AuthStatus(required=False, authenticated=True)
    client = request.client.host if request.client else "unknown"
    if not _limiter.allow(client):
        raise HTTPException(status_code=429, detail="too many login attempts, wait a minute")
    expected = settings.app_password.get_secret_value()
    if not hmac.compare_digest(body.password.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="wrong password")
    token = _signer(request).sign(secrets.token_hex(8)).decode()
    response.set_cookie(
        COOKIE,
        token,
        max_age=MAX_AGE_S,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
    )
    return AuthStatus(required=True, authenticated=True)


@router.post("/logout", response_model=AuthStatus)
def logout(request: Request, response: Response) -> AuthStatus:
    response.delete_cookie(COOKIE)
    return AuthStatus(
        required=request.app.state.settings.app_password is not None, authenticated=False
    )


async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """Middleware: login + CSRF header for /api; everything else (the SPA) is public."""
    path = request.url.path
    protected = path.startswith("/api") and not path.startswith(PUBLIC_PATHS)
    if protected and not is_authenticated(request):
        return JSONResponse({"detail": "login required"}, status_code=401)
    if (
        path.startswith("/api")
        and request.method not in SAFE_METHODS
        and request.headers.get(CSRF_HEADER) != CSRF_VALUE
    ):
        return JSONResponse({"detail": f"missing {CSRF_HEADER} header"}, status_code=403)
    return await call_next(request)
