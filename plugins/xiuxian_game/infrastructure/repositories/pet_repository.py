"""宠物仓储实现"""
from typing import Optional, List
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.pet_instance import PetInstance


class PetRepository(IRepository[PetInstance]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> Optional[PetInstance]:
        return await self._session.get(PetInstance, id)

    async def add(self, entity: PetInstance) -> PetInstance:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PetInstance) -> PetInstance:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PetInstance):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, id: int) -> bool:
        return await self.get_by_id(id) is not None

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(PetInstance.id)))
        return result.scalar_one()

    async def get_active_pet(self, player_id: str) -> Optional[PetInstance]:
        """获取玩家当前激活的伴侣"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_active == True
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_guarding_pet(self, player_id: str) -> Optional[PetInstance]:
        """获取玩家正在守田的宠物"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id,
            PetInstance.is_guarding == True
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_player(self, player_id: str) -> List[PetInstance]:
        """获取玩家所有宠物"""
        stmt = select(PetInstance).where(
            PetInstance.player_id == player_id
        ).order_by(PetInstance.created_at.desc())
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_player(self, player_id: str) -> int:
        """统计玩家宠物数量"""
        result = await self._session.execute(
            select(func.count(PetInstance.id)).where(PetInstance.player_id == player_id)
        )
        return result.scalar_one()
