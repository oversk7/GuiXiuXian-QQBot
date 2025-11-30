"""
公会任务记录仓储实现

提供公会任务完成记录的数据访问抽象
"""

from typing import Optional
from datetime import date, timedelta
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild_task_record import GuildTaskRecord, GuildTaskType


class GuildTaskRecordRepository(IRepository[GuildTaskRecord]):
    """公会任务记录仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化公会任务记录仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, record_id: int) -> Optional[GuildTaskRecord]:
        """
        根据ID获取任务记录

        Args:
            record_id: 记录ID

        Returns:
            任务记录实例，不存在返回None
        """
        stmt = select(GuildTaskRecord).where(GuildTaskRecord.id == record_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def check_task_completed_today(
        self, player_id: str, task_type: GuildTaskType, today: date = None
    ) -> bool:
        """
        检查今日是否已完成指定任务

        Args:
            player_id: 玩家ID
            task_type: 任务类型
            today: 日期（默认今天）

        Returns:
            是否已完成

        对应原代码:
            guild_task_service.py Line 114-126
        """
        if today is None:
            today = date.today()

        stmt = select(func.count(GuildTaskRecord.id)).where(
            and_(
                GuildTaskRecord.player_id == player_id,
                GuildTaskRecord.task_type == task_type,
                GuildTaskRecord.task_date == today
            )
        )
        count = (await self._session.execute(stmt)).scalar_one()
        return count > 0

    async def check_task_completed_this_week(
        self, player_id: str, task_type: GuildTaskType, today: date = None
    ) -> bool:
        """
        检查本周是否已完成指定任务

        Args:
            player_id: 玩家ID
            task_type: 任务类型
            today: 日期（默认今天）

        Returns:
            是否已完成

        对应原代码:
            guild_task_service.py Line 390-406
        """
        if today is None:
            today = date.today()

        # 计算本周一的日期
        days_since_monday = today.weekday()
        monday = today - timedelta(days=days_since_monday)

        stmt = select(func.count(GuildTaskRecord.id)).where(
            and_(
                GuildTaskRecord.player_id == player_id,
                GuildTaskRecord.task_type == task_type,
                GuildTaskRecord.task_date >= monday
            )
        )
        count = (await self._session.execute(stmt)).scalar_one()
        return count > 0

    async def add(self, record: GuildTaskRecord) -> GuildTaskRecord:
        """
        添加任务完成记录

        Args:
            record: 任务记录实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            guild_task_service.py Line 102-111
        """
        self._session.add(record)
        await self._session.flush()  # 刷新以获取生成的ID
        return record

    async def update(self, record: GuildTaskRecord) -> GuildTaskRecord:
        """
        更新任务记录

        Args:
            record: 任务记录实例

        Returns:
            更新后的记录
        """
        self._session.add(record)
        return record

    async def delete(self, record_id: int) -> bool:
        """
        删除任务记录

        Args:
            record_id: 记录ID

        Returns:
            是否成功删除
        """
        record = await self.get_by_id(record_id)
        if record:
            await self._session.delete(record)
            return True
        return False

    async def exists(self, record_id: int) -> bool:
        """
        检查任务记录是否存在

        Args:
            record_id: 记录ID

        Returns:
            是否存在
        """
        record = await self.get_by_id(record_id)
        return record is not None

    async def count(self) -> int:
        """
        获取任务记录总数

        Returns:
            记录总数
        """
        stmt = select(GuildTaskRecord)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
