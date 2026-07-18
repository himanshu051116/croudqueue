from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.run import OutboxEventModel


class OutboxDispatcher:
    """
    Handles atomic claiming and state updates of outbox events.
    Uses PostgreSQL SELECT FOR UPDATE SKIP LOCKED concurrency semantics.
    """

    @staticmethod
    async def claim_next_event(
        session: AsyncSession, processor_id: UUID
    ) -> Optional[OutboxEventModel]:
        """
        Locks and claims the oldest pending outbox event that is ready for delivery.
        Safe for execution by multiple concurrent worker instances.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(OutboxEventModel)
            .filter(
                OutboxEventModel.delivery_status == "PENDING",
                OutboxEventModel.available_at <= now,
                OutboxEventModel.locked_by.is_(None),
            )
            .order_by(OutboxEventModel.created_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        res = await session.execute(stmt)
        event = res.scalar_one_or_none()

        if event:
            event.locked_by = processor_id
            event.locked_at = now
            event.delivery_status = "CLAIMED"
            await session.flush()
        return event

    @staticmethod
    async def mark_processed(session: AsyncSession, event_id: UUID) -> None:
        """Marks a claimed outbox event as successfully processed."""
        stmt = (
            update(OutboxEventModel)
            .where(OutboxEventModel.id == event_id)
            .values(
                delivery_status="PROCESSED",
                processed_at=datetime.now(timezone.utc),
                locked_by=None,
                locked_at=None,
            )
        )
        await session.execute(stmt)
        await session.flush()

    @staticmethod
    async def release_lock(session: AsyncSession, event_id: UUID) -> None:
        """Releases the lock on a claimed outbox event, making it PENDING again."""
        stmt = (
            update(OutboxEventModel)
            .where(OutboxEventModel.id == event_id)
            .values(
                delivery_status="PENDING",
                locked_by=None,
                locked_at=None,
            )
        )
        await session.execute(stmt)
        await session.flush()
