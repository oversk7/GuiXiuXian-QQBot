"""
装备属性来源实现

读取装备的_persist_bonus，用于breakdown详细展示
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..interfaces import IAttributeSource, AttributeBonus


class EquipmentAttributeSource(IAttributeSource):
    """
    装备属性来源

    设计说明:
    1. 装备加成已通过_persist_bonus机制持久化到Player属性
    2. 本类主要用于提供breakdown详细展示
    3. 读取所有已穿戴装备的_persist_bonus汇总

    _persist_bonus机制:
    - 优势: 避免每次战斗重新计算装备加成
    - 实现: plugins/xiuxian_game/item/equipment_commands.py:96-175
    - 触发: 穿戴/卸下装备、使用丹药后
    """

    @property
    def source_name(self) -> str:
        return "equipment"

    async def calculate_bonus(
        self,
        player,
        session: AsyncSession
    ) -> AttributeBonus:
        """
        计算装备属性加成

        通过读取所有已穿戴装备的_persist_bonus汇总

        Args:
            player: Player实例
            session: 数据库会话

        Returns:
            AttributeBonus: 装备加成总和
        """
        # 导入放在方法内部，避免循环依赖
        from ....models.inventory import ItemInstance

        # 查询所有已穿戴的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True
        )
        result = await session.execute(stmt)
        equipped_items = result.scalars().all()

        # 汇总所有装备的_persist_bonus
        total_bonus = AttributeBonus()

        for item in equipped_items:
            persist_bonus = item.extra_attrs.get('_persist_bonus', {})

            if persist_bonus:
                # 累加各属性
                total_bonus.attack += persist_bonus.get('attack', 0)
                total_bonus.defense += persist_bonus.get('defense', 0)
                total_bonus.hp += persist_bonus.get('hp', 0)
                total_bonus.max_hp += persist_bonus.get('max_hp', 0)
                total_bonus.mp += persist_bonus.get('mp', 0)
                total_bonus.max_mp += persist_bonus.get('max_mp', 0)
                total_bonus.agility += persist_bonus.get('agility', 0)
                total_bonus.luck += persist_bonus.get('luck', 0)
                total_bonus.crit_rate += persist_bonus.get('crit_rate', 0.0)
                total_bonus.crit_damage += persist_bonus.get('crit_damage', 0.0)
                total_bonus.dodge_rate += persist_bonus.get('dodge_rate', 0.0)
                total_bonus.accuracy += persist_bonus.get('accuracy', 0.0)

        return total_bonus

    async def get_equipment_detail(
        self,
        player,
        session: AsyncSession
    ) -> list[dict]:
        """
        获取装备详细信息（用于UI展示）

        Returns:
            List[Dict]: 每件装备的名称和加成
        """
        from ....models.inventory import ItemInstance

        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True
        )
        result = await session.execute(stmt)
        equipped_items = result.scalars().all()

        details = []
        for item in equipped_items:
            persist_bonus = item.extra_attrs.get('_persist_bonus', {})
            if persist_bonus:
                details.append({
                    'item_id': item.id,
                    'item_name': item.item_id,  # 需要从ItemConfig获取实际名称
                    'slot': item.extra_attrs.get('slot', 'unknown'),
                    'bonus': persist_bonus,
                })

        return details
