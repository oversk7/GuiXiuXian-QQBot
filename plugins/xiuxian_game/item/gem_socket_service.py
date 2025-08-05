"""
宝石镶嵌系统服务

提供宝石镶嵌的核心逻辑，包括：
1. 宝石镶嵌
2. 宝石拆卸
3. 孔位管理
4. 属性计算
"""

import random
from typing import Dict, Tuple, Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config


class GemSocketService:
    """宝石镶嵌服务类"""
    
    # 镶嵌成本配置
    SOCKET_COSTS = {
        "gem_hammer": 1,  # 镶嵌锤消耗
        "gold": 1000      # 基础金币消耗
    }
    
    # 拆卸成本配置
    REMOVE_COSTS = {
        "gem_chisel": 1,  # 拆卸凿消耗
        "gold": 500       # 基础金币消耗
    }
    
    # 拆卸风险配置
    REMOVE_RISKS = {
        "gem_destroy_rate": 0.15,      # 宝石损坏概率
        "equipment_damage_rate": 0.05   # 装备损伤概率
    }
    
    @classmethod
    def is_socketable_item(cls, item_id: str) -> bool:
        """检查物品是否可镶嵌"""
        from ..config import config
        item_config = config.items_config["by_id"].get(item_id)
        return item_config and item_config.type.value == "GEM"
    
    @classmethod
    def get_gem_type(cls, item_id: str) -> str:
        """获取镶嵌物品类型"""
        if item_id.endswith("_gem"):
            return "宝石"
        elif item_id.endswith("_bead"):
            return "佛珠"
        elif item_id.endswith("_rune"):
            return "符文"
        return "未知"
    
    @classmethod
    async def can_socket_gem(cls, session: AsyncSession, equipment: ItemInstance, gem_item_id: str, slot_index: int, player: Player) -> Tuple[bool, str]:
        """检查是否可以镶嵌宝石"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"
        
        if equipment.equipped:
            return False, "请先卸下装备再进行镶嵌"
        
        # 检查孔位
        if slot_index < 0 or slot_index >= equipment.available_gem_slots:
            return False, f"无效的孔位，装备只有 {equipment.available_gem_slots} 个孔位"
        
        # 检查孔位是否已占用
        if equipment.get_gem_in_slot(slot_index) is not None:
            return False, f"孔位 {slot_index + 1} 已被占用"
        
        # 检查镶嵌物品是否可用
        if not cls.is_socketable_item(gem_item_id):
            return False, "该物品不能镶嵌到装备上"
        
        # 检查是否拥有镶嵌物品
        if not await cls._has_item(session, player.id, gem_item_id, 1):
            gem_config = config.items_config["by_id"].get(gem_item_id)
            gem_name = gem_config.name if gem_config else gem_item_id
            return False, f"缺少镶嵌物品：{gem_name}"
        
        # 检查镶嵌工具
        if not await cls._has_item(session, player.id, "gem_hammer", 1):
            return False, "缺少镶嵌锤"
        
        # 检查金币
        if player.gold < cls.SOCKET_COSTS["gold"]:
            return False, f"金币不足，需要 {cls.SOCKET_COSTS['gold']} 金币"
        
        return True, "可以镶嵌"
    
    @classmethod
    async def socket_gem(cls, session: AsyncSession, equipment: ItemInstance, gem_item_id: str, slot_index: int, player: Player) -> Tuple[bool, str]:
        """镶嵌宝石"""
        # 检查是否可以镶嵌
        can_socket, reason = await cls.can_socket_gem(session, equipment, gem_item_id, slot_index, player)
        if not can_socket:
            return False, reason
        
        # 消耗材料
        gem_success = await ItemInstance.consume_item(session, player.id, gem_item_id, 1)
        hammer_success = await ItemInstance.consume_item(session, player.id, "gem_hammer", 1)
        
        if not gem_success or not hammer_success:
            await session.rollback()
            return False, "消耗材料失败"
        
        # 消耗金币
        player.gold -= cls.SOCKET_COSTS["gold"]
        
        # 镶嵌宝石
        equipment.set_gem_in_slot(slot_index, gem_item_id)
        
        gem_config = config.items_config["by_id"].get(gem_item_id)
        gem_name = gem_config.name if gem_config else gem_item_id
        gem_type = cls.get_gem_type(gem_item_id)
        
        return True, f"✨ 成功镶嵌 {gem_type}：{gem_name} 到孔位 {slot_index + 1}"
    
    @classmethod
    async def can_remove_gem(cls, session: AsyncSession, equipment: ItemInstance, slot_index: int, player: Player) -> Tuple[bool, str]:
        """检查是否可以拆卸宝石"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"
        
        if equipment.equipped:
            return False, "请先卸下装备再进行拆卸"
        
        # 检查孔位
        if slot_index < 0 or slot_index >= equipment.available_gem_slots:
            return False, f"无效的孔位，装备只有 {equipment.available_gem_slots} 个孔位"
        
        # 检查孔位是否有宝石
        gem_item_id = equipment.get_gem_in_slot(slot_index)
        if gem_item_id is None:
            return False, f"孔位 {slot_index + 1} 没有镶嵌物品"
        
        # 检查拆卸工具
        if not await cls._has_item(session, player.id, "gem_chisel", 1):
            return False, "缺少拆卸凿"
        
        # 检查金币
        if player.gold < cls.REMOVE_COSTS["gold"]:
            return False, f"金币不足，需要 {cls.REMOVE_COSTS['gold']} 金币"
        
        return True, "可以拆卸"
    
    @classmethod
    async def remove_gem(cls, session: AsyncSession, equipment: ItemInstance, slot_index: int, player: Player) -> Tuple[bool, str]:
        """拆卸宝石"""
        # 检查是否可以拆卸
        can_remove, reason = await cls.can_remove_gem(session, equipment, slot_index, player)
        if not can_remove:
            return False, reason
        
        gem_item_id = equipment.get_gem_in_slot(slot_index)
        gem_config = config.items_config["by_id"].get(gem_item_id)
        gem_name = gem_config.name if gem_config else gem_item_id
        gem_type = cls.get_gem_type(gem_item_id)
        
        # 消耗工具和金币
        chisel_success = await ItemInstance.consume_item(session, player.id, "gem_chisel", 1)
        if not chisel_success:
            await session.rollback()
            return False, "消耗拆卸凿失败"
        
        player.gold -= cls.REMOVE_COSTS["gold"]
        
        # 拆卸风险判定
        gem_destroyed = random.random() < cls.REMOVE_RISKS["gem_destroy_rate"]
        equipment_damaged = random.random() < cls.REMOVE_RISKS["equipment_damage_rate"]
        
        # 移除宝石
        equipment.set_gem_in_slot(slot_index, None)
        
        result_messages = []
        
        if gem_destroyed:
            result_messages.append(f"💔 {gem_type} {gem_name} 在拆卸过程中损坏了")
        else:
            # 返还宝石到背包
            try:
                await ItemInstance.add_item(session, player.id, gem_item_id, 1)
                result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
            except ValueError:
                result_messages.append(f"💔 背包空间不足，{gem_type} {gem_name} 丢失了")
        
        if equipment_damaged:
            # 装备耐久度损失
            damage = max(1, equipment.config.durability // 10)  # 损失10%耐久度
            equipment.durability = max(0, equipment.durability - damage)
            result_messages.append(f"⚠️ 装备在拆卸过程中受损，耐久度 -{damage}")
        
        return True, "\n".join(result_messages)
    
    @classmethod
    async def get_equipment_gem_info(cls, equipment: ItemInstance) -> List[Dict]:
        """获取装备的宝石镶嵌信息"""
        if not equipment.is_equipment:
            return []
        
        gem_info = []
        for slot_index in range(equipment.available_gem_slots):
            gem_item_id = equipment.get_gem_in_slot(slot_index)
            
            slot_info = {
                "slot_index": slot_index,
                "slot_number": slot_index + 1,
                "is_empty": gem_item_id is None
            }
            
            if gem_item_id:
                gem_config = config.items_config["by_id"].get(gem_item_id)
                slot_info.update({
                    "gem_item_id": gem_item_id,
                    "gem_name": gem_config.name if gem_config else gem_item_id,
                    "gem_type": cls.get_gem_type(gem_item_id),
                    "gem_config": gem_config
                })
            
            gem_info.append(slot_info)
        
        return gem_info
    
    @classmethod
    async def _has_item(cls, session: AsyncSession, player_id: str, item_id: str, required_qty: int) -> bool:
        """检查是否拥有指定数量的物品"""
        from sqlalchemy import func
        
        stmt = select(func.sum(ItemInstance.quantity)).where(
            ItemInstance.player_id == player_id,
            ItemInstance.item_id == item_id
        )
        result = await session.execute(stmt)
        total_qty = result.scalar() or 0
        return total_qty >= required_qty
