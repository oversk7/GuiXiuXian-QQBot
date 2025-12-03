"""
BankFundRepository - 银行理财基金数据访问层

提供理财基金相关的数据库操作
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models.bank_fund import BankFund
from ...domain.repositories.base import IRepository


class BankFundRepository(IRepository[BankFund]):
    """银行理财基金仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[BankFund]:
        """根据基金ID获取基金"""
        return await self._session.get(BankFund, entity_id)

    async def add(self, entity: BankFund) -> BankFund:
        """添加基金"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: BankFund) -> BankFund:
        """更新基金"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: BankFund):
        """删除基金"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[BankFund]:
        """列出所有基金"""
        stmt = select(BankFund)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计基金数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(BankFund)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """检查基金是否存在"""
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 理财基金特定方法 ====================

    async def get_by_type(self, fund_type: str) -> Optional[BankFund]:
        """
        根据基金类型获取基金

        Args:
            fund_type: 基金类型(如"lively"活期)

        Returns:
            基金对象
        """
        stmt = select(BankFund).where(BankFund.fund_type == fund_type)
        result = await self._session.execute(stmt)
        return result.scalars().first()
