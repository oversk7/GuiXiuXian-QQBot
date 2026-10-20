"""
红包仓储

提供RedEnvelope实体的数据访问层，支持：
1. 群内活跃红包查询
2. 领取记录汇总
3. 最近红包记录查询
"""

from typing import Optional, List, Tuple
from datetime import datetime
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.red_envelope import RedEnvelope, RedEnvelopeGrab, RedEnvelopeStatus


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

    def _active_by_group_stmt(self, group_id: str, server_id: int):
        now = datetime.now()
        return select(RedEnvelope).where(
            and_(
                RedEnvelope.server_id == server_id,
                RedEnvelope.group_id == group_id,
                RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value,
                RedEnvelope.expires_at > now
            )
        )

    async def find_active_by_group(self, group_id: str, server_id: int) -> Optional[RedEnvelope]:
        """查找群内活跃红包（排除已过期但状态未及时更新的僵尸红包）"""
        result = await self._session.execute(self._active_by_group_stmt(group_id, server_id))
        return result.scalars().first()

    async def find_active_by_group_for_update(
        self,
        group_id: str,
        server_id: int,
    ) -> Optional[RedEnvelope]:
        """锁定并查找群内活跃红包，避免并发领取或重复创建。"""
        stmt = self._active_by_group_stmt(group_id, server_id).with_for_update()
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def grab_summary(self, envelope_id: int) -> Tuple[int, Optional[RedEnvelopeGrab]]:
        """已入账的领取人数和手气最佳的一条记录。"""
        count = await self._session.scalar(
            select(func.count()).select_from(RedEnvelopeGrab)
            .where(RedEnvelopeGrab.envelope_id == envelope_id)
        )
        best = await self._session.scalar(
            select(RedEnvelopeGrab)
            .where(RedEnvelopeGrab.envelope_id == envelope_id)
            .order_by(RedEnvelopeGrab.amount.desc(), RedEnvelopeGrab.id)
            .limit(1)
        )
        return int(count or 0), best

    async def find_recent_by_group(self, group_id: str, server_id: int, limit: int = 5) -> List[RedEnvelope]:
        """查找群内最近红包记录"""
        stmt = (
            select(RedEnvelope)
            .where(
                and_(
                    RedEnvelope.group_id == group_id,
                    RedEnvelope.server_id == server_id
                )
            )
            .order_by(RedEnvelope.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
