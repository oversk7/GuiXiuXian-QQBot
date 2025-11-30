"""
地点仓储实现

基于 REFACTORING_PLAN_v4.md 的DI架构重构
"""

from typing import Optional, List
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.repositories.base import IRepository
from ...models.location import Location
from ...models.player import Player


class LocationRepository(IRepository[Location]):
    """
    地点仓储实现

    提供地点数据的访问和查询方法，包含N+1优化和JSON查询优化
    """

    def __init__(self, session: AsyncSession):
        """
        初始化地点仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    # ==================== 核心查询方法 ====================

    async def get_by_id(self, location_id: str) -> Optional[Location]:
        """
        按ID查询地点

        Args:
            location_id: 地点唯一标识

        Returns:
            Location对象，如果不存在则返回None
        """
        stmt = select(Location).where(Location.location_id == location_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_id(self, location_id: str) -> Optional[Location]:
        """
        按ID查询地点（IRepository接口的别名方法）

        Args:
            location_id: 地点唯一标识

        Returns:
            Location对象，如果不存在则返回None
        """
        return await self.get_by_id(location_id)

    async def find_by_coordinates(
        self,
        x: int,
        y: int,
        region: str = "大都会"
    ) -> Optional[Location]:
        """
        根据坐标查询地点（预加载NPC）

        Args:
            x: X坐标
            y: Y坐标
            region: 所属区域，默认"大都会"

        Returns:
            Location对象，如果不存在则返回None
        """
        stmt = (
            select(Location)
            .options(selectinload(Location.npcs))  # 预加载NPC列表，避免N+1
            .where(
                and_(
                    Location.x == x,
                    Location.y == y,
                    Location.region == region,
                    Location.is_active == True
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_nearby(
        self,
        x: int,
        y: int,
        region: str,
        max_distance: int
    ) -> List[Location]:
        """
        获取附近地点（SQL排序优化）

        Args:
            x: 中心X坐标
            y: 中心Y坐标
            region: 所属区域
            max_distance: 最大曼哈顿距离

        Returns:
            地点列表，按距离升序排序
        """
        stmt = (
            select(Location)
            .options(selectinload(Location.npcs))
            .where(
                and_(
                    Location.region == region,
                    Location.is_active == True,
                    func.abs(Location.x - x) + func.abs(Location.y - y) <= max_distance
                )
            )
            .order_by(func.abs(Location.x - x) + func.abs(Location.y - y))  # SQL排序
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_type(
        self,
        location_type: str,
        region: str = "大都会"
    ) -> List[Location]:
        """
        根据类型获取地点

        Args:
            location_type: 地点类型
            region: 所属区域，默认"大都会"

        Returns:
            地点列表
        """
        stmt = (
            select(Location)
            .options(selectinload(Location.npcs))
            .where(
                and_(
                    Location.location_type == location_type,
                    Location.region == region,
                    Location.is_active == True
                )
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_with_function(
        self,
        function_name: str,
        region: str = "大都会"
    ) -> List[Location]:
        """
        查询具有特定功能的地点（JSON查询优化）

        使用MySQL JSON查询，避免全表扫描+Python过滤

        Args:
            function_name: 功能名称（如"market", "forge"等）
            region: 所属区域，默认"大都会"

        Returns:
            地点列表
        """
        # 使用JSON查询（MySQL 5.7+）
        stmt = (
            select(Location)
            .options(selectinload(Location.npcs))
            .where(
                and_(
                    Location.region == region,
                    Location.is_active == True,
                    func.json_extract(Location.functions, f'$.{function_name}.enabled') == True
                )
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_nearby_players(
        self,
        x: int,
        y: int,
        region: str,
        max_distance: int,
        exclude_id: str = None
    ) -> List[Player]:
        """
        获取附近的玩家（SQL排序）

        Args:
            x: 中心X坐标
            y: 中心Y坐标
            region: 所属区域
            max_distance: 最大曼哈顿距离
            exclude_id: 排除的玩家ID（通常是当前玩家）

        Returns:
            玩家列表，按距离升序排序
        """
        conditions = [
            Player.region == region,
            func.abs(Player.x - x) + func.abs(Player.y - y) <= max_distance
        ]

        if exclude_id:
            conditions.append(Player.id != exclude_id)

        stmt = (
            select(Player)
            .where(and_(*conditions))
            .order_by(func.abs(Player.x - x) + func.abs(Player.y - y))  # SQL排序
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_all_active(self, region: str = None) -> List[Location]:
        """
        查询所有活跃地点

        Args:
            region: 可选，限定区域

        Returns:
            地点列表
        """
        conditions = [Location.is_active == True]
        if region:
            conditions.append(Location.region == region)

        stmt = select(Location).where(and_(*conditions))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ==================== 写入方法 ====================

    async def add(self, location: Location) -> Location:
        """
        添加新地点

        Args:
            location: Location实体对象

        Returns:
            添加后的Location对象
        """
        self._session.add(location)
        await self._session.flush()
        return location

    async def update(self, location: Location) -> Location:
        """
        更新地点

        Args:
            location: Location实体对象

        Returns:
            更新后的Location对象
        """
        self._session.add(location)
        return location

    async def delete(self, location_id: str) -> bool:
        """
        删除地点（软删除）

        Args:
            location_id: 地点唯一标识

        Returns:
            是否删除成功
        """
        location = await self.get_by_id(location_id)
        if not location:
            return False
        location.is_active = False
        return True

    async def add_batch(self, locations: List[Location]) -> List[Location]:
        """
        批量添加地点

        Args:
            locations: Location实体列表

        Returns:
            添加后的Location列表
        """
        self._session.add_all(locations)
        await self._session.flush()
        return locations
