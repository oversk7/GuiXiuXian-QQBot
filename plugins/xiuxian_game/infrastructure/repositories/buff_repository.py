"""
临时Buff仓储实现（占位符）

TODO: 完整实现
"""

from typing import Optional, List
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ...domain.repositories.base import IRepository
from ...models.temporary_buff import TemporaryBuff


class BuffRepository(IRepository[TemporaryBuff]):
    """临时Buff仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, buff_id: str) -> Optional[TemporaryBuff]:
        stmt = select(TemporaryBuff).where(TemporaryBuff.id == buff_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_active_buffs(self, player_id: str) -> List[TemporaryBuff]:
        """获取玩家激活的buff（未过期）"""
        stmt = select(TemporaryBuff).where(
            and_(
                TemporaryBuff.player_id == player_id,
                TemporaryBuff.expires_at > datetime.now()
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def add(self, buff: TemporaryBuff) -> TemporaryBuff:
        self._session.add(buff)
        await self._session.flush()
        return buff

    async def update(self, buff: TemporaryBuff) -> TemporaryBuff:
        self._session.add(buff)
        return buff

    async def delete(self, buff_id: str) -> bool:
        buff = await self.get_by_id(buff_id)
        if buff:
            await self._session.delete(buff)
            return True
        return False

    async def exists(self, buff_id: str) -> bool:
        buff = await self.get_by_id(buff_id)
        return buff is not None

    async def count(self) -> int:
        # TODO: 实现
        return 0

    async def cleanup_expired(self, player_id: str) -> int:
        """清理过期的buff"""
        stmt = select(TemporaryBuff).where(
            and_(
                TemporaryBuff.player_id == player_id,
                TemporaryBuff.expires_at <= datetime.now()
            )
        )
        result = await self._session.execute(stmt)
        expired_buffs = result.scalars().all()

        for buff in expired_buffs:
            await self._session.delete(buff)

        return len(expired_buffs)
