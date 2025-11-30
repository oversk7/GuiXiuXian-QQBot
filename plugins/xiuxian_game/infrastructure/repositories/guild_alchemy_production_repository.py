"""
公会丹房产出仓储实现

提供公会丹房产出记录的数据访问抽象
"""

from typing import Optional, List
from datetime import date, datetime
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.guild import GuildAlchemyProduction


class GuildAlchemyProductionRepository(IRepository[GuildAlchemyProduction]):
    """公会丹房产出仓储实现"""

    def __init__(self, session: AsyncSession):
        """
        初始化公会丹房产出仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    async def get_by_id(self, production_id: int) -> Optional[GuildAlchemyProduction]:
        """
        根据ID获取丹房产出记录

        Args:
            production_id: 产出ID

        Returns:
            丹房产出实例，不存在返回None
        """
        stmt = select(GuildAlchemyProduction).where(GuildAlchemyProduction.id == production_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_unclaimed_productions(
        self, guild_id: int
    ) -> List[GuildAlchemyProduction]:
        """
        获取公会未领取的丹房产出列表

        Args:
            guild_id: 公会ID

        Returns:
            未领取产出列表（按产出时间降序）

        对应原代码:
            guild_facility_service.py Line 173-177
        """
        stmt = select(GuildAlchemyProduction).where(
            and_(
                GuildAlchemyProduction.guild_id == guild_id,
                GuildAlchemyProduction.claimed == False
            )
        ).order_by(GuildAlchemyProduction.produced_at.desc())

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_today_production_count(
        self, guild_id: int, today: date = None
    ) -> int:
        """
        获取今日已生成的丹房产出数量

        Args:
            guild_id: 公会ID
            today: 日期（默认今天）

        Returns:
            今日产出数量

        对应原代码:
            guild_facility_service.py Line 343-354
        """
        if today is None:
            today = date.today()

        today_start = datetime.combine(today, datetime.min.time())
        today_end = datetime.combine(today, datetime.max.time())

        stmt = select(func.count(GuildAlchemyProduction.id)).where(
            and_(
                GuildAlchemyProduction.guild_id == guild_id,
                GuildAlchemyProduction.produced_at >= today_start,
                GuildAlchemyProduction.produced_at <= today_end
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one()

    async def add(self, production: GuildAlchemyProduction) -> GuildAlchemyProduction:
        """
        添加丹房产出记录

        Args:
            production: 丹房产出实例

        Returns:
            添加后的记录（包含生成的ID）

        对应原代码:
            guild_facility_service.py Line 382-388
        """
        self._session.add(production)
        await self._session.flush()  # 刷新以获取生成的ID
        return production

    async def update(self, production: GuildAlchemyProduction) -> GuildAlchemyProduction:
        """
        更新丹房产出记录

        Args:
            production: 丹房产出实例

        Returns:
            更新后的记录

        对应原代码:
            guild_facility_service.py Line 258-261
        """
        self._session.add(production)
        return production

    async def mark_as_claimed(
        self, production: GuildAlchemyProduction, player_id: str
    ) -> GuildAlchemyProduction:
        """
        标记产出为已领取

        Args:
            production: 丹房产出实例
            player_id: 领取玩家ID

        Returns:
            更新后的记录

        对应原代码:
            guild_facility_service.py Line 258-261
        """
        production.claimed = True
        production.claimed_by = player_id
        production.claimed_at = datetime.now()
        self._session.add(production)
        return production

    async def delete(self, production_id: int) -> bool:
        """
        删除丹房产出记录

        Args:
            production_id: 产出ID

        Returns:
            是否成功删除
        """
        production = await self.get_by_id(production_id)
        if production:
            await self._session.delete(production)
            return True
        return False

    async def exists(self, production_id: int) -> bool:
        """
        检查丹房产出记录是否存在

        Args:
            production_id: 产出ID

        Returns:
            是否存在
        """
        production = await self.get_by_id(production_id)
        return production is not None

    async def count(self) -> int:
        """
        获取丹房产出记录总数

        Returns:
            记录总数
        """
        stmt = select(GuildAlchemyProduction)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
