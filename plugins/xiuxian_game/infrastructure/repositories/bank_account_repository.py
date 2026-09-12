"""
BankAccountRepository - 银行账户数据访问层

提供银行账户相关的数据库操作
"""
from typing import List, Optional
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models.bank_account import BankAccount
from ...models.player import Player
from ..locking import lock_row, lock_rows
from ...domain.repositories.base import IRepository


class BankAccountRepository(IRepository[BankAccount]):
    """银行账户仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: str) -> Optional[BankAccount]:
        """根据玩家ID获取银行账户（player_id是主键）"""
        return await self._session.get(BankAccount, entity_id)

    async def lock_player(self, player_id: str) -> Optional[Player]:
        return await lock_row(self._session, Player, player_id)

    async def get_locked(self, player_id: str) -> Optional[BankAccount]:
        return await lock_row(self._session, BankAccount, player_id)

    async def transfer(self, sender_id: str, receiver_id: str, amount: int) -> bool:
        if amount <= 0 or sender_id == receiver_id:
            return False
        players = await lock_rows(self._session, Player, [sender_id, receiver_id])
        if len(players) != 2:
            return False
        accounts = {}
        for player in players:
            accounts[player.id] = await self.get_or_create(player.id)
        sender, receiver = accounts[sender_id], accounts[receiver_id]
        if sender.balance < amount:
            return False
        sender.balance -= amount
        receiver.balance += amount - int(amount * 0.03)
        await self._session.flush()
        return True

    async def add(self, entity: BankAccount) -> BankAccount:
        """添加银行账户"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: BankAccount) -> BankAccount:
        """更新银行账户"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: BankAccount):
        """删除银行账户"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[BankAccount]:
        """列出所有银行账户"""
        stmt = select(BankAccount)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计银行账户数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(BankAccount)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: str) -> bool:
        """
        检查银行账户是否存在

        Args:
            entity_id: 玩家ID（银行账户主键）

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 银行账户特定方法 ====================

    async def get_or_create(self, player_id: str) -> BankAccount:
        """
        获取或创建银行账户

        Args:
            player_id: 玩家ID

        Returns:
            银行账户对象
        """
        # 调用方先锁玩家，串行化账户首次创建。
        account = await self.get_locked(player_id)
        if not account:
            account = BankAccount(
                player_id=player_id,
                balance=0,
                last_interest=datetime.now()
            )
            account = await self.add(account)
        return account

    async def deposit(self, player_id: str, amount: int) -> bool:
        """
        存款

        Args:
            player_id: 玩家ID
            amount: 存款金额

        Returns:
            是否成功
        """
        if amount <= 0:
            return False

        account = await self.get_or_create(player_id)
        account.balance += amount
        await self.update(account)
        return True

    async def withdraw(self, player_id: str, amount: int) -> bool:
        """
        取款

        Args:
            player_id: 玩家ID
            amount: 取款金额

        Returns:
            是否成功（余额不足返回False）
        """
        if amount <= 0:
            return False

        account = await self.get_locked(player_id)
        if not account or account.balance < amount:
            return False

        account.balance -= amount
        await self.update(account)
        return True

    async def check_balance(self, player_id: str) -> int:
        """
        查询余额

        Args:
            player_id: 玩家ID

        Returns:
            余额（账户不存在返回0）
        """
        account = await self.get_by_id(player_id)
        return account.balance if account else 0

    async def has_sufficient_balance(self, player_id: str, required_amount: int) -> bool:
        """
        检查余额是否充足

        Args:
            player_id: 玩家ID
            required_amount: 所需金额

        Returns:
            是否充足
        """
        balance = await self.check_balance(player_id)
        return balance >= required_amount
