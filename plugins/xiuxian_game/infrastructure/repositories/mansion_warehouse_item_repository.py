"""
阴宅仓库物品仓储实现

提供玩家阴宅仓库物品的数据访问抽象
"""
from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.mansion_warehouse import MansionWarehouseItem


class MansionWarehouseItemRepository(IRepository[MansionWarehouseItem]):
    """阴宅仓库物品仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, item_id: int) -> Optional[MansionWarehouseItem]:
        stmt = select(MansionWarehouseItem).where(MansionWarehouseItem.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_player_id(self, player_id: str) -> List[MansionWarehouseItem]:
        """获取玩家仓库中所有物品堆叠（按存入时间升序）"""
        stmt = (
            select(MansionWarehouseItem)
            .where(MansionWarehouseItem.player_id == player_id)
            .order_by(MansionWarehouseItem.deposited_at)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_player_and_item_id(self, player_id: str, item_id: str) -> List[MansionWarehouseItem]:
        """获取玩家仓库中指定物品的所有堆叠（按ID升序，用于存入时填满）"""
        stmt = (
            select(MansionWarehouseItem)
            .where(and_(
                MansionWarehouseItem.player_id == player_id,
                MansionWarehouseItem.item_id == item_id
            ))
            .order_by(MansionWarehouseItem.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_player_and_item_id_desc(self, player_id: str, item_id: str) -> List[MansionWarehouseItem]:
        """获取玩家仓库中指定物品的所有堆叠（按存入时间降序，用于取出时优先取最新）"""
        stmt = (
            select(MansionWarehouseItem)
            .where(and_(
                MansionWarehouseItem.player_id == player_id,
                MansionWarehouseItem.item_id == item_id
            ))
            .order_by(MansionWarehouseItem.deposited_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_slots_count(self, player_id: str) -> int:
        """获取玩家仓库当前占用的总堆叠数（格子数）"""
        stmt = select(func.count(MansionWarehouseItem.id)).where(
            MansionWarehouseItem.player_id == player_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def add(self, item: MansionWarehouseItem) -> MansionWarehouseItem:
        self._session.add(item)
        await self._session.flush()
        return item

    async def update(self, item: MansionWarehouseItem) -> MansionWarehouseItem:
        self._session.add(item)
        return item

    async def delete(self, item_id: int) -> bool:
        item = await self.get_by_id(item_id)
        if item:
            await self._session.delete(item)
            return True
        return False

    async def exists(self, item_id: int) -> bool:
        item = await self.get_by_id(item_id)
        return item is not None

    async def count(self) -> int:
        stmt = select(func.count(MansionWarehouseItem.id))
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0
