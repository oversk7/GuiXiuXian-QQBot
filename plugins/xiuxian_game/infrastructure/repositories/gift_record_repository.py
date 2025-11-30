"""
礼物记录仓储实现

提供礼物记录的数据访问抽象，支持查询、添加、删除操作
"""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.gift_record import GiftRecord


class GiftRecordRepository(IRepository[GiftRecord]):
    """礼物记录仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化礼物记录仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础CRUD方法 ====================

    async def get_by_id(self, record_id: int) -> Optional[GiftRecord]:
        """
        根据ID获取礼物记录

        Args:
            record_id: 记录ID

        Returns:
            礼物记录实例，不存在返回None
        """
        return await self._session.get(GiftRecord, record_id)

    async def add(self, gift_record: GiftRecord) -> GiftRecord:
        """
        添加礼物记录

        Args:
            gift_record: 礼物记录实例

        Returns:
            添加后的记录（包含生成的ID）
        """
        self._session.add(gift_record)
        await self._session.flush()
        return gift_record

    async def update(self, gift_record: GiftRecord) -> GiftRecord:
        """
        更新礼物记录

        Args:
            gift_record: 礼物记录实例

        Returns:
            更新后的记录
        """
        self._session.add(gift_record)
        await self._session.flush()
        return gift_record

    async def delete(self, record_id: int) -> bool:
        """
        删除礼物记录

        Args:
            record_id: 记录ID

        Returns:
            是否删除成功
        """
        gift_record = await self.get_by_id(record_id)
        if not gift_record:
            return False
        await self._session.delete(gift_record)
        await self._session.flush()
        return True

    async def exists(self, record_id: int) -> bool:
        """
        检查礼物记录是否存在

        Args:
            record_id: 记录ID

        Returns:
            是否存在
        """
        gift_record = await self.get_by_id(record_id)
        return gift_record is not None

    async def count(self) -> int:
        """
        获取礼物记录总数

        Returns:
            记录总数
        """
        from sqlalchemy import func
        stmt = select(func.count(GiftRecord.id))
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    # ==================== 业务查询方法 ====================

    async def get_gift_history(self, player_id: str, limit: int = 10) -> List[GiftRecord]:
        """
        获取玩家的送礼历史（发送者视角）

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            礼物记录列表，按时间倒序排列
        """
        stmt = (
            select(GiftRecord)
            .where(GiftRecord.sender_id == player_id)
            .order_by(GiftRecord.sent_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_received_gifts(self, player_id: str, limit: int = 10) -> List[GiftRecord]:
        """
        获取玩家收到的礼物历史（接收者视角）

        Args:
            player_id: 玩家ID
            limit: 返回记录数量限制

        Returns:
            礼物记录列表，按时间倒序排列
        """
        stmt = (
            select(GiftRecord)
            .where(GiftRecord.receiver_id == player_id)
            .order_by(GiftRecord.sent_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
