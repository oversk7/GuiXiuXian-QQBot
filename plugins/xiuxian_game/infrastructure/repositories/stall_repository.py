"""摊位系统 Repository"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.stall import PlayerStall, StallItem


class PlayerStallRepository:
    """玩家摊位仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, stall_id: int) -> Optional[PlayerStall]:
        return await self._session.get(PlayerStall, stall_id)

    async def get_active_by_player(self, player_id: str) -> Optional[PlayerStall]:
        """获取玩家当前活跃摊位"""
        stmt = select(PlayerStall).where(
            PlayerStall.player_id == player_id,
            PlayerStall.status == "active",
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_active_by_city(self, city_name: str, page: int = 1, page_size: int = 8) -> List[PlayerStall]:
        """查询某城镇的活跃摊位（分页）"""
        stmt = (
            select(PlayerStall)
            .where(PlayerStall.status == "active", PlayerStall.city_name == city_name)
            .order_by(PlayerStall.opened_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_active_by_city(self, city_name: str) -> int:
        stmt = select(func.count()).select_from(PlayerStall).where(
            PlayerStall.status == "active", PlayerStall.city_name == city_name
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def find_all_active(self, page: int = 1, page_size: int = 8) -> List[PlayerStall]:
        """查询所有活跃摊位（分页）"""
        stmt = (
            select(PlayerStall)
            .where(PlayerStall.status == "active")
            .order_by(PlayerStall.opened_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_all_active(self) -> int:
        stmt = select(func.count()).select_from(PlayerStall).where(
            PlayerStall.status == "active"
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def find_expired_active(self) -> List[PlayerStall]:
        """查找已过期但仍为active状态的摊位"""
        stmt = select(PlayerStall).where(
            PlayerStall.status == "active",
            PlayerStall.expires_at <= datetime.now(),
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, entity: PlayerStall) -> PlayerStall:
        self._session.add(entity)
        await self._session.flush()
        return entity


class StallItemRepository:
    """摊位商品仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, item_id: int) -> Optional[StallItem]:
        return await self._session.get(StallItem, item_id)

    async def find_by_stall(self, stall_id: int) -> List[StallItem]:
        """获取摊位上所有商品"""
        stmt = select(StallItem).where(
            StallItem.stall_id == stall_id
        ).order_by(StallItem.listed_at.asc())
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_stall(self, stall_id: int) -> int:
        stmt = select(func.count()).select_from(StallItem).where(
            StallItem.stall_id == stall_id
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def search_by_item_id(self, item_id: str, page: int = 1, page_size: int = 10) -> List[StallItem]:
        """跨摊位搜索特定物品（按单价升序），仅搜索active摊位"""
        stmt = (
            select(StallItem)
            .join(PlayerStall, StallItem.stall_id == PlayerStall.id)
            .where(
                StallItem.item_id == item_id,
                PlayerStall.status == "active",
            )
            .order_by(StallItem.unit_price.asc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def count_by_item_id(self, item_id: str) -> int:
        stmt = (
            select(func.count())
            .select_from(StallItem)
            .join(PlayerStall, StallItem.stall_id == PlayerStall.id)
            .where(
                StallItem.item_id == item_id,
                PlayerStall.status == "active",
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def add(self, entity: StallItem) -> StallItem:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: StallItem):
        await self._session.delete(entity)
        await self._session.flush()

    async def delete_all_by_stall(self, stall_id: int) -> List[StallItem]:
        """删除摊位所有商品并返回（用于退回物品）"""
        items = await self.find_by_stall(stall_id)
        for item in items:
            await self._session.delete(item)
        await self._session.flush()
        return items
