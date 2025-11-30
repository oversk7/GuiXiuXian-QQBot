"""
VIP装备加成仓储实现
"""

from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.vip_equipment_bonus import VIPEquipmentBonus


class VIPEquipmentBonusRepository(IRepository[VIPEquipmentBonus]):
    """VIP装备加成仓储实现"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, record_id: int) -> Optional[VIPEquipmentBonus]:
        stmt = select(VIPEquipmentBonus).where(VIPEquipmentBonus.id == record_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_player_id(self, player_id: str) -> Optional[VIPEquipmentBonus]:
        """
        根据玩家ID获取VIP装备加成记录

        Args:
            player_id: 玩家ID

        Returns:
            VIPEquipmentBonus: 加成记录，如果不存在返回None
        """
        stmt = select(VIPEquipmentBonus).where(VIPEquipmentBonus.player_id == player_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, record: VIPEquipmentBonus) -> VIPEquipmentBonus:
        self._session.add(record)
        await self._session.flush()
        return record

    async def update(self, record: VIPEquipmentBonus) -> VIPEquipmentBonus:
        self._session.add(record)
        return record

    async def delete(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        if record:
            await self._session.delete(record)
            return True
        return False

    async def exists(self, record_id: int) -> bool:
        record = await self.get_by_id(record_id)
        return record is not None

    async def count(self) -> int:
        # TODO: 实现
        return 0

    async def get_or_create(self, player_id: str) -> VIPEquipmentBonus:
        """
        获取或创建玩家的VIP装备加成记录（封装VIPEquipmentBonus.get_or_create）

        Args:
            player_id: 玩家ID

        Returns:
            VIPEquipmentBonus: 加成记录

        Note:
            此方法封装VIPEquipmentBonus.get_or_create类方法，保持向后兼容
        """
        return await VIPEquipmentBonus.get_or_create(self._session, player_id)

    async def add_bonus(
        self, player_id: str, attr_name: str, value: int
    ) -> VIPEquipmentBonus:
        """
        为玩家增加指定属性的VIP装备加成

        Args:
            player_id: 玩家ID
            attr_name: 属性名称（如"attack", "max_mp"等）
            value: 加成值

        Returns:
            VIPEquipmentBonus: 更新后的加成记录
        """
        record = await self.get_or_create(player_id)
        record.add_bonus(attr_name, value)
        return record

    async def get_total_bonus(self, player_id: str) -> dict:
        """
        获取玩家所有VIP装备属性加成

        Args:
            player_id: 玩家ID

        Returns:
            dict: 属性加成字典（如{"attack": 100, "max_mp": 80}）
        """
        record = await self.get_by_player_id(player_id)
        if not record:
            return {}
        return record.get_total_bonus()
