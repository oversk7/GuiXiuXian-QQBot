"""宠物对话历史仓储"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.pet_dialogue_history import PetDialogueHistory


class PetDialogueHistoryRepository(IRepository[PetDialogueHistory]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> Optional[PetDialogueHistory]:
        return await self._session.get(PetDialogueHistory, id)

    async def add(self, entity: PetDialogueHistory) -> PetDialogueHistory:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PetDialogueHistory) -> PetDialogueHistory:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PetDialogueHistory):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, id: int) -> bool:
        return await self.get_by_id(id) is not None

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(PetDialogueHistory.id)))
        return result.scalar_one()

    async def get_recent(self, pet_id: int, player_id: str, limit: int = 10) -> List[PetDialogueHistory]:
        """获取最近对话记录"""
        stmt = (
            select(PetDialogueHistory)
            .where(
                PetDialogueHistory.pet_id == pet_id,
                PetDialogueHistory.player_id == player_id
            )
            .order_by(PetDialogueHistory.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
