"""
红包仓储

提供RedEnvelope实体的数据访问层，支持：
1. 群内活跃红包查询
2. 过期红包批量查询
3. 最近红包记录查询
"""

from typing import Optional, List
from datetime import datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.red_envelope import RedEnvelope, RedEnvelopeStatus


class RedEnvelopeRepository(IRepository[RedEnvelope]):
    """红包仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    # ==================== 基础CRUD ====================

    async def get_by_id(self, entity_id: int) -> Optional[RedEnvelope]:
        return await self._session.get(RedEnvelope, entity_id)

    async def add(self, entity: RedEnvelope) -> RedEnvelope:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: RedEnvelope) -> RedEnvelope:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity_id: int) -> bool:
        entity = await self.get_by_id(entity_id)
        if entity:
            await self._session.delete(entity)
            await self._session.flush()
            return True
        return False

    async def exists(self, entity_id: int) -> bool:
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        from sqlalchemy import func
        stmt = select(func.count()).select_from(RedEnvelope)
        result = await self._session.execute(stmt)
        return result.scalar()

    # ==================== 业务查询 ====================

    async def find_active_by_group(self, group_id: str) -> Optional[RedEnvelope]:
        """查找群内活跃红包"""
        stmt = select(RedEnvelope).where(
            and_(
                RedEnvelope.group_id == group_id,
                RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def find_expired_envelopes(self) -> List[RedEnvelope]:
        """查找已过期但状态仍为ACTIVE的红包"""
        now = datetime.now()
        stmt = select(RedEnvelope).where(
            and_(
                RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value,
                RedEnvelope.expires_at < now
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_recent_by_group(self, group_id: str, limit: int = 5) -> List[RedEnvelope]:
        """查找群内最近红包记录"""
        stmt = (
            select(RedEnvelope)
            .where(RedEnvelope.group_id == group_id)
            .order_by(RedEnvelope.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
