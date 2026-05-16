"""
公会建筑仓储实现

提供公会建筑的数据访问抽象
"""

from typing import List, Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild import GuildBuilding, BuildingType


class GuildBuildingRepository(IRepository[GuildBuilding]):
    """公会建筑仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化公会建筑仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, building_id: int) -> Optional[GuildBuilding]:
        """
        根据ID获取建筑记录

        Args:
            building_id: 建筑ID

        Returns:
            建筑实例，不存在返回None
        """
        stmt = select(GuildBuilding).where(GuildBuilding.id == building_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_guild_and_type(
        self, guild_id: int, building_type: BuildingType
    ) -> Optional[GuildBuilding]:
        """
        根据公会ID和建筑类型获取建筑

        Args:
            guild_id: 公会ID
            building_type: 建筑类型

        Returns:
            建筑实例，不存在返回None

        对应原代码:
            guild_building_service.py Line 142-145
        """
        stmt = select(GuildBuilding).where(
            and_(
                GuildBuilding.guild_id == guild_id,
                GuildBuilding.building_type == building_type
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_guild_and_position(
        self, guild_id: int, plot_x: int, plot_y: int
    ) -> Optional[GuildBuilding]:
        """根据公会ID和基地布局坐标获取建筑"""
        stmt = select(GuildBuilding).where(
            and_(
                GuildBuilding.guild_id == guild_id,
                GuildBuilding.plot_x == plot_x,
                GuildBuilding.plot_y == plot_y,
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_guild_id(self, guild_id: int) -> List[GuildBuilding]:
        """
        获取公会的所有建筑

        Args:
            guild_id: 公会ID

        Returns:
            建筑列表

        对应原代码:
            guild_building_service.py Line 270-271
        """
        stmt = select(GuildBuilding).where(GuildBuilding.guild_id == guild_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def add(self, building: GuildBuilding) -> GuildBuilding:
        """
        添加建筑记录

        Args:
            building: 建筑实例

        Returns:
            添加后的建筑记录（包含生成的ID）

        对应原代码:
            guild_building_service.py Line 259-264
        """
        self._session.add(building)
        await self._session.flush()  # 刷新以获取生成的ID
        return building

    async def update(self, building: GuildBuilding) -> GuildBuilding:
        """
        更新建筑记录

        Args:
            building: 建筑实例

        Returns:
            更新后的建筑记录

        对应原代码:
            guild_building_service.py Line 253-255
        """
        self._session.add(building)
        return building

    async def delete(self, building_id: int) -> bool:
        """
        删除建筑记录

        Args:
            building_id: 建筑ID

        Returns:
            是否成功删除
        """
        building = await self.get_by_id(building_id)
        if building:
            await self._session.delete(building)
            return True
        return False

    async def exists(self, building_id: int) -> bool:
        """
        检查建筑记录是否存在

        Args:
            building_id: 建筑ID

        Returns:
            是否存在
        """
        building = await self.get_by_id(building_id)
        return building is not None

    async def count(self) -> int:
        """
        获取建筑记录总数

        Returns:
            记录总数
        """
        stmt = select(GuildBuilding)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
