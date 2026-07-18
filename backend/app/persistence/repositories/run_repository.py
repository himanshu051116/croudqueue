from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.run import (
    IdempotencyKeyModel,
    OutboxEventModel,
    PreflightRun,
    Session,
)
from backend.app.persistence.repositories.base import BaseRepository


class RunRepository(BaseRepository[PreflightRun]):
    def __init__(self, session: AsyncSession):
        super().__init__(PreflightRun, session)

    async def get_active_session(self) -> Optional[Session]:
        stmt = (
            select(Session)
            .filter(Session.ended_at.is_(None))
            .order_by(Session.created_at.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_outbox_event_by_id(
        self, event_id: "UUID"
    ) -> Optional[OutboxEventModel]:
        return await self.session.get(OutboxEventModel, event_id)

    async def get_idempotency_key(self, key_hash: str) -> Optional[IdempotencyKeyModel]:
        return await self.session.get(IdempotencyKeyModel, key_hash)
