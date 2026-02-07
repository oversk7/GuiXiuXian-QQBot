"""
里界探索会话仓储实现
"""
from sqlalchemy import select, and_, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from typing import Optional, List
from datetime import datetime

from ...domain.repositories.base import IRepository
from ...models.inner_realm import InnerRealmSession


class InnerRealmSessionRepository(IRepository[InnerRealmSession]):
    """
    里界探索会话仓储

    提供里界会话数据访问层,包括:
    - 标准CRUD操作
    - 获取玩家的活跃会话
    - 预加载地块数据
    - 会话重置和清理
    """

    def __init__(self, session: AsyncSession):
        """
        初始化仓储

        Args:
            session: SQLAlchemy异步会话
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, session_id: int) -> Optional[InnerRealmSession]:
        """
        根据ID获取会话

        Args:
            session_id: 会话ID

        Returns:
            会话对象,不存在则返回None
        """
        return await self._session.get(InnerRealmSession, session_id)

    async def add(self, entity: InnerRealmSession) -> InnerRealmSession:
        """
        添加新会话

        Args:
            entity: 会话对象

        Returns:
            添加后的会话对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: InnerRealmSession) -> InnerRealmSession:
        """
        更新会话

        Args:
            entity: 会话对象

        Returns:
            更新后的会话对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, session_id: int) -> bool:
        """
        删除会话

        Args:
            session_id: 会话ID

        Returns:
            是否删除成功
        """
        session = await self.get_by_id(session_id)
        if session:
            await self._session.delete(session)
            await self._session.flush()
            return True
        return False

    async def exists(self, session_id: int) -> bool:
        """
        检查会话是否存在

        Args:
            session_id: 会话ID

        Returns:
            是否存在
        """
        result = await self._session.execute(
            select(InnerRealmSession.id).where(InnerRealmSession.id == session_id)
        )
        return result.scalar_one_or_none() is not None

    async def count(self) -> int:
        """
        获取会话总数

        Returns:
            会话数量
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(InnerRealmSession.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_active_session(
        self, player_id: str, realm_name: str
    ) -> Optional[InnerRealmSession]:
        """
        获取玩家在指定里界的活跃会话

        Args:
            player_id: 玩家ID
            realm_name: 里界名称

        Returns:
            会话对象,不存在则返回None
        """
        stmt = select(InnerRealmSession).where(
            and_(
                InnerRealmSession.player_id == player_id,
                InnerRealmSession.realm_name == realm_name,
                InnerRealmSession.is_settled == False
            )
        ).options(selectinload(InnerRealmSession.tiles))

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_with_tiles(self, session_id: int) -> Optional[InnerRealmSession]:
        """
        获取会话并预加载地块数据

        Args:
            session_id: 会话ID

        Returns:
            会话对象(含地块),不存在则返回None
        """
        stmt = select(InnerRealmSession).where(
            InnerRealmSession.id == session_id
        ).options(selectinload(InnerRealmSession.tiles))

        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_player_sessions(
        self, player_id: str, include_settled: bool = False
    ) -> List[InnerRealmSession]:
        """
        获取玩家的所有会话

        Args:
            player_id: 玩家ID
            include_settled: 是否包含已结算的会话

        Returns:
            会话列表
        """
        conditions = [InnerRealmSession.player_id == player_id]
        if not include_settled:
            conditions.append(InnerRealmSession.is_settled == False)

        stmt = select(InnerRealmSession).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_old_sessions(self, before_date: datetime) -> int:
        """
        删除指定日期之前的旧会话

        Args:
            before_date: 截止日期

        Returns:
            删除的会话数量
        """
        stmt = sql_delete(InnerRealmSession).where(
            and_(
                InnerRealmSession.is_settled == True,
                InnerRealmSession.entered_at < before_date
            )
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def get_sessions_need_refresh(
        self, before_date: datetime
    ) -> List[InnerRealmSession]:
        """
        获取需要刷新的会话(last_refresh早于指定日期)

        Args:
            before_date: 刷新截止时间

        Returns:
            需要刷新的会话列表
        """
        stmt = select(InnerRealmSession).where(
            and_(
                InnerRealmSession.is_settled == False,
                InnerRealmSession.last_refresh < before_date
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
