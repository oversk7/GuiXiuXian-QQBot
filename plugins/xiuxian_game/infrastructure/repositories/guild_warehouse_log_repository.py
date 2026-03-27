"""
公会仓库操作日志仓储实现

提供公会仓库存取记录的数据访问抽象
"""

from typing import List
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild import GuildWarehouseLog


class GuildWarehouseLogRepository(IRepository[GuildWarehouseLog]):
    """公会仓库操作日志仓储实现"""

    # 每个公会最多保留的日志条数
    MAX_LOGS_PER_GUILD = 50

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, log_id: int):
        stmt = select(GuildWarehouseLog).where(GuildWarehouseLog.id == log_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_by_guild(
        self, guild_id: int, limit: int = 20
    ) -> List[GuildWarehouseLog]:
        """
        获取公会最近的仓库操作日志

        Args:
            guild_id: 公会ID
            limit: 返回条数，默认20

        Returns:
            日志列表（按时间降序）
        """
        stmt = (
            select(GuildWarehouseLog)
            .where(GuildWarehouseLog.guild_id == guild_id)
            .order_by(GuildWarehouseLog.operated_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, log: GuildWarehouseLog) -> GuildWarehouseLog:
        self._session.add(log)
        await self._session.flush()
        return log

    async def cleanup_old_logs(self, guild_id: int) -> int:
        """
        清理超出上限的旧日志，保留最近 MAX_LOGS_PER_GUILD 条

        Args:
            guild_id: 公会ID

        Returns:
            删除的记录数
        """
        # 先统计总数
        count_stmt = select(func.count(GuildWarehouseLog.id)).where(
            GuildWarehouseLog.guild_id == guild_id
        )
        result = await self._session.execute(count_stmt)
        total = result.scalar_one() or 0

        if total <= self.MAX_LOGS_PER_GUILD:
            return 0

        # 找到要保留的最小ID（按时间降序取前N条中的最小ID）
        keep_stmt = (
            select(GuildWarehouseLog.id)
            .where(GuildWarehouseLog.guild_id == guild_id)
            .order_by(GuildWarehouseLog.operated_at.desc())
            .limit(self.MAX_LOGS_PER_GUILD)
        )
        keep_result = await self._session.execute(keep_stmt)
        keep_ids = [row[0] for row in keep_result.all()]

        if not keep_ids:
            return 0

        # 删除不在保留列表中的记录
        delete_stmt = delete(GuildWarehouseLog).where(
            GuildWarehouseLog.guild_id == guild_id,
            GuildWarehouseLog.id.notin_(keep_ids)
        )
        delete_result = await self._session.execute(delete_stmt)
        return delete_result.rowcount

    async def update(self, log: GuildWarehouseLog) -> GuildWarehouseLog:
        self._session.add(log)
        return log

    async def delete(self, log_id: int) -> bool:
        log = await self.get_by_id(log_id)
        if log:
            await self._session.delete(log)
            return True
        return False

    async def exists(self, log_id: int) -> bool:
        return await self.get_by_id(log_id) is not None

    async def count(self) -> int:
        stmt = select(func.count(GuildWarehouseLog.id))
        result = await self._session.execute(stmt)
        return result.scalar_one() or 0
