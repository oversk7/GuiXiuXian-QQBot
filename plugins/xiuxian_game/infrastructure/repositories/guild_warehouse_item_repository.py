"""
公会仓库物品仓储实现

提供公会仓库物品的数据访问抽象
"""

from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild import GuildWarehouseItem


class GuildWarehouseItemRepository(IRepository[GuildWarehouseItem]):
    """公会仓库物品仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化公会仓库物品仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, item_id: int) -> Optional[GuildWarehouseItem]:
        """
        根据ID获取仓库物品记录

        Args:
            item_id: 仓库物品ID

        Returns:
            仓库物品实例，不存在返回None
        """
        stmt = select(GuildWarehouseItem).where(GuildWarehouseItem.id == item_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_guild_id(
        self, guild_id: int
    ) -> List[GuildWarehouseItem]:
        """
        获取公会仓库所有物品

        Args:
            guild_id: 公会ID

        Returns:
            仓库物品列表（按存入时间降序）

        对应原代码:
            guild_facility_service.py Line 410
        """
        stmt = select(GuildWarehouseItem).where(
            GuildWarehouseItem.guild_id == guild_id
        ).order_by(GuildWarehouseItem.deposited_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_guild_and_item_id(
        self, guild_id: int, item_id: str
    ) -> List[GuildWarehouseItem]:
        """
        获取公会仓库中指定物品ID的所有堆叠

        Args:
            guild_id: 公会ID
            item_id: 物品ID

        Returns:
            仓库物品堆叠列表（按ID升序）

        对应原代码:
            guild_facility_service.py Line 469-472
        """
        stmt = select(GuildWarehouseItem).where(
            and_(
                GuildWarehouseItem.guild_id == guild_id,
                GuildWarehouseItem.item_id == item_id
            )
        ).order_by(GuildWarehouseItem.id)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_guild_and_item_id_desc(
        self, guild_id: int, item_id: str
    ) -> List[GuildWarehouseItem]:
        """
        获取公会仓库中指定物品ID的所有堆叠（按存入时间降序）

        Args:
            guild_id: 公会ID
            item_id: 物品ID

        Returns:
            仓库物品堆叠列表（按存入时间降序）

        对应原代码:
            guild_facility_service.py Line 547-549

        Note:
            用于取出物品时，优先取出最新存入的
        """
        stmt = select(GuildWarehouseItem).where(
            and_(
                GuildWarehouseItem.guild_id == guild_id,
                GuildWarehouseItem.item_id == item_id
            )
        ).order_by(GuildWarehouseItem.deposited_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_total_slots_count(self, guild_id: int) -> int:
        """
        获取公会仓库当前占用的总格子数

        Args:
            guild_id: 公会ID

        Returns:
            当前占用格子数

        对应原代码:
            guild_facility_service.py Line 484-485
        """
        stmt = select(func.count(GuildWarehouseItem.id)).where(
            GuildWarehouseItem.guild_id == guild_id
        )
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0

    async def add(self, warehouse_item: GuildWarehouseItem) -> GuildWarehouseItem:
        """
        添加仓库物品记录

        Args:
            warehouse_item: 仓库物品实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            guild_facility_service.py Line 515-522
        """
        self._session.add(warehouse_item)
        await self._session.flush()  # 刷新以获取生成的ID
        return warehouse_item

    async def update(self, warehouse_item: GuildWarehouseItem) -> GuildWarehouseItem:
        """
        更新仓库物品记录

        Args:
            warehouse_item: 仓库物品实例

        Returns:
            更新后的记录

        对应原代码:
            guild_facility_service.py Line 508-510
        """
        self._session.add(warehouse_item)
        return warehouse_item

    async def delete(self, item_id: int) -> bool:
        """
        删除仓库物品记录

        Args:
            item_id: 仓库物品ID

        Returns:
            是否成功删除

        对应原代码:
            guild_facility_service.py Line 563
        """
        warehouse_item = await self.get_by_id(item_id)
        if warehouse_item:
            await self._session.delete(warehouse_item)
            return True
        return False

    async def exists(self, item_id: int) -> bool:
        """
        检查仓库物品记录是否存在

        Args:
            item_id: 仓库物品ID

        Returns:
            是否存在
        """
        warehouse_item = await self.get_by_id(item_id)
        return warehouse_item is not None

    async def count(self) -> int:
        """
        获取仓库物品记录总数

        Returns:
            记录总数
        """
        stmt = select(GuildWarehouseItem)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
