"""
镶嵌物升级系统服务

提供镶嵌物升级的核心逻辑，包括：
1. 镶嵌物合成需求计算（多个相同镶嵌物+升阶石）
2. 升级成功率计算
3. 升级失败处理
4. 属性提升计算
"""

import random
from typing import Dict, Tuple, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config


class GemUpgradeService:
    """镶嵌物升级服务类"""
    
    # 升级成功率配置
    SUCCESS_RATES = {
        1: 0.95,   # 1->2级 95%
        2: 0.90,   # 2->3级 90%
        3: 0.85,   # 3->4级 85%
        4: 0.80,   # 4->5级 80%
        5: 0.75,   # 5->6级 75%
        6: 0.70,   # 6->7级 70%
        7: 0.65,   # 7->8级 65%
        8: 0.60,   # 8->9级 60%
        9: 0.50,   # 9->10级 50%
    }
    
    # 升级金币消耗
    UPGRADE_GOLD_COSTS = {
        1: 5000,   2: 8000,   3: 12000,
        4: 18000,  5: 25000,  6: 35000,
        7: 50000,  8: 70000,  9: 100000
    }
    
    @classmethod
    def is_upgradeable_gem(cls, item_id: str) -> bool:
        """检查物品是否是可升级的镶嵌物"""
        from ..config import config
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config or item_config.type.value != "GEM":
            return False
        
        # 检查是否是分级镶嵌物（包含_数字后缀）
        parts = item_id.split('_')
        if len(parts) < 3:  # 例如：strength_gem_1
            return False
        
        try:
            level = int(parts[-1])
            return 1 <= level <= 10
        except ValueError:
            return False
    
    @classmethod
    def get_gem_level(cls, item_id: str) -> int:
        """获取镶嵌物等级"""
        if not cls.is_upgradeable_gem(item_id):
            return 0
        
        parts = item_id.split('_')
        try:
            return int(parts[-1])
        except (ValueError, IndexError):
            return 0
    
    @classmethod
    def get_gem_base_type(cls, item_id: str) -> str:
        """获取镶嵌物基础类型（不含等级）"""
        if not cls.is_upgradeable_gem(item_id):
            return ""
        
        parts = item_id.split('_')
        if len(parts) >= 3:
            return '_'.join(parts[:-1])  # 去掉最后的等级数字
        return ""
    
    @classmethod
    def get_next_level_gem_id(cls, item_id: str) -> Optional[str]:
        """获取下一级镶嵌物的ID"""
        current_level = cls.get_gem_level(item_id)
        if current_level == 0 or current_level >= 10:
            return None

        base_type = cls.get_gem_base_type(item_id)
        if not base_type:
            return None

        next_gem_id = f"{base_type}_{current_level + 1}"

        # 验证下一级镶嵌物是否存在
        if config.items_config["by_id"].get(next_gem_id):
            return next_gem_id
        return None

    @classmethod
    def get_previous_level_gem_id(cls, item_id: str) -> Optional[str]:
        """获取前一级镶嵌物的ID"""
        current_level = cls.get_gem_level(item_id)
        if current_level <= 1:
            return None  # 1级镶嵌物没有前一级

        base_type = cls.get_gem_base_type(item_id)
        if not base_type:
            return None

        prev_gem_id = f"{base_type}_{current_level - 1}"

        # 验证前一级镶嵌物是否存在
        if config.items_config["by_id"].get(prev_gem_id):
            return prev_gem_id
        return None
    
    @classmethod
    def get_upgrade_materials(cls, current_level: int) -> Dict[str, int]:
        """获取升级所需升阶石材料"""
        if current_level >= 10:
            return {}  # 已达最高等级

        target_level = current_level + 1
        materials = {}

        # 根据目标等级确定所需升阶石
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
    def get_required_gem_count(cls, current_level: int) -> int:
        """获取升级所需的相同镶嵌物数量"""
        if current_level >= 10:
            return 0
        
        # 升级需要的镶嵌物数量（包括自己）
        if current_level <= 3:
            return 2  # 需要2个相同镶嵌物
        elif current_level <= 6:
            return 3  # 需要3个相同镶嵌物
        elif current_level <= 9:
            return 4  # 需要4个相同镶嵌物
        else:
            return 5  # 9->10级需要5个
    
    @classmethod
    def get_upgrade_gold_cost(cls, current_level: int) -> int:
        """获取升级所需金币"""
        return cls.UPGRADE_GOLD_COSTS.get(current_level, 0)
    
    @classmethod
    def get_success_rate(cls, current_level: int, use_protection: bool = False, player_luck: int = 0) -> float:
        """获取升级成功率"""
        base_rate = cls.SUCCESS_RATES.get(current_level, 0.0)

        # 运气加成（最多20%）
        from ..utils import luck_prob
        luck_bonus = luck_prob(player_luck) * 0.2  # 运气值转换为0-20%的加成
        base_rate = min(1.0, base_rate + luck_bonus)

        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)  # 稳定水晶增加20%成功率
        return base_rate
    
    @classmethod
    async def _has_enough_material(cls, session: AsyncSession, player_id: str, material_id: str, required_qty: int) -> bool:
        """检查是否有足够的材料"""
        stmt = select(ItemInstance.quantity).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == material_id
        )
        result = await session.execute(stmt)
        owned_qty = sum(result.scalars().all())
        return owned_qty >= required_qty
    
    @classmethod
    async def _has_enough_gems(cls, session: AsyncSession, player_id: str, gem_id: str, required_qty: int) -> bool:
        """检查是否有足够的镶嵌物"""
        stmt = select(ItemInstance.quantity).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == gem_id
        )
        result = await session.execute(stmt)
        owned_qty = sum(result.scalars().all())
        return owned_qty >= required_qty
    
    @classmethod
    async def can_upgrade_gem(cls, session: AsyncSession, gem_id: str, player: Player, use_protection: bool = False) -> Tuple[bool, str]:
        """检查是否可以升级镶嵌物"""
        if not cls.is_upgradeable_gem(gem_id):
            return False, "该物品不是可升级的镶嵌物"
        
        current_level = cls.get_gem_level(gem_id)
        if current_level >= 10:
            return False, "镶嵌物已达最高等级"
        
        next_gem_id = cls.get_next_level_gem_id(gem_id)
        if not next_gem_id:
            return False, "找不到下一级镶嵌物配置"
        
        # 检查镶嵌物数量
        required_gem_count = cls.get_required_gem_count(current_level)
        if not await cls._has_enough_gems(session, player.id, gem_id, required_gem_count):
            return False, f"镶嵌物数量不足，需要 {required_gem_count} 个"
        
        # 检查升阶石材料
        required_materials = cls.get_upgrade_materials(current_level)
        for material_id, required_qty in required_materials.items():
            if not await cls._has_enough_material(session, player.id, material_id, required_qty):
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                return False, f"缺少材料：{material_name} x{required_qty}"
        
        # 检查稳定水晶（如果使用）
        if use_protection:
            if not await cls._has_enough_material(session, player.id, "stabilizer_crystal", 1):
                return False, "缺少稳定水晶"
        
        # 检查金币
        required_gold = cls.get_upgrade_gold_cost(current_level)
        if player.gold < required_gold:
            return False, f"金币不足，需要 {required_gold} 金币"
        
        return True, "可以升级"

    @classmethod
    async def upgrade_gem(cls, session: AsyncSession, gem_id: str, player: Player, use_protection: bool = False) -> Tuple[bool, str, Dict[str, int]]:
        """
        升级镶嵌物
        返回: (成功标志, 消息, 消耗的材料字典)
        """
        # 检查是否可以升级
        can_upgrade, reason = await cls.can_upgrade_gem(session, gem_id, player, use_protection)
        if not can_upgrade:
            return False, reason, {}

        current_level = cls.get_gem_level(gem_id)
        next_gem_id = cls.get_next_level_gem_id(gem_id)
        required_gem_count = cls.get_required_gem_count(current_level)
        required_materials = cls.get_upgrade_materials(current_level)
        required_gold = cls.get_upgrade_gold_cost(current_level)

        # 消耗金币
        player.gold -= required_gold

        # 消耗镶嵌物
        gem_success = await ItemInstance.consume_item(session, player.id, gem_id, required_gem_count)
        if not gem_success:
            await session.rollback()
            return False, "扣除镶嵌物失败", {}

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

        # 计算成功率并判定结果
        success_rate = cls.get_success_rate(current_level, use_protection, player.luck)
        is_success = random.random() < success_rate

        gem_config = config.items_config["by_id"].get(gem_id)
        gem_name = gem_config.name if gem_config else gem_id

        if is_success:
            # 升级成功，给予下一级镶嵌物
            try:
                await ItemInstance.add_item(session, player.id, next_gem_id, 1)
                next_gem_config = config.items_config["by_id"].get(next_gem_id)
                next_gem_name = next_gem_config.name if next_gem_config else next_gem_id

                message = f"🎉 升级成功！\n✨ {gem_name} → {next_gem_name}\n💰 消耗金币: {required_gold}"
                return True, message, consumed_materials
            except ValueError as e:
                await session.rollback()
                return False, f"升级成功但添加物品失败：{e}", {}
        else:
            # 升级失败
            if use_protection:
                # 使用了稳定水晶，返还一个原等级镶嵌物
                try:
                    await ItemInstance.add_item(session, player.id, gem_id, 1)
                    message = f"💔 升级失败！\n🛡️ 稳定水晶保护生效，返还 {gem_name}\n💰 消耗金币: {required_gold}"
                except ValueError:
                    message = f"💔 升级失败！\n⚠️ 背包空间不足，{gem_name} 丢失了\n💰 消耗金币: {required_gold}"
            else:
                # 没有保护，镶嵌物降阶
                prev_gem_id = cls.get_previous_level_gem_id(gem_id)
                if prev_gem_id:
                    # 有前一级，降阶到前一级
                    try:
                        await ItemInstance.add_item(session, player.id, prev_gem_id, 1)
                        prev_gem_config = config.items_config["by_id"].get(prev_gem_id)
                        prev_gem_name = prev_gem_config.name if prev_gem_config else prev_gem_id
                        message = f"💔 升级失败！\n📉 {gem_name} 降阶为 {prev_gem_name}\n💰 消耗金币: {required_gold}"
                    except ValueError:
                        message = f"💔 升级失败！\n⚠️ 背包空间不足，镶嵌物丢失了\n💰 消耗金币: {required_gold}"
                else:
                    # 已经是1级，无法降阶，直接消失
                    message = f"💔 升级失败！\n💀 {gem_name} 已是最低等级，升级失败后消失\n💰 消耗金币: {required_gold}"

            return False, message, consumed_materials

    @classmethod
    def get_gem_display_info(cls, gem_id: str, player_luck: int = 0) -> Dict[str, any]:
        """获取镶嵌物显示信息"""
        if not cls.is_upgradeable_gem(gem_id):
            return {}

        current_level = cls.get_gem_level(gem_id)
        next_gem_id = cls.get_next_level_gem_id(gem_id)

        gem_config = config.items_config["by_id"].get(gem_id)
        if not gem_config:
            return {}

        info = {
            "current_level": current_level,
            "current_name": gem_config.name,
            "can_upgrade": current_level < 10 and next_gem_id is not None,
            "required_gem_count": cls.get_required_gem_count(current_level),
            "required_materials": cls.get_upgrade_materials(current_level),
            "required_gold": cls.get_upgrade_gold_cost(current_level),
            "success_rate": cls.get_success_rate(current_level, False, player_luck),
            "success_rate_with_protection": cls.get_success_rate(current_level, True, player_luck)
        }

        if next_gem_id:
            next_gem_config = config.items_config["by_id"].get(next_gem_id)
            if next_gem_config:
                info["next_level"] = current_level + 1
                info["next_name"] = next_gem_config.name

        return info
