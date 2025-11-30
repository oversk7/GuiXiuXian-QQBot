"""
公会仓储实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计
支持GuildService的DI改造
"""

from typing import Optional, List
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ...domain.repositories.base import IRepository
from ...models.guild import Guild, GuildMember, GuildPosition


class GuildRepository(IRepository[Guild]):
    """
    公会仓储实现

    提供公会数据的访问和查询方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化公会仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    async def get_by_id(self, guild_id: int) -> Optional[Guild]:
        """
        根据ID获取公会

        Args:
            guild_id: 公会ID

        Returns:
            公会对象，如果不存在则返回 None
        """
        stmt = select(Guild).where(Guild.id == guild_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Guild]:
        """
        根据名称获取公会

        Args:
            name: 公会名称

        Returns:
            公会对象，如果不存在则返回 None
        """
        stmt = select(Guild).where(Guild.name == name)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, guild: Guild) -> Guild:
        """
        添加新公会

        Args:
            guild: 公会对象

        Returns:
            添加后的公会（包含生成的ID）
        """
        self._session.add(guild)
        await self._session.flush()  # 获取自增ID
        return guild

    async def update(self, guild: Guild) -> Guild:
        """
        更新公会

        Args:
            guild: 公会对象

        Returns:
            更新后的公会
        """
        self._session.add(guild)
        return guild

    async def delete(self, guild_id: int) -> bool:
        """
        删除公会

        Args:
            guild_id: 公会ID

        Returns:
            是否删除成功
        """
        guild = await self.get_by_id(guild_id)
        if guild:
            await self._session.delete(guild)
            return True
        return False

    async def exists(self, guild_id: int) -> bool:
        """
        检查公会是否存在

        Args:
            guild_id: 公会ID

        Returns:
            是否存在
        """
        stmt = select(func.count()).select_from(Guild).where(Guild.id == guild_id)
        result = await self._session.execute(stmt)
        count = result.scalar()
        return count > 0

    async def count(self) -> int:
        """
        获取公会总数

        Returns:
            公会数量
        """
        stmt = select(func.count()).select_from(Guild)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def get_member_count(self, guild_id: int) -> int:
        """
        获取公会成员数量

        Args:
            guild_id: 公会ID

        Returns:
            成员数量
        """
        stmt = select(func.count()).select_from(GuildMember).where(GuildMember.guild_id == guild_id)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def get_members(self, guild_id: int) -> List[GuildMember]:
        """
        获取公会成员列表

        Args:
            guild_id: 公会ID

        Returns:
            成员列表
        """
        stmt = select(GuildMember).where(GuildMember.guild_id == guild_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_member(self, guild_id: int, player_id: str) -> Optional[GuildMember]:
        """
        获取特定成员信息

        Args:
            guild_id: 公会ID
            player_id: 玩家ID

        Returns:
            成员信息，如果不存在则返回 None
        """
        stmt = select(GuildMember).where(
            and_(GuildMember.guild_id == guild_id, GuildMember.player_id == player_id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add_member(self, guild_member: GuildMember) -> GuildMember:
        """
        添加公会成员

        Args:
            guild_member: 公会成员对象

        Returns:
            添加后的成员对象
        """
        self._session.add(guild_member)
        await self._session.flush()
        return guild_member

    async def remove_member(self, guild_id: int, player_id: str) -> bool:
        """
        移除公会成员

        Args:
            guild_id: 公会ID
            player_id: 玩家ID

        Returns:
            是否移除成功
        """
        member = await self.get_member(guild_id, player_id)
        if member:
            await self._session.delete(member)
            return True
        return False
