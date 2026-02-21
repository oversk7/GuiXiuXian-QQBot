from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ...models.lower_world import LowerWorldStronghold


class LowerWorldRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_player_id(self, player_id: str) -> Optional[LowerWorldStronghold]:
        result = await self._session.execute(
            select(LowerWorldStronghold).where(LowerWorldStronghold.player_id == player_id)
        )
        return result.scalar_one_or_none()

    async def create(self, stronghold: LowerWorldStronghold) -> LowerWorldStronghold:
        self._session.add(stronghold)
        await self._session.flush()
        return stronghold

    async def get_all(self) -> List[LowerWorldStronghold]:
        """获取所有山寨（用于定时任务）"""
        result = await self._session.execute(select(LowerWorldStronghold))
        return result.scalars().all()
