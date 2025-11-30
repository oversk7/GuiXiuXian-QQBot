"""
PlayerJobStatsRepository - 玩家打工统计数据访问层

提供玩家打工统计相关的数据库操作
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models.part_time_job import PlayerJobStats
from ..domain.repositories.base import IRepository


class PlayerJobStatsRepository(IRepository[PlayerJobStats]):
    """玩家打工统计仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[PlayerJobStats]:
        """根据ID获取玩家打工统计"""
        return await self._session.get(PlayerJobStats, entity_id)

    async def add(self, entity: PlayerJobStats) -> PlayerJobStats:
        """添加玩家打工统计"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: PlayerJobStats) -> PlayerJobStats:
        """更新玩家打工统计"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: PlayerJobStats):
        """删除玩家打工统计"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[PlayerJobStats]:
        """列出所有玩家打工统计"""
        stmt = select(PlayerJobStats)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计记录数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(PlayerJobStats)
        result = await self._session.execute(stmt)
        return result.scalar()

    # ==================== 玩家打工统计特定方法 ====================

    async def get_by_player_id(self, player_id: str) -> Optional[PlayerJobStats]:
        """
        根据玩家ID获取打工统计

        Args:
            player_id: 玩家ID

        Returns:
            玩家打工统计对象，如果不存在则返回None
        """
        stmt = select(PlayerJobStats).where(PlayerJobStats.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_or_create(self, player_id: str) -> PlayerJobStats:
        """
        获取或创建玩家打工统计

        Args:
            player_id: 玩家ID

        Returns:
            玩家打工统计对象
        """
        stats = await self.get_by_player_id(player_id)
        if not stats:
            stats = PlayerJobStats(
                player_id=player_id,
                total_jobs_completed=0,
                total_earnings=0,
                total_work_hours=0,
                current_streak=0,
                max_streak=0,
                achievements={}
            )
            stats = await self.add(stats)
        return stats

    async def update_job_completion(
        self,
        player_id: str,
        earnings: int,
        work_hours: float,
        work_date: datetime
    ) -> PlayerJobStats:
        """
        更新玩家完成工作的统计

        Args:
            player_id: 玩家ID
            earnings: 本次收入
            work_hours: 本次工作小时数
            work_date: 工作日期

        Returns:
            更新后的统计对象
        """
        stats = await self.get_or_create(player_id)

        stats.total_jobs_completed += 1
        stats.total_earnings += earnings
        stats.total_work_hours += work_hours
        stats.update_streak(work_date)

        await self.update(stats)
        return stats

    async def get_top_earners(self, limit: int = 10) -> List[PlayerJobStats]:
        """
        获取收入排行榜

        Args:
            limit: 返回记录数量限制

        Returns:
            按总收入排序的玩家统计列表
        """
        stmt = (
            select(PlayerJobStats)
            .order_by(PlayerJobStats.total_earnings.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_top_workers(self, limit: int = 10) -> List[PlayerJobStats]:
        """
        获取工作量排行榜

        Args:
            limit: 返回记录数量限制

        Returns:
            按完成工作数排序的玩家统计列表
        """
        stmt = (
            select(PlayerJobStats)
            .order_by(PlayerJobStats.total_jobs_completed.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_top_streaks(self, limit: int = 10) -> List[PlayerJobStats]:
        """
        获取连续工作排行榜

        Args:
            limit: 返回记录数量限制

        Returns:
            按最大连续天数排序的玩家统计列表
        """
        stmt = (
            select(PlayerJobStats)
            .order_by(PlayerJobStats.max_streak.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
