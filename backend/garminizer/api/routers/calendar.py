"""calendar endpoints (implemented in S4)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/calendar", tags=["calendar"])
