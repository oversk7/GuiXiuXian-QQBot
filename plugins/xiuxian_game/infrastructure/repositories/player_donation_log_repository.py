"""
玩家捐献日志仓储实现

提供玩家每日捐献记录的数据访问抽象
"""

from typing import Optional
from datetime import date
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.donation_log import PlayerDonationLog


class PlayerDonationLogRepository(IRepository[PlayerDonationLog]):
    """玩家捐献日志仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化玩家捐献日志仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, log_id: int) -> Optional[PlayerDonationLog]:
        """
        根据ID获取捐献日志记录

        Args:
            log_id: 日志ID

        Returns:
            捐献日志实例，不存在返回None
        """
        stmt = select(PlayerDonationLog).where(PlayerDonationLog.id == log_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_today_donation_amount(
        self, player_id: str, today: date = None
    ) -> int:
        """
        获取玩家今日捐献总金额

        Args:
            player_id: 玩家ID
            today: 日期（默认今天）

        Returns:
            今日捐献总金额

        对应原代码:
            guild_economy_service.py Line 54-59
        """
        if today is None:
            today = date.today()

        stmt = select(func.coalesce(func.sum(PlayerDonationLog.amount), 0)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def count_today_donations(
        self, player_id: str, today: date = None
    ) -> int:
        """
        获取玩家今日捐献记录数量

        Args:
            player_id: 玩家ID
            today: 日期（默认今天）

        Returns:
            今日捐献记录数量

        对应原代码:
            guild_task_service.py Line 258-262
        """
        if today is None:
            today = date.today()

        stmt = select(func.count(PlayerDonationLog.id)).where(
            PlayerDonationLog.player_id == player_id,
            PlayerDonationLog.donate_date == today
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def add(self, donation_log: PlayerDonationLog) -> PlayerDonationLog:
        """
        添加捐献日志记录

        Args:
            donation_log: 捐献日志实例

        Returns:
            添加后的记录（ID在事务提交时生成）

        对应原代码:
            guild_economy_service.py Line 94-99
        """
        self._session.add(donation_log)
        return donation_log

    async def update(self, donation_log: PlayerDonationLog) -> PlayerDonationLog:
        """
        更新捐献日志记录

        Args:
            donation_log: 捐献日志实例

        Returns:
            更新后的记录
        """
        self._session.add(donation_log)
        return donation_log

    async def delete(self, log_id: int) -> bool:
        """
        删除捐献日志记录

        Args:
            log_id: 日志ID

        Returns:
            是否成功删除
        """
        donation_log = await self.get_by_id(log_id)
        if donation_log:
            await self._session.delete(donation_log)
            return True
        return False

    async def exists(self, log_id: int) -> bool:
        """
        检查捐献日志记录是否存在

        Args:
            log_id: 日志ID

        Returns:
            是否存在
        """
        donation_log = await self.get_by_id(log_id)
        return donation_log is not None

    async def count(self) -> int:
        """
        获取捐献日志记录总数

        Returns:
            记录总数
        """
        stmt = select(PlayerDonationLog)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
