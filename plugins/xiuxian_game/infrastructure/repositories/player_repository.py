"""
玩家仓储实现

基于 REFACTORING_PLAN_v4.md 第2.2节的设计
"""

from typing import Optional, List
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from ...domain.repositories.base import IRepository
from ...models.player import Player
from ...models.account_ownership import AccountOwnership


class PlayerRepository(IRepository[Player]):
    """
    玩家仓储实现

    提供玩家数据的访问和查询方法
    """

    def __init__(self, session: AsyncSession):
        """
        初始化玩家仓储

        Args:
            session: 数据库会话（由UnitOfWork注入）
        """
        self._session = session

    async def get_by_id(self, player_id: str) -> Optional[Player]:
        """
        根据ID获取玩家

        Args:
            player_id: 玩家ID

        Returns:
            玩家对象，如果不存在则返回 None
        """
        stmt = select(Player).where(Player.id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, player_id: str) -> Optional[Player]:
        """锁定并刷新玩家行，用于金币等资产的并发更新。"""
        stmt = (
            select(Player)
            .where(Player.id == player_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_uid(self, uid: int, server_id: int | None = None) -> Optional[Player]:
        """
        根据UID获取玩家

        Args:
            uid: 玩家UID（数字）

        Returns:
            玩家对象，如果不存在则返回 None
        """
        stmt = select(Player).where(Player.uid == uid)
        if server_id is not None:
            stmt = stmt.where(Player.server_id == server_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_platform_id(self, platform_id: str) -> Optional[Player]:
        """
        根据平台ID获取玩家（实际上就是get_by_id的别名，但语义更清晰）

        Args:
            platform_id: 平台ID（QQ号等）

        Returns:
            玩家对象，如果不存在则返回 None
        """
        return await self.get_by_id(platform_id)

    async def get_with_monthly_cards(self, player_id: str) -> Optional[Player]:
        """
        获取玩家及其月卡信息（优化N+1查询）

        使用 joinedload 预加载月卡关系

        Args:
            player_id: 玩家ID

        Returns:
            玩家对象（包含预加载的月卡）
        """
        stmt = (
            select(Player)
            .options(joinedload(Player.monthly_cards))
            .where(Player.id == player_id)
        )
        result = await self._session.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_nearby_players(
        self,
        x: int,
        y: int,
        region: str,
        max_distance: int,
        server_id: int = 1,
    ) -> List[Player]:
        """
        获取附近的玩家（优化的查询）

        基于 data_access_investigation.md 的建议：
        - 使用边界框预过滤（数据库层）
        - 使用曼哈顿距离后过滤（应用层）

        Args:
            x: X坐标
            y: Y坐标
            region: 区域名称
            max_distance: 最大距离

        Returns:
            附近的玩家列表
        """
        # 边界框查询（利用索引）
        stmt = select(Player).where(
            and_(
                Player.region == region,
                Player.server_id == server_id,
                Player.x.between(x - max_distance, x + max_distance),
                Player.y.between(y - max_distance, y + max_distance)
            )
        )
        result = await self._session.execute(stmt)
        players = result.scalars().all()

        # 曼哈顿距离后过滤
        return [
            p for p in players
            if abs(p.x - x) + abs(p.y - y) <= max_distance
        ]

    async def add(self, player: Player) -> Player:
        """
        添加新玩家

        Args:
            player: 玩家对象

        Returns:
            添加后的玩家（包含生成的ID）
        """
        self._session.add(player)
        await self._session.flush()  # 获取自增ID
        return player

    async def update(self, player: Player) -> Player:
        """
        更新玩家

        Args:
            player: 玩家对象

        Returns:
            更新后的玩家
        """
        self._session.add(player)
        return player

    async def delete(self, player_id: str) -> bool:
        """
        删除玩家

        Args:
            player_id: 玩家ID

        Returns:
            是否删除成功
        """
        player = await self.get_by_id(player_id)
        if player:
            await self._session.delete(player)
            return True
        return False

    async def exists(self, player_id: str) -> bool:
        """
        检查玩家是否存在

        Args:
            player_id: 玩家ID

        Returns:
            是否存在
        """
        stmt = select(func.count()).select_from(Player).where(Player.id == player_id)
        result = await self._session.execute(stmt)
        count = result.scalar()
        return count > 0

    async def count(self) -> int:
        """
        获取玩家总数

        Returns:
            玩家数量
        """
        stmt = select(func.count()).select_from(Player)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def get_by_nickname(self, nickname: str) -> Optional[Player]:
        """
        根据昵称获取玩家

        Args:
            nickname: 玩家昵称

        Returns:
            玩家对象，如果不存在则返回 None
        """
        stmt = select(Player).where(Player.nickname == nickname)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_guild_members(self, guild_id: str) -> List[Player]:
        """
        获取公会成员列表

        Args:
            guild_id: 公会ID

        Returns:
            公会成员列表
        """
        stmt = select(Player).where(Player.guild_id == guild_id)
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_many_by_ids(self, player_ids: List[str]) -> List[Player]:
        """
        批量获取玩家（按ID列表）

        用于优化多个玩家的批量查询，避免多次单独查询

        Args:
            player_ids: 玩家ID列表

        Returns:
            玩家对象列表（仅返回存在的玩家）
        """
        if not player_ids:
            return []

        stmt = select(Player).where(Player.id.in_(player_ids))
        result = await self._session.execute(stmt)
        return result.scalars().all()

    async def get_active_by_platform_id(self, platform_id: str) -> Optional[Player]:
        """
        根据平台ID获取当前激活的玩家账号

        通过 AccountOwnership 表查询 is_active=True 的账号，
        支持多账号切换功能。

        Args:
            platform_id: 平台ID（QQ号、频道ID等）

        Returns:
            激活的玩家对象，如果不存在则返回 None
        """
        stmt = (
            select(Player)
            .join(AccountOwnership, Player.id == AccountOwnership.player_id)
            .where(
                and_(
                    AccountOwnership.owner_platform_id == platform_id,
                    AccountOwnership.is_active == True
                )
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_mansion_owner_at_location(self, x: int, y: int, server_id: int = 1) -> Optional[Player]:
        """
        查找指定坐标的阴宅主人

        Args:
            x: X坐标
            y: Y坐标

        Returns:
            阴宅主人对象，如果该位置没有阴宅则返回 None
        """
        stmt = select(Player).where(
            and_(
                Player.mansion_x == x,
                Player.mansion_y == y,
                Player.server_id == server_id,
                Player.mansion_level > 0
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()
