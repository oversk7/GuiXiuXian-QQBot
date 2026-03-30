"""
里界地块仓储实现
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from ...domain.repositories.base import IRepository
from ...models.inner_realm import InnerRealmTile


class InnerRealmTileRepository(IRepository[InnerRealmTile]):
    """
    里界地块仓储

    提供里界地块数据访问层,包括:
    - 标准CRUD操作
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

