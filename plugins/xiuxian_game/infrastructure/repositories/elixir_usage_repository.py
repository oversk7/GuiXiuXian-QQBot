"""
丹药使用记录仓储实现
"""

from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date

from ...domain.repositories.base import IRepository
from ...models.elixir_usage import ElixirUsageLog


class ElixirUsageRepository(IRepository[ElixirUsageLog]):
    """丹药使用记录仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, record_id: int) -> Optional[ElixirUsageLog]:
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.id == record_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, record: ElixirUsageLog) -> ElixirUsageLog:
        self._session.add(record)
        await self._session.flush()
        return record

    async def update(self, record: ElixirUsageLog) -> ElixirUsageLog:
        self._session.add(record)
        return record

    async def delete(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        if record:
            await self._session.delete(record)
            return True
        return False

    async def exists(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        return record is not None

    async def count(self) -> int:
        # TODO: 实现
        return 0

    async def get_or_create_log(
        self, player_id: str, item_id: str, use_date: date = None
    ) -> ElixirUsageLog:
        """
        获取或创建当日使用记录（封装ElixirUsageLog.get_or_create_log）

        Args:
            player_id: 玩家ID
            item_id: 物品ID
            use_date: 使用日期（默认今天）

        Returns:
            ElixirUsageLog: 使用记录

        Note:
            此方法封装ElixirUsageLog.get_or_create_log类方法，保持向后兼容
        """
        return await ElixirUsageLog.get_or_create_log(
            self._session, player_id, item_id, use_date
        )

    async def get_player_usage_by_date(
        self, player_id: str, use_date: date = None
    ) -> List[ElixirUsageLog]:
        """
        获取玩家指定日期的所有丹药使用记录

        Args:
            player_id: 玩家ID
            use_date: 使用日期（默认今天）

        Returns:
            List[ElixirUsageLog]: 使用记录列表
        """
        if use_date is None:
            use_date = date.today()

        stmt = select(ElixirUsageLog).where(
            ElixirUsageLog.player_id == player_id,
            ElixirUsageLog.use_date == use_date
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_player_usage_by_item(
        self, player_id: str, item_id: str
    ) -> List[ElixirUsageLog]:
        """
        获取玩家指定物品的所有使用记录

        Args:
            player_id: 玩家ID
            item_id: 物品ID

        Returns:
            List[ElixirUsageLog]: 使用记录列表
        """
        stmt = select(ElixirUsageLog).where(
            ElixirUsageLog.player_id == player_id,
            ElixirUsageLog.item_id == item_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_player_usage(self, player_id: str) -> List[ElixirUsageLog]:
        """
        获取玩家所有丹药使用记录（不限日期）

        Args:
            player_id: 玩家ID

        Returns:
            List[ElixirUsageLog]: 所有使用记录列表

        Note:
            用于计算永久丹药加成，需要统计所有历史记录
        """
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
