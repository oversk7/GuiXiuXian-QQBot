"""
装备实例交易服务

提供装备实例交易的核心逻辑，包括：
1. 装备交易判断
2. 装备摘要生成
3. 装备实例冻结和解冻
4. 装备交易执行
"""

from typing import List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from ..models.inventory import ItemInstance
from ..models.market_order import MarketOrder
from ..config import config


class EquipmentTradeService:
    """装备实例交易服务类"""
    
    @classmethod
    def is_equipment_trade(cls, item_id: str) -> bool:
        """判断是否为装备交易"""
        item_config = config.items_config["by_id"].get(item_id)
        return item_config and item_config.type.value == "EQUIPMENT"
    
    @classmethod
    def generate_equipment_summary(cls, equipment: ItemInstance) -> str:
        """生成装备摘要信息用于显示（含稀有度、词缀、铭文）"""
        if not equipment.is_equipment:
            return equipment.config.name

        tpl = equipment.config
        # 稀有度图标 + 名称
        parts = [tpl.get_display_name()]

        # 升阶等级
        if equipment.upgrade_level > 0:
            parts.append(f"+{equipment.upgrade_level}阶")

        # 宝石镶嵌信息（仅统计非铭文的宝石）
        if equipment.available_gem_slots > 0:
            used_slots = equipment.used_gem_slots
            total_slots = equipment.available_gem_slots
            if used_slots > 0:
                parts.append(f"[💎{used_slots}/{total_slots}]")
            else:
                parts.append(f"[🔘{total_slots}]")

        # 词缀数量
        from ..item.affix_service import get_affixes_from_equipment
        affixes = get_affixes_from_equipment(equipment.extra_attrs)
        if affixes:
            parts.append(f"🔮{len(affixes)}词缀")

        # 铭文数量
        from ..item.inscription_service import get_inscriptions_from_equipment
        inscriptions = get_inscriptions_from_equipment(equipment.gem_slots_data)
        if inscriptions:
            parts.append(f"📜{len(inscriptions)}铭文")

        # 耐久度（低于80%时显示）
        if tpl:
            durability_ratio = equipment.durability / tpl.durability
            if durability_ratio < 0.8:
                parts.append(f"🛠️{equipment.durability}/{tpl.durability}")

        return " ".join(parts)
    
    @classmethod
    async def get_player_equipment_list(cls, session: AsyncSession, player_id: str, item_id: str) -> List[ItemInstance]:
        """获取玩家指定装备的所有实例，按品质排序"""
        stmt = select(ItemInstance).where(
            and_(
                ItemInstance.player_id == player_id,
                ItemInstance.item_id == item_id,
                ItemInstance.equipped == False  # 只能挂牌未装备的装备
            )
        ).order_by(
            ItemInstance.upgrade_level.desc(),  # 升阶等级高的在前
            ItemInstance.id.asc()  # 同等级按ID排序
        )
        
        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    async def freeze_equipment(cls, session: AsyncSession, equipment: ItemInstance) -> bool:
        """冻结装备实例（标记为交易中）"""
        if equipment.equipped:
            return False
        
        # 检查是否已经在交易中
        stmt = select(MarketOrder).where(
            and_(
                MarketOrder.item_instance_id == equipment.id,
                MarketOrder.is_instance_trade == True
            )
        )
        result = await session.execute(stmt)
        existing_order = result.scalars().first()
        
        if existing_order:
            return False  # 已经在交易中
        
        # 在extra_attrs中标记为冻结状态
        extra_attrs = equipment.extra_attrs or {}
        extra_attrs["_frozen_for_trade"] = True
        equipment.extra_attrs = extra_attrs
        session.add(equipment)
        
        return True
    
    @classmethod
    async def unfreeze_equipment(cls, session: AsyncSession, equipment: ItemInstance):
        """解冻装备实例"""
        if equipment.extra_attrs:
            equipment.extra_attrs.pop("_frozen_for_trade", None)
            session.add(equipment)
    
    @classmethod
    async def transfer_equipment(cls, session: AsyncSession, equipment: ItemInstance, new_owner_id: str) -> bool:
        """转移装备所有权"""
        try:
            # 解冻装备
            await cls.unfreeze_equipment(session, equipment)
            
            # 转移所有权
            equipment.player_id = new_owner_id
            session.add(equipment)
            
            return True
        except Exception:
            return False
    
    @classmethod
    async def get_equipment_by_instance_id(cls, session: AsyncSession, instance_id: int) -> Optional[ItemInstance]:
        """根据实例ID获取装备"""
        return await session.get(ItemInstance, instance_id)
    
    @classmethod
    def format_equipment_selection_list(cls, equipment_list: List[ItemInstance]) -> List[str]:
        """格式化装备选择列表"""
        lines = []
        for i, eq in enumerate(equipment_list, 1):
            summary = cls.generate_equipment_summary(eq)
            lines.append(f"{i}. 🆔{eq.id} {summary}")
        return lines
    
    @classmethod
    def calculate_equipment_value_range(cls, equipment: ItemInstance) -> Tuple[int, int]:
        """计算装备价值范围（用于估价参考）"""
        if not equipment.is_equipment or not equipment.config:
            return 0, 0
        
        base_value = equipment.config.price
        
        # 升阶加成
        upgrade_multiplier = equipment.get_upgrade_bonus_multiplier()
        value_with_upgrade = int(base_value * upgrade_multiplier)
        
        # 宝石价值估算
        gem_value = 0
        if equipment.gem_slots_data:
            for gem_item_id in equipment.gem_slots_data.values():
                gem_config = config.items_config["by_id"].get(gem_item_id)
                if gem_config:
                    gem_value += gem_config.price
        
        # 耐久度影响
        durability_ratio = equipment.durability / equipment.config.durability if equipment.config.durability > 0 else 1.0
        durability_factor = max(0.5, durability_ratio)  # 最低50%价值
        
        total_value = int((value_with_upgrade + gem_value) * durability_factor)
        
        # 返回建议价格范围（-20% ~ +30%）
        min_price = int(total_value * 0.8)
        max_price = int(total_value * 1.3)
        
        return min_price, max_price
