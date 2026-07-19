from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.domain.workflow import LifecycleState, validate_transition
from backend.app.persistence.models.run import OutboxEventModel
from backend.app.persistence.models.run import PreflightRun as RunModel
from backend.app.services.audit_service import AuditService


class RunNotFoundError(LookupError):
    pass


class OwnershipError(PermissionError):
    pass


class TransitionError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


def transition_run(run: RunModel, target: LifecycleState) -> LifecycleState:
    current = LifecycleState(run.lifecycle_state)
    if not validate_transition(current, target):
        raise TransitionError(
            f"Invalid transition from {current.value} to {target.value}."
        )
    run.lifecycle_state = target.value
    return current


async def append_event(
    db: AsyncSession,
    *,
    session_id: UUID,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    await AuditService.append_event(db, session_id, run_id, event_type, payload)
    db.add(
        OutboxEventModel(
            event_type=event_type,
            payload={"session_id": str(session_id), "run_id": str(run_id), **payload},
            delivery_status="PENDING",
        )
    )
    await db.flush()
