"""
灵壤/地块仓储实现
"""
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from ...domain.repositories.base import IRepository
from ...models.spirit_field import SpiritFieldPlot


class SpiritFieldPlotRepository(IRepository[SpiritFieldPlot]):
    """灵壤/地块仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, plot_id: int) -> Optional[SpiritFieldPlot]:
        return await self._session.get(SpiritFieldPlot, plot_id)

    async def add(self, entity: SpiritFieldPlot) -> SpiritFieldPlot:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: SpiritFieldPlot) -> SpiritFieldPlot:
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: SpiritFieldPlot):
        await self._session.delete(entity)
        await self._session.flush()

    async def exists(self, plot_id: int) -> bool:
        entity = await self.get_by_id(plot_id)
        return entity is not None

    async def count(self) -> int:
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count(SpiritFieldPlot.id))
        )
        return result.scalar_one()

    async def get_plots_by_field_id(self, field_id: int) -> List[SpiritFieldPlot]:
        """获取灵田所有地块，按编号排序"""
        stmt = (
            select(SpiritFieldPlot)
            .where(SpiritFieldPlot.field_id == field_id)
            .order_by(SpiritFieldPlot.plot_index)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_plot_by_field_and_index(self, field_id: int, plot_index: int) -> Optional[SpiritFieldPlot]:
        """获取指定灵田的指定编号地块"""
        stmt = select(SpiritFieldPlot).where(
            SpiritFieldPlot.field_id == field_id,
            SpiritFieldPlot.plot_index == plot_index
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_empty_plots(self, field_id: int) -> List[SpiritFieldPlot]:
        """获取空闲地块"""
        stmt = (
            select(SpiritFieldPlot)
            .where(
                SpiritFieldPlot.field_id == field_id,
                SpiritFieldPlot.crop_id == None
            )
            .order_by(SpiritFieldPlot.plot_index)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_mature_plots(self, field_id: int) -> List[SpiritFieldPlot]:
        """获取已成熟的地块"""
        stmt = (
            select(SpiritFieldPlot)
            .where(
                SpiritFieldPlot.field_id == field_id,
                SpiritFieldPlot.is_mature == True,
                SpiritFieldPlot.crop_id != None
            )
            .order_by(SpiritFieldPlot.plot_index)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_planted_plots(self, field_id: int) -> List[SpiritFieldPlot]:
        """获取已种植的地块（含成熟和未成熟）"""
        stmt = (
            select(SpiritFieldPlot)
            .where(
                SpiritFieldPlot.field_id == field_id,
                SpiritFieldPlot.crop_id != None
            )
            .order_by(SpiritFieldPlot.plot_index)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def reset_all_water_counts(self):
        """重置所有地块的灌溉次数(每日定时任务用)"""
        stmt = (
            update(SpiritFieldPlot)
            .where(SpiritFieldPlot.crop_id != None)
            .values(water_count=0)
        )
        await self._session.execute(stmt)
        await self._session.flush()
