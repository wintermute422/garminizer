"""insights endpoints (implemented in S4)."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/insights", tags=["insights"])
