"""
装备升阶系统服务（装备合成模式）

提供装备升阶的核心逻辑，包括：
1. 装备合成需求计算（多个相同装备+升阶石）
2. 升阶成功率计算
3. 升阶失败处理
4. 属性提升计算
"""

import random
from typing import Dict, Tuple, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config


class EquipmentUpgradeService:
    """装备升阶服务类（装备合成模式）"""

    # 升阶成功率配置
    SUCCESS_RATES = {
        1: 0.90, 2: 0.85, 3: 0.80,  # 1-3阶：高成功率
        4: 0.70, 5: 0.60, 6: 0.50,  # 4-6阶：中等成功率
        7: 0.40, 8: 0.30, 9: 0.20,  # 7-9阶：低成功率
        10: 0.10                     # 10阶：极低成功率
    }

    # 升阶失败后果配置
    FAILURE_CONSEQUENCES = {
        # 1-3阶：只消耗材料，装备不变
        1: {"downgrade": 0, "destroy": 0.0},
        2: {"downgrade": 0, "destroy": 0.0},
        3: {"downgrade": 0, "destroy": 0.0},

        # 4-6阶：可能降1阶
        4: {"downgrade": 1, "destroy": 0.0},
        5: {"downgrade": 1, "destroy": 0.0},
        6: {"downgrade": 1, "destroy": 0.0},

        # 7-9阶：可能降2阶或损坏
        7: {"downgrade": 2, "destroy": 0.05},
        8: {"downgrade": 2, "destroy": 0.08},
        9: {"downgrade": 2, "destroy": 0.10},

        # 10阶：可能降3阶或损坏
        10: {"downgrade": 3, "destroy": 0.15}
    }

    # 装备合成需求配置（需要的相同装备数量）
    EQUIPMENT_REQUIREMENTS = {
        1: 2,   # 1阶需要2个0阶装备
        2: 2,   # 2阶需要2个1阶装备
        3: 2,   # 3阶需要2个2阶装备
        4: 3,   # 4阶需要3个3阶装备
        5: 3,   # 5阶需要3个4阶装备
        6: 3,   # 6阶需要3个5阶装备
        7: 4,   # 7阶需要4个6阶装备
        8: 4,   # 8阶需要4个7阶装备
        9: 4,   # 9阶需要4个8阶装备
        10: 5   # 10阶需要5个9阶装备
    }
    
    @classmethod
    def get_equipment_requirements(cls, current_level: int) -> int:
        """获取升阶所需的相同装备数量"""
        if current_level >= 10:
            return 0  # 已达最高等级

        target_level = current_level + 1
        return cls.EQUIPMENT_REQUIREMENTS.get(target_level, 2)

    @classmethod
    def get_upgrade_materials(cls, current_level: int) -> Dict[str, int]:
        """获取升阶所需升阶石材料"""
        if current_level >= 10:
            return {}  # 已达最高等级

        target_level = current_level + 1
        materials = {}

        # 只需要升阶石，不需要其他材料
        if target_level <= 3:
            materials["upgrade_stone_low"] = target_level
        elif target_level <= 6:
            materials["upgrade_stone_mid"] = target_level - 3
        elif target_level <= 9:
            materials["upgrade_stone_high"] = target_level - 6
        else:  # target_level == 10
            materials["upgrade_stone_supreme"] = 1

        return materials

    @classmethod
    async def get_available_equipment_for_upgrade(cls, session: AsyncSession, player_id: str,
                                                 equipment_item_id: str, required_level: int) -> List[ItemInstance]:
        """获取可用于升阶的相同装备列表"""
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == equipment_item_id,
            ItemInstance.upgrade_level == required_level,
            ItemInstance.equipped == False  # 只能使用未装备的装备
        ).order_by(ItemInstance.durability.asc())  # 优先使用耐久度低的

        result = await session.execute(stmt)
        return result.scalars().all()
    
    @classmethod
    def get_upgrade_gold_cost(cls, current_level: int) -> int:
        """获取升阶所需金币"""
        if current_level >= 10:
            return 0

        target_level = current_level + 1
        # 金币需求大幅增加，更高的投入要求
        base_cost = 5000 * (3 ** target_level)  # 基础成本提升

        # 高阶装备额外增加成本
        if target_level >= 7:
            base_cost += 100000 * (target_level - 6)  # 7阶以上每阶额外增加10万+

        return base_cost
    
    @classmethod
    def get_success_rate(cls, current_level: int, use_protection: bool = False) -> float:
        """获取升阶成功率"""
        if current_level >= 10:
            return 0.0
        
        target_level = current_level + 1
        base_rate = cls.SUCCESS_RATES.get(target_level, 0.0)
        
        # 稳定水晶提升成功率
        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)
        
        return base_rate
    
    @classmethod
    async def can_upgrade(cls, session: AsyncSession, equipment: ItemInstance, player: Player) -> Tuple[bool, str]:
        """检查是否可以升阶（装备合成模式）"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"

        if equipment.upgrade_level >= 10:
            return False, "装备已达最高等级"

        if equipment.equipped:
            return False, "请先卸下装备再进行升阶"

        # 检查相同装备数量
        required_equipment_count = cls.get_equipment_requirements(equipment.upgrade_level)
        available_equipment = await cls.get_available_equipment_for_upgrade(
            session, player.id, equipment.item_id, equipment.upgrade_level
        )

        if len(available_equipment) < required_equipment_count:
            return False, f"需要 {required_equipment_count} 个 +{equipment.upgrade_level}阶 {equipment.config.name}，当前只有 {len(available_equipment)} 个"

        # 检查升阶石材料
        required_materials = cls.get_upgrade_materials(equipment.upgrade_level)
        for material_id, required_qty in required_materials.items():
            if not await cls._has_enough_material(session, player.id, material_id, required_qty):
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                return False, f"缺少材料：{material_name} x{required_qty}"

        # 检查金币
        required_gold = cls.get_upgrade_gold_cost(equipment.upgrade_level)
        if player.gold < required_gold:
            return False, f"金币不足，需要 {required_gold} 金币"

        return True, "可以升阶"
    
    @classmethod
    async def _has_enough_material(cls, session: AsyncSession, player_id: str, material_id: str, required_qty: int) -> bool:
        """检查是否有足够的材料"""
        from sqlalchemy import select, func
        
        stmt = select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == material_id
        )
        result = await session.execute(stmt)
        total_qty = result.scalar() or 0
        return total_qty >= required_qty
    
    @classmethod
    async def perform_upgrade(cls, session: AsyncSession, equipment: ItemInstance, player: Player, use_protection: bool = False) -> Tuple[bool, str, Dict]:
        """执行装备升阶（装备合成模式）"""
        # 再次检查是否可以升阶
        can_upgrade, reason = await cls.can_upgrade(session, equipment, player)
        if not can_upgrade:
            return False, reason, {}

        # 获取升阶信息
        current_level = equipment.upgrade_level
        target_level = current_level + 1
        required_materials = cls.get_upgrade_materials(current_level)
        required_gold = cls.get_upgrade_gold_cost(current_level)
        success_rate = cls.get_success_rate(current_level, use_protection)

        # 获取需要消耗的装备
        required_equipment_count = cls.get_equipment_requirements(current_level)
        available_equipment = await cls.get_available_equipment_for_upgrade(
            session, player.id, equipment.item_id, current_level
        )

        # 选择要消耗的装备（排除主装备本身）
        equipment_to_consume = []
        for eq in available_equipment:
            if eq.id != equipment.id and len(equipment_to_consume) < required_equipment_count - 1:
                equipment_to_consume.append(eq)

        if len(equipment_to_consume) < required_equipment_count - 1:
            return False, "可用装备数量不足", {}

        # 消耗升阶石材料
        consumed_materials = {}
        for material_id, required_qty in required_materials.items():
            success = await ItemInstance.consume_item(session, player.id, material_id, required_qty)
            if not success:
                await session.rollback()
                return False, "扣除材料失败", {}
            consumed_materials[material_id] = required_qty

        # 消耗稳定水晶（如果使用）
        if use_protection:
            protection_success = await ItemInstance.consume_item(session, player.id, "stabilizer_crystal", 1)
            if not protection_success:
                await session.rollback()
                return False, "缺少稳定水晶", {}
            consumed_materials["stabilizer_crystal"] = 1

        # 消耗装备
        consumed_equipment_names = []
        for eq in equipment_to_consume:
            consumed_equipment_names.append(f"{eq.config.name}(ID:{eq.id})")
            await session.delete(eq)

        player.gold -= required_gold
        
        # 判断升阶结果
        is_success = random.random() < success_rate
        result_info = {
            "target_level": target_level,
            "success_rate": success_rate,
            "consumed_materials": consumed_materials,
            "consumed_equipment": consumed_equipment_names,
            "consumed_gold": required_gold,
            "used_protection": use_protection
        }
        
        if is_success:
            # 升阶成功
            equipment.upgrade_level = target_level
            result_info["result"] = "success"
            result_info["new_level"] = target_level
            return True, f"🎉 升阶成功！装备升级到 +{target_level} 阶", result_info
        else:
            # 升阶失败
            consequence = cls.FAILURE_CONSEQUENCES.get(target_level, {"downgrade": 0, "destroy": 0.0})
            
            # 稳定水晶保护
            if use_protection:
                result_info["result"] = "failed_protected"
                return False, f"💔 升阶失败，但稳定水晶保护了装备", result_info
            
            # 检查是否损坏
            if random.random() < consequence["destroy"]:
                # 装备损坏前，先回收镶嵌的宝石
                recovered_gems = await cls._recover_gems_from_equipment(session, equipment, player)

                # 删除装备
                await session.delete(equipment)
                result_info["result"] = "destroyed"

                # 构建消息
                message = "💥 升阶失败，装备已损坏！"
                if recovered_gems:
                    message += f"\n💎 随机回收镶嵌物：{', '.join(recovered_gems)}"
                else:
                    message += "\n💀 装备上没有镶嵌物可回收"

                return False, message, result_info
            
            # 装备降级
            downgrade_levels = consequence["downgrade"]
            if downgrade_levels > 0:
                new_level = max(0, current_level - downgrade_levels)
                equipment.upgrade_level = new_level
                result_info["result"] = "downgraded"
                result_info["new_level"] = new_level
                return False, f"💔 升阶失败，装备降级到 +{new_level} 阶", result_info
            else:
                result_info["result"] = "failed_no_change"
                return False, f"💔 升阶失败，装备等级不变", result_info

    @classmethod
    async def _recover_gems_from_equipment(cls, session: AsyncSession, equipment: ItemInstance, player: Player) -> List[str]:
        """
        从装备中随机回收一个镶嵌的宝石
        返回回收的宝石名称列表
        """
        import random
        from ..models.inventory import ItemInstance
        from ..config import config

        recovered_gems = []

        if not equipment.is_equipment or not equipment.gem_slots_data:
            return recovered_gems

        # 收集所有镶嵌的宝石
        available_gems = []
        for slot_index, gem_item_id in equipment.gem_slots_data.items():
            if gem_item_id:
                available_gems.append(gem_item_id)

        # 如果没有镶嵌的宝石，直接返回
        if not available_gems:
            return recovered_gems

        # 随机选择一个宝石进行回收
        selected_gem_id = random.choice(available_gems)
        gem_config = config.items_config["by_id"].get(selected_gem_id)
        gem_name = gem_config.name if gem_config else selected_gem_id

        try:
            # 尝试将宝石添加到背包
            await ItemInstance.add_item(session, player.id, selected_gem_id, 1)
            recovered_gems.append(gem_name)
        except ValueError:
            # 背包空间不足，转换为金币
            if gem_config and gem_config.price:
                gold_value = gem_config.price
                player.gold += gold_value
                recovered_gems.append(f"{gem_name}(转为{gold_value}金币)")
            else:
                # 没有价格配置，按默认价格处理
                default_gold = 1000
                player.gold += default_gold
                recovered_gems.append(f"{gem_name}(转为{default_gold}金币)")

        return recovered_gems
