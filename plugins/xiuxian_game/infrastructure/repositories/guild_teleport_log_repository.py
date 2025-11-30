"""
公会传送日志仓储实现

提供公会传送记录的数据访问抽象
"""

from typing import Optional
from datetime import date, datetime
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild import GuildTeleportLog


class GuildTeleportLogRepository(IRepository[GuildTeleportLog]):
    """公会传送日志仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化公会传送日志仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, log_id: int) -> Optional[GuildTeleportLog]:
        """
        根据ID获取传送日志记录

        Args:
            log_id: 日志ID

        Returns:
            传送日志实例，不存在返回None
        """
        stmt = select(GuildTeleportLog).where(GuildTeleportLog.id == log_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_today_teleport_count(
        self, player_id: str, guild_id: int, today: date = None
    ) -> int:
        """
        获取玩家今日传送次数

        Args:
            player_id: 玩家ID
            guild_id: 公会ID
            today: 日期（默认今天）

        Returns:
            今日传送次数

        对应原代码:
            guild_facility_service.py Line 114-126
        """
        if today is None:
            today = date.today()

        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        stmt = select(func.count(GuildTeleportLog.id)).where(
            and_(
                GuildTeleportLog.player_id == player_id,
                GuildTeleportLog.guild_id == guild_id,
                GuildTeleportLog.teleported_at >= today_start,
                GuildTeleportLog.teleported_at <= today_end
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def add(self, teleport_log: GuildTeleportLog) -> GuildTeleportLog:
        """
        添加传送日志记录

        Args:
            teleport_log: 传送日志实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            guild_facility_service.py Line 158-166
        """
        self._session.add(teleport_log)
        await self._session.flush()  # 刷新以获取生成的ID
        return teleport_log

    async def update(self, teleport_log: GuildTeleportLog) -> GuildTeleportLog:
        """
        更新传送日志记录

        Args:
            teleport_log: 传送日志实例

        Returns:
            更新后的记录
        """
        self._session.add(teleport_log)
        return teleport_log

    async def delete(self, log_id: int) -> bool:
        """
        删除传送日志记录

        Args:
            log_id: 日志ID

        Returns:
            是否成功删除
        """
        teleport_log = await self.get_by_id(log_id)
        if teleport_log:
            await self._session.delete(teleport_log)
            return True
        return False

    async def exists(self, log_id: int) -> bool:
        """
        检查传送日志记录是否存在

        Args:
            log_id: 日志ID

        Returns:
            是否存在
        """
        teleport_log = await self.get_by_id(log_id)
        return teleport_log is not None

    async def count(self) -> int:
        """
        获取传送日志记录总数

        Returns:
            记录总数
        """
        stmt = select(GuildTeleportLog)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
