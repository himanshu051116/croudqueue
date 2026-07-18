from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.services.golden_flow_service import (
    GoldenFlowService,
    OwnershipError,
    RunNotFoundError,
    TransitionError,
    ValidationError,
)

router = APIRouter(prefix="/api/runs", tags=["Golden Flow Runs"])


class RunCreateRequest(BaseModel):
    session_id: UUID
    scenario_key: str = Field(min_length=1, max_length=100)


class SelectCandidateRequest(BaseModel):
    candidate_id: UUID


class GenerateGuidanceRequest(BaseModel):
    enable_fault_injection: bool = False


class ApproveRequest(BaseModel):
    approved_by_user_id: UUID
    approver_role: str = Field(min_length=2, max_length=80)
    approval_note: str | None = Field(default=None, max_length=1000)
    expected_bundle_hash: str = Field(min_length=64, max_length=64)


async def require_session_id(
    x_session_id: UUID = Header(alias="X-Session-ID"),
) -> UUID:
    return x_session_id


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, RunNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, OwnershipError):
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, TransitionError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, (ValidationError, ValueError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        )
    if isinstance(exc, IntegrityError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The requested operation conflicts with existing state.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The operation could not be completed.",
    )


async def _execute(operation: Any, db: AsyncSession) -> dict[str, Any]:
    try:
        return cast(dict[str, Any], await operation)
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise _http_error(exc) from exc


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_run(
    request: RunCreateRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.create_run(
            db, session_id=request.session_id, scenario_key=request.scenario_key
        ),
        db,
    )


@router.post("/{run_id}/select-candidate")
async def select_candidate(
    run_id: UUID,
    request: SelectCandidateRequest,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.select_candidate(
            db,
            run_id=run_id,
            session_id=session_id,
            candidate_id=request.candidate_id,
        ),
        db,
    )


@router.post("/{run_id}/generate-guidance")
async def generate_guidance(
    run_id: UUID,
    request: GenerateGuidanceRequest,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.generate_guidance(
            db,
            run_id=run_id,
            session_id=session_id,
            enable_fault_injection=request.enable_fault_injection,
        ),
        db,
    )


@router.post("/{run_id}/repair")
async def repair_guidance(
    run_id: UUID,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.repair(db, run_id=run_id, session_id=session_id), db
    )


@router.post("/{run_id}/simulate")
async def simulate(
    run_id: UUID,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.simulate(db, run_id=run_id, session_id=session_id), db
    )


@router.post("/{run_id}/approve", status_code=status.HTTP_201_CREATED)
async def approve(
    run_id: UUID,
    request: ApproveRequest,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.approve(
            db,
            run_id=run_id,
            session_id=session_id,
            approved_by_user_id=request.approved_by_user_id,
            approver_role=request.approver_role,
            approval_note=request.approval_note,
            expected_bundle_hash=request.expected_bundle_hash,
        ),
        db,
    )


@router.post("/{run_id}/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish(
    run_id: UUID,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.publish(db, run_id=run_id, session_id=session_id), db
    )


@router.get("/{run_id}")
async def run_details(
    run_id: UUID,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.details(db, run_id=run_id, session_id=session_id), db
    )


@router.get("/{run_id}/audit")
async def audit_timeline(
    run_id: UUID,
    session_id: UUID = Depends(require_session_id),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _execute(
        GoldenFlowService.audit_timeline(db, run_id=run_id, session_id=session_id),
        db,
    )
