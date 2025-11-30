"""
JobLocationRepository - 工作地点数据访问层

提供工作地点相关的数据库操作
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from ...models.part_time_job import JobLocation
from ...domain.repositories.base import IRepository


class JobLocationRepository(IRepository[JobLocation]):
    """工作地点仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[JobLocation]:
        """根据ID获取工作地点"""
        return await self._session.get(JobLocation, entity_id)

    async def add(self, entity: JobLocation) -> JobLocation:
        """添加工作地点"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: JobLocation) -> JobLocation:
        """更新工作地点"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: JobLocation):
        """删除工作地点"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[JobLocation]:
        """列出所有工作地点"""
        stmt = select(JobLocation)
        if filters.get("is_active") is not None:
            stmt = stmt.where(JobLocation.is_active == filters["is_active"])
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计工作地点数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(JobLocation)
        if filters.get("is_active") is not None:
            stmt = stmt.where(JobLocation.is_active == filters["is_active"])
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """
        检查工作地点是否存在

        Args:
            entity_id: 工作地点ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 工作地点特定方法 ====================

    async def get_by_location_id(self, location_id: str) -> Optional[JobLocation]:
        """
        根据地点ID获取工作地点

        Args:
            location_id: 地点ID（唯一标识符）

        Returns:
            工作地点对象，如果不存在则返回None
        """
        stmt = select(JobLocation).where(JobLocation.location_id == location_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_coordinates(self, x: int, y: int) -> Optional[JobLocation]:
        """
        根据坐标获取工作地点

        Args:
            x: X坐标
            y: Y坐标

        Returns:
            该坐标的工作地点，如果不存在则返回None
        """
        stmt = select(JobLocation).where(
            and_(
                JobLocation.x == x,
                JobLocation.y == y,
                JobLocation.is_active == True
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_active_locations(self) -> List[JobLocation]:
        """
        获取所有激活的工作地点

        Returns:
            激活的工作地点列表
        """
        stmt = select(JobLocation).where(JobLocation.is_active == True)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_locations_by_region(self, region: str) -> List[JobLocation]:
        """
        根据区域获取工作地点

        Args:
            region: 区域名称

        Returns:
            该区域的工作地点列表
        """
        stmt = select(JobLocation).where(
            and_(
                JobLocation.region == region,
                JobLocation.is_active == True
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_locations_for_level(self, player_level: int) -> List[JobLocation]:
        """
        获取玩家等级可访问的工作地点

        Args:
            player_level: 玩家等级

        Returns:
            可访问的工作地点列表
        """
        stmt = select(JobLocation).where(
            and_(
                JobLocation.is_active == True,
                JobLocation.required_level <= player_level
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
