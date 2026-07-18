from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.domain.venue import VenueTopology
from backend.app.services.golden_flow_service import (
    GoldenFlowService,
    OwnershipError,
    RunNotFoundError,
)
from backend.app.services.venue_service import VenueService

router = APIRouter(prefix="/api/venue", tags=["Venue and Scenarios"])


class StructuredIntentSchema(BaseModel):
    objective: str
    target: str
    affected_audience: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    excluded_cohorts: list[str] = Field(default_factory=list)


class ScenarioConfigSchema(BaseModel):
    key: str
    name: str
    description: str
    default_intent: StructuredIntentSchema


class EvaluationRequest(BaseModel):
    scenario_key: str
    session_id: UUID


@router.get("/topology", response_model=VenueTopology)
async def get_topology() -> VenueTopology:
    try:
        return VenueService.load_topology()
    except (OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load the validated venue topology: {exc}",
        ) from exc


@router.get("/scenarios", response_model=list[ScenarioConfigSchema])
async def get_scenarios() -> list[ScenarioConfigSchema]:
    scenarios = VenueService.load_scenarios()
    return [
        ScenarioConfigSchema(
            key=item["key"],
            name=item["name"],
            description=item["description"],
            default_intent=StructuredIntentSchema.model_validate(
                item["default_intent"]
            ),
        )
        for item in scenarios
    ]


@router.post("/evaluate", status_code=status.HTTP_201_CREATED, deprecated=True)
async def evaluate_scenario(
    request: EvaluationRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    """Compatibility endpoint. New clients should use POST /api/runs."""
    try:
        return await GoldenFlowService.create_run(
            db,
            session_id=request.session_id,
            scenario_key=request.scenario_key,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.get("/snapshot/{snapshot_id}")
async def get_snapshot(
    snapshot_id: UUID,
    session_id: UUID = Header(alias="X-Session-ID"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        return await GoldenFlowService.snapshot_details(
            db, snapshot_id=snapshot_id, session_id=session_id
        )
    except RunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
