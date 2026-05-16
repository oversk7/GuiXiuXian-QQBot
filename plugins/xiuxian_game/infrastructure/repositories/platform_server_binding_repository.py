"""平台区服绑定仓储。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.platform_server_binding import PlatformServerBinding


class PlatformServerBindingRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_owner(self, owner_platform_id: str) -> PlatformServerBinding | None:
        stmt = select(PlatformServerBinding).where(
            PlatformServerBinding.owner_platform_id == owner_platform_id
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def save(self, binding: PlatformServerBinding) -> PlatformServerBinding:
        self._session.add(binding)
        await self._session.flush()
        return binding
