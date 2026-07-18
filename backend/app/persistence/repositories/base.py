from typing import Generic, Optional, Sequence, Type, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class BaseRepository(Generic[T]):
    def __init__(self, model_class: Type[T], session: AsyncSession):
        self.model_class = model_class
        self.session = session

    async def get_by_id(self, id_: UUID) -> Optional[T]:
        return await self.session.get(self.model_class, id_)

    async def list_all(self) -> Sequence[T]:
        stmt = select(self.model_class)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: T) -> T:
        self.session.add(entity)
        return entity

    async def delete(self, entity: T) -> None:
        await self.session.delete(entity)
