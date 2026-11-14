"""Weight goal: trend against the target line, weekly checkpoints, body fat, the daily log with
the energy balance, and the goal settings (also editable from Claude Desktop via MCP)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Response

from garminizer.api.deps import ClockDep, SessionDep
from garminizer.goal import service
from garminizer.goal.schemas import GoalCheckpointIn, GoalEnergyBalance, GoalSettings, GoalView

router = APIRouter(prefix="/api/goal", tags=["goal"])


@router.get("", response_model=GoalView)
def goal_view(session: SessionDep, clock: ClockDep) -> GoalView:
    """Settings, status tiles, every day since the start, checkpoints and body-fat trend."""
    return service.view(session, clock=clock)


@router.put("/settings", response_model=GoalSettings)
def put_settings(session: SessionDep, body: GoalSettings) -> GoalSettings:
    """Create or replace the goal."""
    stored = service.set_settings(session, body)
    session.commit()
    return stored


@router.delete("/settings", status_code=204)
def delete_settings(session: SessionDep) -> Response:
    """Remove the goal (weigh-ins, meals and activities stay)."""
    if not service.clear_settings(session):
        raise HTTPException(status_code=404, detail="no weight goal is set")
    session.commit()
    return Response(status_code=204)


@router.put("/checkpoints/{day}", response_model=GoalSettings)
def put_checkpoint(session: SessionDep, day: date, body: GoalCheckpointIn) -> GoalSettings:
    """Count a checkpoint as reached although the trend was above the target (or undo it)."""
    try:
        stored = service.set_checkpoint(session, day, accepted=body.accepted)
    except service.GoalError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    session.commit()
    return stored


@router.get("/balance", response_model=GoalEnergyBalance)
def balance(
    session: SessionDep,
    clock: ClockDep,
    day: Annotated[date | None, Query(description="Local day (default today)")] = None,
) -> GoalEnergyBalance:
    """Intake vs burn (BMR x activity factor + active training calories) of one day."""
    return service.energy_balance(session, day or clock.today(), clock=clock)
