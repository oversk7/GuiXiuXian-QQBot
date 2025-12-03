"""
FundHoldingRepository - 理财持仓数据访问层

提供理财持仓相关的数据库操作
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ...models.bank_fund import FundHolding
from ...domain.repositories.base import IRepository


class FundHoldingRepository(IRepository[FundHolding]):
    """理财持仓仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[FundHolding]:
        """根据持仓ID获取持仓"""
        return await self._session.get(FundHolding, entity_id)

    async def add(self, entity: FundHolding) -> FundHolding:
        """添加持仓"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: FundHolding) -> FundHolding:
        """更新持仓"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: FundHolding):
        """删除持仓"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[FundHolding]:
        """列出所有持仓"""
        stmt = select(FundHolding)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计持仓数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(FundHolding)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """检查持仓是否存在"""
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 理财持仓特定方法 ====================

    async def get_player_holdings(self, player_id: str, active_only: bool = True) -> List[FundHolding]:
        """
        获取玩家的所有持仓

        Args:
            player_id: 玩家ID
            active_only: 是否只返回活跃持仓(默认True)

        Returns:
            持仓列表
        """
        stmt = select(FundHolding).where(FundHolding.player_id == player_id)

        if active_only:
            stmt = stmt.where(FundHolding.is_active == True)

        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_active_holdings(self) -> List[FundHolding]:
        """
        获取所有活跃持仓（用于定时任务结算）

        Returns:
            活跃持仓列表
        """
        stmt = select(FundHolding).where(FundHolding.is_active == True)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
