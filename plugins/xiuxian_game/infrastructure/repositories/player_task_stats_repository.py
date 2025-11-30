"""
玩家任务统计仓储实现

提供玩家任务统计数据的数据访问抽象
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild_task_record import PlayerTaskStats


class PlayerTaskStatsRepository(IRepository[PlayerTaskStats]):
    """玩家任务统计仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化玩家任务统计仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, stats_id: int) -> Optional[PlayerTaskStats]:
        """
        根据ID获取统计记录

        Args:
            stats_id: 统计ID

        Returns:
            统计记录实例，不存在返回None
        """
        stmt = select(PlayerTaskStats).where(PlayerTaskStats.id == stats_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_player_id(self, player_id: str) -> Optional[PlayerTaskStats]:
        """
        根据玩家ID获取统计记录

        Args:
            player_id: 玩家ID

        Returns:
            统计记录实例，不存在返回None

        对应原代码:
            guild_task_service.py Line 73-74
        """
        stmt = select(PlayerTaskStats).where(PlayerTaskStats.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self, player_id: str) -> PlayerTaskStats:
        """
        获取或创建玩家任务统计

        Args:
            player_id: 玩家ID

        Returns:
            统计记录实例

        对应原代码:
            guild_task_service.py Line 71-96
        """
        stats = await self.get_by_player_id(player_id)

        if not stats:
            stats = PlayerTaskStats(
                player_id=player_id,
                total_explorations=0,
                total_combat_victories=0,
                total_commissions=0,
                today_explorations=0,
                today_combat_victories=0,
                today_commissions=0,
                week_commissions=0,
                week_daily_tasks=0
            )
            self._session.add(stats)
            await self._session.flush()  # 确保获得ID

        # 重置过期的统计数据
        stats.reset_daily_stats()
        stats.reset_weekly_stats()
        self._session.add(stats)

        return stats

    async def increment_exploration_stats(
        self, player_id: str, count: int = 1
    ) -> PlayerTaskStats:
        """
        增加探索统计

        Args:
            player_id: 玩家ID
            count: 增加数量

        Returns:
            更新后的统计记录

        对应原代码:
            guild_task_service.py Line 129-134
        """
        stats = await self.get_or_create(player_id)
        stats.total_explorations += count
        stats.today_explorations += count
        self._session.add(stats)
        return stats

    async def increment_combat_victory_stats(
        self, player_id: str, count: int = 1
    ) -> PlayerTaskStats:
        """
        增加战斗胜利统计

        Args:
            player_id: 玩家ID
            count: 增加数量

        Returns:
            更新后的统计记录

        对应原代码:
            guild_task_service.py Line 137-142
        """
        stats = await self.get_or_create(player_id)
        stats.total_combat_victories += count
        stats.today_combat_victories += count
        self._session.add(stats)
        return stats

    async def increment_commission_stats(
        self, player_id: str, count: int = 1
    ) -> PlayerTaskStats:
        """
        增加委托完成统计

        Args:
            player_id: 玩家ID
            count: 增加数量

        Returns:
            更新后的统计记录

        对应原代码:
            guild_task_service.py Line 145-151
        """
        stats = await self.get_or_create(player_id)
        stats.total_commissions += count
        stats.today_commissions += count
        stats.week_commissions += count
        self._session.add(stats)
        return stats

    async def increment_daily_task_completion(
        self, player_id: str
    ) -> PlayerTaskStats:
        """
        增加日常任务完成统计（用于周活跃任务）

        Args:
            player_id: 玩家ID

        Returns:
            更新后的统计记录

        对应原代码:
            guild_task_service.py Line 483-487
        """
        stats = await self.get_or_create(player_id)
        stats.week_daily_tasks += 1
        self._session.add(stats)
        return stats

    async def add(self, stats: PlayerTaskStats) -> PlayerTaskStats:
        """
        添加统计记录

        Args:
            stats: 统计记录实例

        Returns:
            添加后的记录（包含生成的ID）
        """
        self._session.add(stats)
        await self._session.flush()
        return stats

    async def update(self, stats: PlayerTaskStats) -> PlayerTaskStats:
        """
        更新统计记录

        Args:
            stats: 统计记录实例

        Returns:
            更新后的记录
        """
        self._session.add(stats)
        return stats

    async def delete(self, stats_id: int) -> bool:
        """
        删除统计记录

        Args:
            stats_id: 统计ID

        Returns:
            是否成功删除
        """
        stats = await self.get_by_id(stats_id)
        if stats:
            await self._session.delete(stats)
            return True
        return False

    async def exists(self, stats_id: int) -> bool:
        """
        检查统计记录是否存在

        Args:
            stats_id: 统计ID

        Returns:
            是否存在
        """
        stats = await self.get_by_id(stats_id)
        return stats is not None

    async def count(self) -> int:
        """
        获取统计记录总数

        Returns:
            记录总数
        """
        stmt = select(PlayerTaskStats)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
