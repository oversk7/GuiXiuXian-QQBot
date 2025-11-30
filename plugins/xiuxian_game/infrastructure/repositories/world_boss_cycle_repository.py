"""
世界BOSS周期仓储实现

提供世界BOSS周期（WorldBossCycle）的数据访问抽象
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ...domain.repositories.base import IRepository
from ...models.world_boss import WorldBossCycle


class WorldBossCycleRepository(IRepository[WorldBossCycle]):
    """世界BOSS周期仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化世界BOSS周期仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, cycle_id: int) -> Optional[WorldBossCycle]:
        """
        根据ID获取周期记录

        Args:
            cycle_id: 周期ID

        Returns:
            周期记录实例，不存在返回None
        """
        stmt = select(WorldBossCycle).where(WorldBossCycle.id == cycle_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_cycle_key(self, cycle_key: str) -> Optional[WorldBossCycle]:
        """
        根据周期键获取周期记录

        Args:
            cycle_key: 周期键（如"2025W10_SAT_20"）

        Returns:
            周期记录实例，不存在返回None

        对应原代码:
            world_boss/service.py Line 67（查询现有周期）
        """
        stmt = select(WorldBossCycle).where(WorldBossCycle.cycle_key == cycle_key)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_current_cycle(self) -> Optional[WorldBossCycle]:
        """
        获取当前最新的周期记录

        Returns:
            最新周期记录，不存在返回None

        对应原代码:
            world_boss/service.py Line 63-64（获取最新周期）
        """
        stmt = select(WorldBossCycle).order_by(WorldBossCycle.id.desc()).limit(1)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_cycle(
        self,
        cycle_key: str,
        boss_name: str,
        boss_title: str,
        next_refresh_at: datetime
    ) -> WorldBossCycle:
        """
        创建新的周期记录

        Args:
            cycle_key: 周期键
            boss_name: BOSS名称
            boss_title: BOSS称号
            next_refresh_at: 下次刷新时间

        Returns:
            创建的周期记录

        对应原代码:
            world_boss/service.py Line 74-81（创建新周期）
        """
        cycle = WorldBossCycle(
            cycle_key=cycle_key,
            boss_name=boss_name,
            boss_title=boss_title,
            next_refresh_at=next_refresh_at
        )
        self._session.add(cycle)
        await self._session.flush()  # 刷新以获取生成的ID
        return cycle

    async def mark_as_settled(self, cycle: WorldBossCycle) -> WorldBossCycle:
        """
        标记周期为已结算

        Args:
            cycle: 周期记录实例

        Returns:
            更新后的记录

        对应原代码:
            world_boss/service.py Line 96（标记结算）
        """
        cycle.settled = True
        self._session.add(cycle)
        return cycle

    async def add(self, cycle: WorldBossCycle) -> WorldBossCycle:
        """
        添加周期记录

        Args:
            cycle: 周期记录实例

        Returns:
            添加后的记录（包含生成的ID）
        """
        self._session.add(cycle)
        await self._session.flush()
        return cycle

    async def update(self, cycle: WorldBossCycle) -> WorldBossCycle:
        """
        更新周期记录

        Args:
            cycle: 周期记录实例

        Returns:
            更新后的记录
        """
        self._session.add(cycle)
        return cycle

    async def delete(self, cycle_id: int) -> bool:
        """
        删除周期记录

        Args:
            cycle_id: 周期ID

        Returns:
            是否成功删除
        """
        cycle = await self.get_by_id(cycle_id)
        if cycle:
            await self._session.delete(cycle)
            return True
        return False

    async def exists(self, cycle_id: int) -> bool:
        """
        检查周期记录是否存在

        Args:
            cycle_id: 周期ID

        Returns:
            是否存在
        """
        cycle = await self.get_by_id(cycle_id)
        return cycle is not None

    async def count(self) -> int:
        """
        获取周期记录总数

        Returns:
            记录总数
        """
        stmt = select(WorldBossCycle)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
