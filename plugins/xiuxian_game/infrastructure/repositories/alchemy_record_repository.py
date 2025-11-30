"""
炼丹记录仓储实现

提供炼丹记录的数据访问抽象，支持查询、添加、删除操作
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.alchemy_task import AlchemyRecord


class AlchemyRecordRepository(IRepository[AlchemyRecord]):
    """炼丹记录仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化炼丹记录仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, record_id: int) -> Optional[AlchemyRecord]:
        """
        根据ID获取炼丹记录

        Args:
            record_id: 记录ID

        Returns:
            炼丹记录实例，不存在返回None
        """
        stmt = select(AlchemyRecord).where(AlchemyRecord.id == record_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_player_id(self, player_id: str) -> List[AlchemyRecord]:
        """
        获取玩家的所有炼丹记录

        Args:
            player_id: 玩家ID

        Returns:
            炼丹记录列表（按开始时间倒序排列）

        对应原代码:
            alchemy/service.py Line 224
        """
        stmt = (
            select(AlchemyRecord)
            .where(AlchemyRecord.player_id == player_id)
            .order_by(AlchemyRecord.started_at.desc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_claimable_by_player_id(
        self, player_id: str
    ) -> List[AlchemyRecord]:
        """
        获取玩家可领取的炼丹记录（已完成但未领取）

        Args:
            player_id: 玩家ID

        Returns:
            可领取的炼丹记录列表

        对应原代码:
            alchemy/__init__.py Line 130（筛选is_finished()且未领取的记录）

        Note:
            由于is_finished()是Python方法（基于datetime.now()），
            无法在SQL层面过滤，需要在应用层过滤
        """
        # 先查询所有未领取的记录
        stmt = (
            select(AlchemyRecord)
            .where(
                AlchemyRecord.player_id == player_id,
                AlchemyRecord.claimed == False
            )
            .order_by(AlchemyRecord.started_at.asc())
        )
        result = await self._session.execute(stmt)
        all_unclaimed = list(result.scalars().all())

        # 在应用层过滤已完成的记录
        return [record for record in all_unclaimed if record.is_finished()]

    async def add(self, record: AlchemyRecord) -> AlchemyRecord:
        """
        添加炼丹记录

        Args:
            record: 炼丹记录实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            alchemy/service.py Line 208
        """
        self._session.add(record)
        await self._session.flush()  # 刷新以获取生成的ID
        return record

    async def update(self, record: AlchemyRecord) -> AlchemyRecord:
        """
        更新炼丹记录

        Args:
            record: 炼丹记录实例

        Returns:
            更新后的记录
        """
        self._session.add(record)
        return record

    async def delete(self, record: AlchemyRecord) -> None:
        """
        删除炼丹记录

        Args:
            record: 炼丹记录实例

        对应原代码:
            alchemy/service.py Line 279
        """
        await self._session.delete(record)

    async def exists(self, record_id: int) -> bool:
        """
        检查炼丹记录是否存在

        Args:
            record_id: 记录ID

        Returns:
            是否存在
        """
        record = await self.get_by_id(record_id)
        return record is not None

    async def count(self) -> int:
        """
        获取炼丹记录总数

        Returns:
            记录总数
        """
        stmt = select(AlchemyRecord)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
