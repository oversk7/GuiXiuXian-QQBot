"""
灵田仓储实现
"""
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.spirit_field import SpiritField


class SpiritFieldRepository(IRepository[SpiritField]):
    """灵田仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, field_id: int) -> Optional[SpiritField]:
        return await self._session.get(SpiritField, field_id)

    async def add(self, entity: SpiritField) -> SpiritField:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: SpiritField) -> SpiritField:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: SpiritField):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, field_id: int) -> bool:
        entity = await self.get_by_id(field_id)
        return entity is not None

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(SpiritField.id))
        )
        return result.scalar_one()

    async def get_by_player_id(self, player_id: str) -> Optional[SpiritField]:
        """根据玩家ID获取灵田"""
        stmt = select(SpiritField).where(SpiritField.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
