from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.models.run import Session as SessionModel
from backend.app.services.integrity import domain_hash

GENESIS_HASH = domain_hash("CROWDCUE_AUDIT_GENESIS_V1", "GENESIS")


def audit_timestamp(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


def compute_audit_hash(
    previous_hash: str,
    payload: dict[str, Any],
    event_type: str,
    created_at_iso: str,
    sequence_number: int,
) -> str:
    return domain_hash(
        "CROWDCUE_AUDIT_EVENT_V1",
        {
            "previous_event_hash": previous_hash,
            "payload": payload,
            "event_type": event_type,
            "created_at": created_at_iso,
            "sequence_number": sequence_number,
        },
    )


class AuditService:
    @staticmethod
    async def append_event(
        session: AsyncSession,
        session_id: UUID,
        run_id: UUID | None,
        event_type: str,
        payload: dict[str, Any],
    ) -> AuditEventModel:
        # Serialise each session's chain. PostgreSQL honours this lock; SQLite test
        # mode executes serially and still validates the hash contract.
        session_row = await session.execute(
            select(SessionModel).where(SessionModel.id == session_id).with_for_update()
        )
        if session_row.scalar_one_or_none() is None:
            raise ValueError("Cannot append audit event for an unknown session.")
        result = await session.execute(
            select(AuditEventModel)
            .where(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number.desc())
            .limit(1)
            .with_for_update()
        )
        previous = result.scalar_one_or_none()
        sequence = previous.sequence_number + 1 if previous else 0
        previous_hash = previous.event_hash if previous else GENESIS_HASH
        created_at = datetime.now(timezone.utc)
        event_hash = compute_audit_hash(
            previous_hash,
            payload,
            event_type,
            audit_timestamp(created_at),
            sequence,
        )
        event = AuditEventModel(
            session_id=session_id,
            run_id=run_id,
            event_type=event_type,
            payload=payload,
            sequence_number=sequence,
            previous_event_hash=previous_hash,
            event_hash=event_hash,
            created_at=created_at,
        )
        session.add(event)
        await session.flush()
        return event

    @staticmethod
    def verify_chain(events: list[AuditEventModel]) -> bool:
        expected_previous = GENESIS_HASH
        for expected_sequence, event in enumerate(events):
            if event.sequence_number != expected_sequence:
                return False
            if event.previous_event_hash != expected_previous:
                return False
            expected_hash = compute_audit_hash(
                expected_previous,
                event.payload,
                event.event_type,
                audit_timestamp(event.created_at),
                event.sequence_number,
            )
            if event.event_hash != expected_hash:
                return False
            expected_previous = event.event_hash
        return True
