from typing import Optional, Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.persistence.models.audit import AuditEventModel
from backend.app.persistence.repositories.base import BaseRepository


class AuditRepository(BaseRepository[AuditEventModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuditEventModel, session)

    async def get_last_event(self, session_id: UUID) -> Optional[AuditEventModel]:
        stmt = (
            select(AuditEventModel)
            .filter(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number.desc())
            .limit(1)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_session_chain(self, session_id: UUID) -> Sequence[AuditEventModel]:
        stmt = (
            select(AuditEventModel)
            .filter(AuditEventModel.session_id == session_id)
            .order_by(AuditEventModel.sequence_number.asc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()
