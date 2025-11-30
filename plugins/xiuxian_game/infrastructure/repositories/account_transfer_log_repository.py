"""
账号转让历史仓储

提供AccountTransferLog实体的数据访问层，支持：
1. 记录账号转让操作
2. 查询玩家的转让历史
3. 查询某个用户的买入/卖出历史
4. 审计追踪
"""

from typing import Optional, List
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from ..domain.repositories.base import IRepository
from ...models.account_transfer_log import AccountTransferLog


class AccountTransferLogRepository(IRepository[AccountTransferLog]):
    """账号转让历史仓储"""

    def __init__(self, session: AsyncSession):
        """
        初始化账号转让历史仓储

        Args:
            session: 数据库会话
        """
        self._session = session

    # ==================== 基础查询 ====================

    async def find_by_id(self, log_id: int) -> Optional[AccountTransferLog]:
        """
        通过主键ID查询转让记录

        Args:
            log_id: 转让记录ID

        Returns:
            转让记录，不存在返回None
        """
        return await self._session.get(AccountTransferLog, log_id)

    # ==================== 账号转让历史查询 ====================

    async def find_by_player_id(
        self,
        player_id: str,
        limit: Optional[int] = None
    ) -> List[AccountTransferLog]:
        """
        查询某个游戏账号的所有转让历史

        Args:
            player_id: 游戏账号ID
            limit: 限制返回数量（最近N条）

        Returns:
            转让记录列表（按时间倒序）
        """
        stmt = (
            select(AccountTransferLog)
            .where(AccountTransferLog.player_id == player_id)
            .order_by(desc(AccountTransferLog.transfer_time))
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_from_platform(
        self,
        from_platform_id: str,
        limit: Optional[int] = None
    ) -> List[AccountTransferLog]:
        """
        查询某个用户转出（卖出/赠送）的所有账号历史

        Args:
            from_platform_id: 原拥有者的平台ID
            limit: 限制返回数量（最近N条）

        Returns:
            转让记录列表（按时间倒序）
        """
        stmt = (
            select(AccountTransferLog)
            .where(AccountTransferLog.from_platform_id == from_platform_id)
            .order_by(desc(AccountTransferLog.transfer_time))
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_to_platform(
        self,
        to_platform_id: str,
        limit: Optional[int] = None
    ) -> List[AccountTransferLog]:
        """
        查询某个用户接收（买入/获赠）的所有账号历史

        Args:
            to_platform_id: 新拥有者的平台ID
            limit: 限制返回数量（最近N条）

        Returns:
            转让记录列表（按时间倒序）
        """
        stmt = (
            select(AccountTransferLog)
            .where(AccountTransferLog.to_platform_id == to_platform_id)
            .order_by(desc(AccountTransferLog.transfer_time))
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_transfer_key(
        self,
        transfer_key: str
    ) -> Optional[AccountTransferLog]:
        """
        通过转让密钥查询转让记录（用于审计）

        Args:
            transfer_key: 使用的转让密钥

        Returns:
            转让记录，不存在返回None
        """
        stmt = select(AccountTransferLog).where(
            AccountTransferLog.transfer_key_used == transfer_key
        )
        result = await self._session.execute(stmt)
        return result.scalars().first()

    # ==================== 统计查询 ====================

    async def count_transfers_by_player(self, player_id: str) -> int:
        """
        统计某个游戏账号的转让次数

        Args:
            player_id: 游戏账号ID

        Returns:
            转让次数
        """
        stmt = select(AccountTransferLog).where(
            AccountTransferLog.player_id == player_id
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def count_transfers_from_platform(self, from_platform_id: str) -> int:
        """
        统计某个用户转出的账号数量

        Args:
            from_platform_id: 原拥有者的平台ID

        Returns:
            转出账号数量
        """
        stmt = select(AccountTransferLog).where(
            AccountTransferLog.from_platform_id == from_platform_id
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def count_transfers_to_platform(self, to_platform_id: str) -> int:
        """
        统计某个用户接收的账号数量

        Args:
            to_platform_id: 新拥有者的平台ID

        Returns:
            接收账号数量
        """
        stmt = select(AccountTransferLog).where(
            AccountTransferLog.to_platform_id == to_platform_id
        )
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    # ==================== CRUD操作 ====================

    async def create(
        self,
        player_id: str,
        from_platform_id: str,
        to_platform_id: str,
        transfer_type: str,
        transfer_key_used: Optional[str] = None,
        notes: Optional[str] = None
    ) -> AccountTransferLog:
        """
        创建新的转让记录

        Args:
            player_id: 被转让的游戏账号ID
            from_platform_id: 原拥有者的平台ID
            to_platform_id: 新拥有者的平台ID
            transfer_type: 转让类型（sale/gift/admin）
            transfer_key_used: 使用的转让密钥
            notes: 转让备注

        Returns:
            创建后的转让记录（包含生成的ID）
        """
        log = AccountTransferLog(
            player_id=player_id,
            from_platform_id=from_platform_id,
            to_platform_id=to_platform_id,
            transfer_type=transfer_type,
            transfer_key_used=transfer_key_used,
            notes=notes
        )
        self._session.add(log)
        await self._session.flush()
        return log

    async def update(self, log: AccountTransferLog) -> None:
        """
        更新转让记录（一般不需要，仅用于修正错误）

        Args:
            log: 转让记录
        """
        self._session.add(log)
        await self._session.flush()

    async def delete(self, log: AccountTransferLog) -> None:
        """
        删除转让记录（谨慎使用，会影响审计追踪）

        Args:
            log: 转让记录
        """
        await self._session.delete(log)
        await self._session.flush()

    # ==================== 高级查询 ====================

    async def find_recent_transfers(
        self,
        days: int = 7,
        limit: Optional[int] = 50
    ) -> List[AccountTransferLog]:
        """
        查询最近N天的所有转让记录（用于管理员监控）

        Args:
            days: 最近天数
            limit: 限制返回数量

        Returns:
            转让记录列表（按时间倒序）
        """
        from datetime import timedelta
        cutoff_time = datetime.now() - timedelta(days=days)

        stmt = (
            select(AccountTransferLog)
            .where(AccountTransferLog.transfer_time >= cutoff_time)
            .order_by(desc(AccountTransferLog.transfer_time))
        )

        if limit:
            stmt = stmt.limit(limit)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def find_transfers_between_users(
        self,
        platform_id_1: str,
        platform_id_2: str
    ) -> List[AccountTransferLog]:
        """
        查询两个用户之间的所有转让记录（双向）

        Args:
            platform_id_1: 用户1的平台ID
            platform_id_2: 用户2的平台ID

        Returns:
            转让记录列表（按时间倒序）
        """
        stmt = (
            select(AccountTransferLog)
            .where(
                and_(
                    AccountTransferLog.from_platform_id.in_([platform_id_1, platform_id_2]),
                    AccountTransferLog.to_platform_id.in_([platform_id_1, platform_id_2])
                )
            )
            .order_by(desc(AccountTransferLog.transfer_time))
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
