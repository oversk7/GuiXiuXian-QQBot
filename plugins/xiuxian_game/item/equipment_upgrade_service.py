"""
装备升阶系统服务

提供装备升阶的核心逻辑，包括：
1. 升阶材料需求计算
2. 升阶成功率计算
3. 升阶失败处理
4. 属性提升计算
"""

import random
from typing import Dict, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config


class EquipmentUpgradeService:
    """装备升阶服务类"""
    
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
    
    @classmethod
    def get_upgrade_materials(cls, current_level: int) -> Dict[str, int]:
        """获取升阶所需材料"""
        if current_level >= 10:
            return {}  # 已达最高等级
        
        target_level = current_level + 1
        materials = {}
        
        # 基础材料需求（随等级递增）
        base_materials = {
            "spirit_bone": 10 + target_level * 5,
            "strange_stone": 2 + target_level,
        }
        
        # 升阶石需求
        if target_level <= 3:
            materials["upgrade_stone_low"] = target_level
        elif target_level <= 6:
            materials["upgrade_stone_mid"] = target_level - 3
        elif target_level <= 9:
            materials["upgrade_stone_high"] = target_level - 6
        else:  # target_level == 10
            materials["upgrade_stone_supreme"] = 1
        
        # 添加基础材料
        materials.update(base_materials)
        
        # 高阶需要额外稀有材料
        if target_level >= 7:
            materials["flesh_crystal"] = target_level - 5
        if target_level >= 9:
            materials["soul_crystal"] = target_level - 7
        if target_level == 10:
            materials["demon_heart"] = 1
        
        return materials
    
    @classmethod
    def get_upgrade_gold_cost(cls, current_level: int) -> int:
        """获取升阶所需金币"""
        if current_level >= 10:
            return 0
        
        target_level = current_level + 1
        # 金币需求指数增长
        return 1000 * (2 ** target_level)
    
    @classmethod
    def get_success_rate(cls, current_level: int, use_protection: bool = False) -> float:
        """获取升阶成功率"""
        if current_level >= 10:
            return 0.0
        
        target_level = current_level + 1
        base_rate = cls.SUCCESS_RATES.get(target_level, 0.0)
        
        # 护身符提升成功率
        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)
        
        return base_rate
    
    @classmethod
    async def can_upgrade(cls, session: AsyncSession, equipment: ItemInstance, player: Player) -> Tuple[bool, str]:
        """检查是否可以升阶"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"
        
        if equipment.upgrade_level >= 10:
            return False, "装备已达最高等级"
        
        if equipment.equipped:
            return False, "请先卸下装备再进行升阶"
        
        # 检查材料
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
        """执行装备升阶"""
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
        
        # 消耗材料和金币
        consumed_materials = {}
        for material_id, required_qty in required_materials.items():
            success = await ItemInstance.consume_item(session, player.id, material_id, required_qty)
            if not success:
                await session.rollback()
                return False, "扣除材料失败", {}
            consumed_materials[material_id] = required_qty
        
        # 消耗护身符（如果使用）
        if use_protection:
            protection_success = await ItemInstance.consume_item(session, player.id, "protection_charm", 1)
            if not protection_success:
                await session.rollback()
                return False, "缺少护身符", {}
            consumed_materials["protection_charm"] = 1
        
        player.gold -= required_gold
        
        # 判断升阶结果
        is_success = random.random() < success_rate
        result_info = {
            "target_level": target_level,
            "success_rate": success_rate,
            "consumed_materials": consumed_materials,
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
            
            # 护身符保护
            if use_protection:
                result_info["result"] = "failed_protected"
                return False, f"💔 升阶失败，但护身符保护了装备", result_info
            
            # 检查是否损坏
            if random.random() < consequence["destroy"]:
                # 装备损坏
                await session.delete(equipment)
                result_info["result"] = "destroyed"
                return False, f"💥 升阶失败，装备已损坏！", result_info
            
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
