"""
账号所有权仓储

提供AccountOwnership实体的数据访问层，支持：
1. 查找玩家拥有的所有账号
2. 查找当前激活的账号
3. 账号切换
4. 转让密钥管理
"""

from typing import Optional, List
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ...domain.repositories.base import IRepository
from ...models.account_ownership import AccountOwnership
from ...models.player import Player


class AccountOwnershipRepository(IRepository[AccountOwnership]):
    """账号所有权仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化账号所有权仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础查询 ====================

    async def find_by_id(self, ownership_id: int) -> Optional[AccountOwnership]:
        """
        通过主键ID查询所有权记录

        Args:
            ownership_id: 所有权记录ID

        Returns:
            所有权记录，不存在返回None
        """
        return await self._session.get(AccountOwnership, ownership_id)

    async def find_by_player_id(self, player_id: str) -> Optional[AccountOwnership]:
        """
        通过游戏账号ID查询所有权记录

        Args:
            player_id: 游戏账号ID

        Returns:
            所有权记录，不存在返回None
        """
        stmt = select(AccountOwnership).where(
            AccountOwnership.player_id == player_id
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 玩家账号查询 ====================

    async def find_all_by_owner(
        self,
        owner_platform_id: str,
        include_player: bool = False
    ) -> List[AccountOwnership]:
        """
        查找某个玩家拥有的所有游戏账号

        Args:
            owner_platform_id: 拥有者的平台ID
            include_player: 是否预加载Player对象（避免N+1）

        Returns:
            所有权记录列表（按创建时间排序）
        """
        stmt = select(AccountOwnership).where(
            AccountOwnership.owner_platform_id == owner_platform_id
        ).order_by(AccountOwnership.created_at)

        if include_player:
            stmt = stmt.options(selectinload(AccountOwnership.player))

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_active_by_owner(
        self,
        owner_platform_id: str
    ) -> Optional[AccountOwnership]:
        """
        查找某个玩家当前激活的游戏账号

        Args:
            owner_platform_id: 拥有者的平台ID

        Returns:
            激活的所有权记录，不存在返回None
        """
        stmt = select(AccountOwnership).where(
            and_(
                AccountOwnership.owner_platform_id == owner_platform_id,
                AccountOwnership.is_active == True
            )
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 转让密钥查询 ====================

    async def find_by_transfer_key(
        self,
        transfer_key: str
    ) -> Optional[AccountOwnership]:
        """
        通过转让密钥查找所有权记录

        Args:
            transfer_key: 转让密钥

        Returns:
            所有权记录，不存在返回None
        """
        stmt = select(AccountOwnership).where(
            AccountOwnership.transfer_key == transfer_key
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 账号切换 ====================

    async def deactivate_all_accounts(self, owner_platform_id: str) -> int:
        """
        将某个玩家的所有账号设为非激活状态

        Args:
            owner_platform_id: 拥有者的平台ID

        Returns:
            影响的行数
        """
        stmt = (
            update(AccountOwnership)
            .where(AccountOwnership.owner_platform_id == owner_platform_id)
            .values(is_active=False)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount

    async def activate_account(
        self,
        owner_platform_id: str,
        player_id: str
    ) -> bool:
        """
        激活指定的游戏账号

        先将所有账号设为非激活，再激活指定账号

        Args:
            owner_platform_id: 拥有者的平台ID
            player_id: 要激活的游戏账号ID

        Returns:
            是否成功
        """
        # 1. 将所有账号设为非激活
        await self.deactivate_all_accounts(owner_platform_id)

        # 2. 激活指定账号
        stmt = (
            update(AccountOwnership)
            .where(
                and_(
                    AccountOwnership.owner_platform_id == owner_platform_id,
                    AccountOwnership.player_id == player_id
                )
            )
            .values(is_active=True)
        )
        result = await self._session.execute(stmt)
        await self._session.flush()
        return result.rowcount > 0

    # ==================== CRUD操作 ====================

    async def create(self, ownership: AccountOwnership) -> AccountOwnership:
        """
        创建新的所有权记录

        Args:
            ownership: 所有权记录

        Returns:
            创建后的所有权记录（包含生成的ID）
        """
        self._session.add(ownership)
        await self._session.flush()
        return ownership

    async def update(self, ownership: AccountOwnership) -> None:
        """
        更新所有权记录

        Args:
            ownership: 所有权记录
        """
        self._session.add(ownership)
        await self._session.flush()

    async def delete(self, ownership: AccountOwnership) -> None:
        """
        删除所有权记录

        Args:
            ownership: 所有权记录
        """
        await self._session.delete(ownership)
        await self._session.flush()

    # ==================== 批量操作 ====================

    async def count_by_owner(self, owner_platform_id: str) -> int:
        """
        统计某个玩家拥有的游戏账号数量

        Args:
            owner_platform_id: 拥有者的平台ID

        Returns:
            账号数量
        """
        stmt = select(AccountOwnership).where(
            AccountOwnership.owner_platform_id == owner_platform_id
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
