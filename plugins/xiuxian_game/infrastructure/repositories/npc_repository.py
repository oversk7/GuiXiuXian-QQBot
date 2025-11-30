"""
NPC仓储实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计
"""

from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.repositories.base import IRepository
from ...models.npc import NPC, NPCType, NPCStatus
from ...models.location import Location


class NPCRepository(IRepository[NPC]):
    """
    NPC仓储实现

    提供NPC数据的访问和查询方法，支持AI Agent NPC接口预留
    """

    def __init__(self, session: AsyncSession):
        """
        初始化NPC仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    # ==================== 核心查询方法 ====================

    async def get_by_id(self, npc_id: str) -> Optional[NPC]:
        """
        按ID查询NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            NPC对象，如果不存在或已删除则返回None
        """
        stmt = select(NPC).where(
            and_(NPC.npc_id == npc_id, NPC.is_active == True)
        ).options(selectinload(NPC.location))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str, location_id: int = None) -> Optional[NPC]:
        """
        按名称查询NPC

        Args:
            name: NPC名称（精确匹配）
            location_id: 可选，限定地点ID

        Returns:
            NPC对象，如果不存在则返回None
        """
        conditions = [NPC.name == name, NPC.is_active == True]
        if location_id:
            conditions.append(NPC.location_id == location_id)

        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_location(
        self,
        location_id: int,
        npc_type: NPCType = None,
        include_dead: bool = False
    ) -> List[NPC]:
        """
        按地点查询NPC

        Args:
            location_id: 地点ID
            npc_type: 可选，NPC类型过滤
            include_dead: 是否包含死亡NPC，默认False

        Returns:
            NPC列表
        """
        conditions = [NPC.location_id == location_id, NPC.is_active == True]

        if npc_type:
            conditions.append(NPC.npc_type == npc_type)

        if not include_dead:
            conditions.append(NPC.status != NPCStatus.DEAD)

        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_type(
        self,
        npc_type: NPCType,
        region: str = None
    ) -> List[NPC]:
        """
        按类型查询NPC

        Args:
            npc_type: NPC类型
            region: 可选，区域过滤

        Returns:
            NPC列表（仅包含存活的NPC）
        """
        conditions = [NPC.npc_type == npc_type, NPC.is_active == True, NPC.status != NPCStatus.DEAD]

        if region:
            stmt = select(NPC).join(Location).where(
                and_(Location.region == region, *conditions)
            ).options(selectinload(NPC.location))
        else:
            stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_partial_name(
        self,
        partial_name: str,
        location_id: int = None
    ) -> List[NPC]:
        """
        模糊查询NPC名称

        Args:
            partial_name: 部分名称（模糊匹配）
            location_id: 可选，限定地点ID

        Returns:
            匹配的NPC列表
        """
        conditions = [
            NPC.name.like(f"%{partial_name}%"),
            NPC.is_active == True,
            NPC.status != NPCStatus.DEAD
        ]

        if location_id:
            conditions.append(NPC.location_id == location_id)

        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_dynamic_npcs(self, location_id: int = None) -> List[NPC]:
        """
        查询动态NPC

        Args:
            location_id: 可选，限定地点ID

        Returns:
            动态NPC列表
        """
        conditions = [NPC.is_dynamic == True, NPC.is_active == True]

        if location_id:
            conditions.append(NPC.location_id == location_id)

        stmt = select(NPC).where(and_(*conditions)).options(selectinload(NPC.location))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_respawning_npcs(self) -> List[NPC]:
        """
        查询复活中的NPC（复活时间已到）

        Returns:
            可以复活的NPC列表
        """
        stmt = select(NPC).where(
            and_(
                NPC.status == NPCStatus.RESPAWNING,
                NPC.respawn_time <= datetime.now(),
                NPC.is_active == True
            )
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    # ==================== 创建/更新/删除方法 ====================

    async def create(self, npc: NPC) -> NPC:
        """
        创建NPC

        Args:
            npc: NPC实体对象

        Returns:
            创建后的NPC对象
        """
        self._session.add(npc)
        await self._session.flush()
        return npc

    async def add(self, entity: NPC) -> NPC:
        """add别名，调用create以符合IRepository接口"""
        return await self.create(entity)

    async def update(self, npc: NPC) -> NPC:
        """
        更新NPC

        Args:
            npc: NPC实体对象

        Returns:
            更新后的NPC对象
        """
        self._session.add(npc)
        await self._session.flush()
        return npc

    async def kill(self, npc_id: str) -> bool:
        """
        击杀NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否击杀成功
        """
        npc = await self.get_by_id(npc_id)
        if not npc or not npc.is_killable:
            return False
        npc.kill()
        return True

    async def respawn(self, npc_id: str) -> bool:
        """
        复活NPC

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否复活成功
        """
        npc = await self.get_by_id(npc_id)
        if not npc:
            return False
        return npc.respawn()

    async def delete(self, npc_id: str) -> bool:
        """
        删除NPC（软删除）

        Args:
            npc_id: NPC唯一标识

        Returns:
            是否删除成功
        """
        npc = await self.get_by_id(npc_id)
        if not npc:
            return False
        npc.is_active = False
        return True

    async def exists(self, entity_id: str) -> bool:
        """
        检查NPC是否存在

        Args:
            entity_id: NPC ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    async def count(self) -> int:
        """
        获取NPC总数

        Returns:
            NPC数量
        """
        from sqlalchemy import func
        stmt = select(func.count()).select_from(NPC)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def cleanup_expired_dynamic(self, max_age_hours: int = 24) -> int:
        """
        清理过期动态NPC

        Args:
            max_age_hours: 最大存活时间（小时），默认24小时

        Returns:
            清理的NPC数量
        """
        cutoff_time = datetime.now() - timedelta(hours=max_age_hours)

        stmt = select(NPC).where(
            and_(
                NPC.is_dynamic == True,
                NPC.created_at < cutoff_time,
                NPC.status == NPCStatus.DEAD
            )
        )
        result = await self._session.execute(stmt)
        expired_npcs = result.scalars().all()

        for npc in expired_npcs:
            npc.is_active = False

        return len(expired_npcs)

    # ==================== AI Agent NPC相关预留方法 ====================

    async def get_with_ai_config(self, npc_id: str) -> Optional[NPC]:
        """
        获取NPC及其AI配置（预留）

        未来会扩展为同时预加载NPCCharacter关系
        当前实现等同于get_by_id

        Args:
            npc_id: NPC唯一标识

        Returns:
            NPC对象及其AI配置
        """
        return await self.get_by_id(npc_id)

    async def get_ai_enabled_by_location(self, location_id: int) -> List[NPC]:
        """
        获取位置的AI启用NPC（预留）

        Args:
            location_id: 地点ID

        Returns:
            启用AI的NPC列表
        """
        npcs = await self.get_by_location(location_id)
        return [npc for npc in npcs if npc.extra_data.get("ai_enabled", False)]
