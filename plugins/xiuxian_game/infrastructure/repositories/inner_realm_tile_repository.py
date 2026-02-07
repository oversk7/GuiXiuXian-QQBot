"""
里界地块仓储实现
"""
from sqlalchemy import select, and_, delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional, List

from ...domain.repositories.base import IRepository
from ...models.inner_realm import InnerRealmTile


class InnerRealmTileRepository(IRepository[InnerRealmTile]):
    """
    里界地块仓储

    提供里界地块数据访问层,包括:
    - 标准CRUD操作
    - 按坐标查询地块
    - 获取会话的所有地块
    - 按事件类型筛选
    """

    def __init__(self, session: AsyncSession):
        """
        初始化仓储

        Args:
            session: SQLAlchemy异步会话
        """
        self._session = session

    # ==================== 标准CRUD操作 ====================

    async def get_by_id(self, tile_id: int) -> Optional[InnerRealmTile]:
        """
        根据ID获取地块

        Args:
            tile_id: 地块ID

        Returns:
            地块对象,不存在则返回None
        """
        return await self._session.get(InnerRealmTile, tile_id)

    async def add(self, entity: InnerRealmTile) -> InnerRealmTile:
        """
        添加新地块

        Args:
            entity: 地块对象

        Returns:
            添加后的地块对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: InnerRealmTile) -> InnerRealmTile:
        """
        更新地块

        Args:
            entity: 地块对象

        Returns:
            更新后的地块对象
        """
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, tile_id: int) -> bool:
        """
        删除地块

        Args:
            tile_id: 地块ID

        Returns:
            是否删除成功
        """
        tile = await self.get_by_id(tile_id)
        if tile:
            await self._session.delete(tile)
            await self._session.flush()
            return True
        return False

    async def exists(self, tile_id: int) -> bool:
        """
        检查地块是否存在

        Args:
            tile_id: 地块ID

        Returns:
            是否存在
        """
        result = await self._session.execute(
            select(InnerRealmTile.id).where(InnerRealmTile.id == tile_id)
        )
        return result.scalar_one_or_none() is not None

    async def count(self) -> int:
        """
        获取地块总数

        Returns:
            地块数量
        """
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(InnerRealmTile.id))
        )
        return result.scalar_one()

    # ==================== 领域查询方法 ====================

    async def get_by_position(
        self, session_id: int, x: int, y: int
    ) -> Optional[InnerRealmTile]:
        """
        按坐标获取地块

        Args:
            session_id: 会话ID
            x: X坐标
            y: Y坐标

        Returns:
            地块对象,不存在则返回None
        """
        stmt = select(InnerRealmTile).where(
            and_(
                InnerRealmTile.session_id == session_id,
                InnerRealmTile.x == x,
                InnerRealmTile.y == y
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_session_tiles(self, session_id: int) -> List[InnerRealmTile]:
        """
        获取会话的所有地块

        Args:
            session_id: 会话ID

        Returns:
            地块列表
        """
        stmt = select(InnerRealmTile).where(
            InnerRealmTile.session_id == session_id
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_tiles_by_type(
        self, session_id: int, event_type: str
    ) -> List[InnerRealmTile]:
        """
        按事件类型获取地块

        Args:
            session_id: 会话ID
            event_type: 事件类型(NPC/LOOT/CLUE/EMPTY/BOSS)

        Returns:
            地块列表
        """
        stmt = select(InnerRealmTile).where(
            and_(
                InnerRealmTile.session_id == session_id,
                InnerRealmTile.event_type == event_type
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_untriggered_tiles(
        self, session_id: int
    ) -> List[InnerRealmTile]:
        """
        获取未触发的地块

        Args:
            session_id: 会话ID

        Returns:
            未触发的地块列表
        """
        stmt = select(InnerRealmTile).where(
            and_(
                InnerRealmTile.session_id == session_id,
                InnerRealmTile.is_triggered == False
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_nearby_tiles(
        self, session_id: int, x: int, y: int, radius: int = 1
    ) -> List[InnerRealmTile]:
        """
        获取附近的地块

        Args:
            session_id: 会话ID
            x: 中心X坐标
            y: 中心Y坐标
            radius: 半径(默认1,即3x3范围)

        Returns:
            附近的地块列表
        """
        from sqlalchemy import func
        stmt = select(InnerRealmTile).where(
            and_(
                InnerRealmTile.session_id == session_id,
                func.abs(InnerRealmTile.x - x) <= radius,
                func.abs(InnerRealmTile.y - y) <= radius
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def delete_session_tiles(self, session_id: int) -> int:
        """
        删除会话的所有地块

        Args:
            session_id: 会话ID

        Returns:
            删除的地块数量
        """
        stmt = sql_delete(InnerRealmTile).where(
            InnerRealmTile.session_id == session_id
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def batch_add(self, tiles: List[InnerRealmTile]) -> List[InnerRealmTile]:
        """
        批量添加地块

        Args:
            tiles: 地块列表

        Returns:
            添加后的地块列表
        """
        self._session.add_all(tiles)
        await self._session.flush()
        return tiles
