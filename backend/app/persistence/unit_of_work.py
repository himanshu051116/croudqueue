from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import AsyncSessionLocal
from backend.app.persistence.repositories.audit_repository import AuditRepository
from backend.app.persistence.repositories.run_repository import RunRepository


class UnitOfWork:
    def __init__(self) -> None:
        self.session_factory = AsyncSessionLocal
        self.session: Optional[AsyncSession] = None

    async def __aenter__(self) -> "UnitOfWork":
        self.session = self.session_factory()
        self.runs = RunRepository(self.session)
        self.audits = AuditRepository(self.session)
        return self

    async def __aexit__(
        self, exc_type: object, exc_val: object, exc_tb: object
    ) -> None:
        if self.session:
            if exc_type is not None:
                await self.rollback()
            await self.session.close()

    async def commit(self) -> None:
        if self.session:
            await self.session.commit()

    async def rollback(self) -> None:
        if self.session:
            await self.session.rollback()
