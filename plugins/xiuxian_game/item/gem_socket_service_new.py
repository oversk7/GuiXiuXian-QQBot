"""
宝石镶嵌系统服务 (DI架构版本)

改造说明:
- 混合模式设计：3个纯计算方法保持@staticmethod + 5个数据访问方法转为实例方法
- 通过构造函数注入ItemRepository和PlayerRepository依赖
- 移除内部rollback()调用，异常直接抛出由外层safe_session()处理
- 保持业务逻辑完全一致
"""

import random
from typing import Dict, Tuple, List
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


class GemSocketService:
    """宝石镶嵌服务类 (DI架构版本)"""

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

    def __init__(
        self,
        item_repo: ItemRepository,
        player_repo: PlayerRepository,
    ):
        """
        初始化宝石镶嵌服务

        Args:
            item_repo: 物品仓储
            player_repo: 玩家仓储
        """
        self._item_repo = item_repo
        self._player_repo = player_repo

    # ==================== 静态方法（纯计算，无数据访问） ====================

    @staticmethod
    def is_socketable_item(item_id: str) -> bool:
        """
        检查物品是否可镶嵌

        Args:
            item_id: 物品ID

        Returns:
            是否可镶嵌

        对应原代码:
            gem_socket_service.py Line 42-46
        """
        item_config = config.items_config["by_id"].get(item_id)
        return item_config and item_config.type.value in ("GEM", "INSCRIPTION")

    @staticmethod
    def get_gem_type(item_id: str) -> str:
        """
        获取镶嵌物品类型

        Args:
            item_id: 物品ID

        Returns:
            物品类型名称

        对应原代码:
            gem_socket_service.py Line 48-81
        """
        # 铭文类型
        if item_id.startswith("inscription_"):
            return "铭文"
        # 处理等级化镶嵌物（如 strength_gem_1）
        if "_gem_" in item_id:
            return "宝石"
        elif "_bead_" in item_id:
            return "佛珠"
        elif "_jade_" in item_id:
            return "翡翠"
        elif "_agate_" in item_id:
            return "玛瑙"
        elif "_crystal_" in item_id:
            return "水晶"
        elif "_amethyst_" in item_id:
            return "紫晶"
        elif "_rune_" in item_id:
            return "符文"
        # 兼容旧格式
        elif item_id.endswith("_gem"):
            return "宝石"
        elif item_id.endswith("_bead"):
            return "佛珠"
        elif item_id.endswith("_jade"):
            return "翡翠"
        elif item_id.endswith("_agate"):
            return "玛瑙"
        elif item_id.endswith("_crystal"):
            return "水晶"
        elif item_id.endswith("_amethyst"):
            return "紫晶"
        elif item_id.endswith("_rune"):
            return "符文"
        return "未知"

    @staticmethod
    def get_equipment_gem_info(equipment: ItemInstance) -> List[Dict]:
        """获取装备的镶嵌物信息（宝石+铭文）"""
        if not equipment.is_equipment:
            return []

        gem_info = []
        for slot_index in range(equipment.available_gem_slots):
            slot_val = equipment.get_gem_in_slot(slot_index)

            slot_info = {
                "slot_index": slot_index,
                "slot_number": slot_index + 1,
                "is_empty": slot_val is None,
                "is_inscription": False,
            }

            if slot_val is None:
                slot_info.update({
                    "gem_item_id": None,
                    "gem_name": "空",
                    "gem_type": "空",
                    "gem_config": None,
                })
            elif isinstance(slot_val, dict):
                # 铭文
                insc_item_id = slot_val.get("item_id", "")
                insc_cfg = config.items_config["by_id"].get(insc_item_id)
                slot_info.update({
                    "gem_item_id": insc_item_id,
                    "gem_name": insc_cfg.name if insc_cfg else insc_item_id,
                    "gem_type": "铭文",
                    "gem_config": insc_cfg,
                    "is_inscription": True,
                    "inscription_data": slot_val,
                })
            else:
                # 宝石
                gem_config = config.items_config["by_id"].get(slot_val)
                slot_info.update({
                    "gem_item_id": slot_val,
                    "gem_name": gem_config.name if gem_config else slot_val,
                    "gem_type": GemSocketService.get_gem_type(slot_val),
                    "gem_config": gem_config,
                })

            gem_info.append(slot_info)

        return gem_info

    # ==================== 实例方法（数据访问） ====================

    async def _has_item(self, player_id: str, item_id: str, required_qty: int) -> bool:
        """
        检查是否拥有指定数量的物品

        Args:
            player_id: 玩家ID
            item_id: 物品ID
            required_qty: 所需数量

        Returns:
            是否拥有足够数量

        对应原代码:
            gem_socket_service.py Line 253-264
        """
        total_qty = await self._item_repo.get_material_total_quantity(player_id, item_id)
        return total_qty >= required_qty

    async def can_socket_gem(self, equipment: ItemInstance, gem_item_id: str, slot_index: int, player: Player) -> Tuple[bool, str]:
        """
        检查是否可以镶嵌宝石

        Args:
            equipment: 装备实例
            gem_item_id: 宝石物品ID
            slot_index: 孔位索引
            player: 玩家对象

        Returns:
            (是否可以镶嵌, 提示信息)

        对应原代码:
            gem_socket_service.py Line 83-118
        """
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
        if not self.is_socketable_item(gem_item_id):
            return False, "该物品不能镶嵌到装备上"

        # 检查是否拥有镶嵌物品
        if not await self._has_item(player.id, gem_item_id, 1):
            gem_config = config.items_config["by_id"].get(gem_item_id)
            gem_name = gem_config.name if gem_config else gem_item_id
            return False, f"缺少镶嵌物品：{gem_name}"

        # 检查镶嵌工具
        if not await self._has_item(player.id, "gem_hammer", 1):
            return False, "缺少镶嵌锤"

        # 检查金币
        if player.gold < self.SOCKET_COSTS["gold"]:
            return False, f"金币不足，需要 {self.SOCKET_COSTS['gold']} 金币"

        return True, "可以镶嵌"

    async def socket_gem(self, equipment: ItemInstance, gem_item_id: str, slot_index: int, player: Player,
                         inscription_instance: "ItemInstance" = None) -> Tuple[bool, str]:
        """镶嵌宝石或铭文

        Args:
            equipment: 装备实例
            gem_item_id: 宝石/铭文物品ID
            slot_index: 孔位索引
            player: 玩家对象
            inscription_instance: 铭文物品实例（仅铭文镶嵌时传入，用于读取随机数值）
        """
        can_socket, reason = await self.can_socket_gem(equipment, gem_item_id, slot_index, player)
        if not can_socket:
            return False, reason

        item_cfg = config.items_config["by_id"].get(gem_item_id)
        is_inscription = item_cfg and item_cfg.type.value == "INSCRIPTION"

        if is_inscription and inscription_instance:
            # 铭文镶嵌：读取随机数值，写入孔位为字典格式
            insc_values = (inscription_instance.extra_attrs or {}).get("_inscription_values", {})
            slot_data = {"item_id": gem_item_id, "values": insc_values}
            # 消耗一个铭文实例（防御性处理：若被整理背包误合并导致quantity>1，只减1）
            if inscription_instance.quantity > 1:
                inscription_instance.quantity -= 1
                self._item_repo._session.add(inscription_instance)
            else:
                await self._item_repo.delete_item_instance(inscription_instance)
            # 消耗镶嵌锤
            hammer_success = await self._item_repo.consume_item(player.id, "gem_hammer", 1)
            if not hammer_success:
                raise ValueError("消耗镶嵌锤失败")
            player.gold -= self.SOCKET_COSTS["gold"]
            await self._player_repo.update(player)
            equipment.set_gem_in_slot(slot_index, slot_data)
            insc_name = item_cfg.name if item_cfg else gem_item_id
            return True, f"✨ 成功镶嵌铭文：{insc_name} 到孔位 {slot_index + 1}"
        else:
            # 宝石镶嵌：原有逻辑
            gem_success = await self._item_repo.consume_item(player.id, gem_item_id, 1)
            hammer_success = await self._item_repo.consume_item(player.id, "gem_hammer", 1)
            if not gem_success or not hammer_success:
                raise ValueError("消耗材料失败")
            player.gold -= self.SOCKET_COSTS["gold"]
            await self._player_repo.update(player)
            equipment.set_gem_in_slot(slot_index, gem_item_id)
            gem_config = config.items_config["by_id"].get(gem_item_id)
            gem_name = gem_config.name if gem_config else gem_item_id
            gem_type = self.get_gem_type(gem_item_id)
            return True, f"✨ 成功镶嵌 {gem_type}：{gem_name} 到孔位 {slot_index + 1}"

    async def can_remove_gem(self, equipment: ItemInstance, slot_index: int, player: Player, use_protection: bool = False) -> Tuple[bool, str]:
        """
        检查是否可以拆卸宝石

        Args:
            equipment: 装备实例
            slot_index: 孔位索引
            player: 玩家对象
            use_protection: 是否使用稳定水晶（消除宝石损坏和装备损伤风险）

        Returns:
            (是否可以拆卸, 提示信息)

        对应原代码:
            gem_socket_service.py Line 148-174
        """
        if not equipment.is_equipment:
            return False, "该物品不是装备"

        if equipment.equipped:
            return False, "请先卸下装备再进行拆卸"

        # 检查孔位
        if slot_index < 0 or slot_index >= equipment.available_gem_slots:
            return False, f"无效的孔位，装备只有 {equipment.available_gem_slots} 个孔位"

        # 检查孔位是否有宝石/铭文
        slot_val = equipment.get_gem_in_slot(slot_index)
        if slot_val is None:
            return False, f"孔位 {slot_index + 1} 没有镶嵌物品"

        # 检查拆卸工具
        if not await self._has_item(player.id, "gem_chisel", 1):
            return False, "缺少拆卸凿"

        # 使用稳定水晶时，额外检查是否拥有稳定水晶
        if use_protection and not await self._has_item(player.id, "stabilizer_crystal", 1):
            return False, "缺少稳定水晶"

        # 检查金币
        if player.gold < self.REMOVE_COSTS["gold"]:
            return False, f"金币不足，需要 {self.REMOVE_COSTS['gold']} 金币"

        return True, "可以拆卸"

    async def remove_gem(self, equipment: ItemInstance, slot_index: int, player: Player, use_protection: bool = False) -> Tuple[bool, str]:
        """拆卸宝石或铭文"""
        can_remove, reason = await self.can_remove_gem(equipment, slot_index, player, use_protection)
        if not can_remove:
            return False, reason

        slot_val = equipment.get_gem_in_slot(slot_index)
        is_inscription = isinstance(slot_val, dict)

        if is_inscription:
            insc_item_id = slot_val.get("item_id", "")
            insc_values = slot_val.get("values", {})
            item_cfg = config.items_config["by_id"].get(insc_item_id)
            gem_name = item_cfg.name if item_cfg else insc_item_id
            gem_type = "铭文"
        else:
            gem_item_id = slot_val
            gem_config = config.items_config["by_id"].get(gem_item_id)
            gem_name = gem_config.name if gem_config else gem_item_id
            gem_type = self.get_gem_type(gem_item_id)

        # 消耗工具和金币
        chisel_success = await self._item_repo.consume_item(player.id, "gem_chisel", 1)
        if not chisel_success:
            raise ValueError("消耗拆卸凿失败")
        if use_protection:
            crystal_success = await self._item_repo.consume_item(player.id, "stabilizer_crystal", 1)
            if not crystal_success:
                raise ValueError("消耗稳定水晶失败")
        player.gold -= self.REMOVE_COSTS["gold"]
        await self._player_repo.update(player)

        # 移除孔位
        equipment.set_gem_in_slot(slot_index, None)

        result_messages = []

        if use_protection:
            if is_inscription:
                await self._restore_inscription(player.id, insc_item_id, insc_values)
                result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
            else:
                try:
                    await self._item_repo.add_item(player.id, gem_item_id, 1)
                    result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
                except ValueError:
                    result_messages.append(f"💔 背包空间不足，{gem_type} {gem_name} 丢失了")
            result_messages.append("🛡️ 稳定水晶保护生效，物品和装备完好无损")
        else:
            gem_destroyed = random.random() < self.REMOVE_RISKS["gem_destroy_rate"]
            equipment_damaged = random.random() < self.REMOVE_RISKS["equipment_damage_rate"]

            if gem_destroyed:
                result_messages.append(f"💔 {gem_type} {gem_name} 在拆卸过程中损坏了")
            else:
                if is_inscription:
                    await self._restore_inscription(player.id, insc_item_id, insc_values)
                    result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
                else:
                    try:
                        await self._item_repo.add_item(player.id, gem_item_id, 1)
                        result_messages.append(f"✅ 成功拆卸 {gem_type}：{gem_name}")
                    except ValueError:
                        result_messages.append(f"💔 背包空间不足，{gem_type} {gem_name} 丢失了")

            if equipment_damaged:
                damage = max(1, equipment.config.durability // 10)
                equipment.durability = max(0, equipment.durability - damage)
                result_messages.append(f"⚠️ 装备在拆卸过程中受损，耐久度 -{damage}")

        return True, "\n".join(result_messages)

    async def _restore_inscription(self, player_id: str, item_id: str, values: dict):
        """恢复铭文物品到背包（从孔位数据重建 ItemInstance）"""
        inst = ItemInstance(
            player_id=player_id,
            item_id=item_id,
            quantity=1,
            extra_attrs={"_inscription_values": values},
        )
        self._item_repo._session.add(inst)
        await self._item_repo._session.flush()
