"""
装备升阶系统服务（装备合成模式） - DI架构版本

提供装备升阶的核心逻辑，包括：
1. 装备合成需求计算（多个相同装备+升阶石）
2. 升阶成功率计算
3. 升阶失败处理
4. 属性提升计算

重构说明：
- 所有@classmethod改为实例方法
- 通过构造函数注入ItemRepository和PlayerRepository
- 移除session参数，通过Repository访问数据
- 保持业务逻辑完全一致
"""

import random
from typing import Dict, Tuple, Optional, List
from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


class EquipmentUpgradeService:
    """装备升阶服务类（装备合成模式） - DI架构版本"""

    # 升阶成功率配置（已优化，提高玩家体验）
    SUCCESS_RATES = {
        1: 0.95, 2: 0.90, 3: 0.85,  # 1-3阶：高成功率
        4: 0.80, 5: 0.75, 6: 0.70,  # 4-6阶：中等成功率
        7: 0.60, 8: 0.50, 9: 0.40,  # 7-9阶：中低成功率
        10: 0.25                     # 10阶：低成功率
    }

    # 升阶失败后果配置（已优化，减轻惩罚）
    FAILURE_CONSEQUENCES = {
        # 1-3阶：只消耗材料，装备不变
        1: {"downgrade": 0, "destroy": 0.0},
        2: {"downgrade": 0, "destroy": 0.0},
        3: {"downgrade": 0, "destroy": 0.0},

        # 4-6阶：可能降1阶
        4: {"downgrade": 1, "destroy": 0.0},
        5: {"downgrade": 1, "destroy": 0.0},
        6: {"downgrade": 1, "destroy": 0.0},

        # 7-9阶：可能降1阶或少量损坏风险
        7: {"downgrade": 1, "destroy": 0.02},
        8: {"downgrade": 1, "destroy": 0.03},
        9: {"downgrade": 2, "destroy": 0.05},

        # 10阶：可能降2阶或损坏
        10: {"downgrade": 2, "destroy": 0.08}
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

    def __init__(
        self,
        item_repo: ItemRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化装备升阶服务

        Args:
            item_repo: 物品仓储
            player_repo: 玩家仓储
        """
        self._item_repo = item_repo
        self._player_repo = player_repo

    def is_rare_equipment(self, item_id: str) -> bool:
        """判断是否为稀有装备（没有配方的装备）

        稀有装备包括：
        1. VIP定制装备（如天退星刀）
        2. Boss掉落专属装备（如幸运剪刀、黑色信封等）
        3. 其他没有配方的特殊装备

        这些装备不需要消耗多个装备来升阶，只需要特殊材料
        """
        item_config = config.items_config["by_id"].get(item_id)
        if not item_config:
            return False

        # 检查是否有recipe字段
        # 如果没有recipe或recipe为None/空，则视为稀有装备
        return not hasattr(item_config, 'recipe') or not item_config.recipe

    def get_equipment_requirements(self, current_level: int, item_id: str = None) -> int:
        """获取升阶所需的相同装备数量

        Args:
            current_level: 当前升阶等级
            item_id: 装备ID（用于判断是否为稀有装备）
        """
        if current_level >= 10:
            return 0  # 已达最高等级

        # 稀有装备（没有配方的装备）不需要消耗多个装备
        if item_id and self.is_rare_equipment(item_id):
            return 1  # 只需要装备本身

        target_level = current_level + 1
        return self.EQUIPMENT_REQUIREMENTS.get(target_level, 2)

    def get_upgrade_materials(self, current_level: int, item_id: str = None) -> Dict[str, int]:
        """获取升阶所需升阶石材料

        Args:
            current_level: 当前升阶等级
            item_id: 装备ID（用于判断是否为稀有装备）
        """
        if current_level >= 10:
            return {}  # 已达最高等级

        target_level = current_level + 1
        materials = {}

        # 稀有装备（没有配方的装备）使用特殊材料
        if item_id and self.is_rare_equipment(item_id):
            # 根据装备稀有度和等级要求，使用不同的材料组合
            item_config = config.items_config["by_id"].get(item_id)

            if item_config:
                rarity = getattr(item_config, 'rarity', 'white')
                required_level = getattr(item_config, 'required_level', 1)

                # 根据稀有度和等级确定材料
                if rarity == 'orange' or required_level >= 150:
                    # 传说级装备：使用高级材料
                    if target_level <= 3:
                        materials["upgrade_stone_low"] = target_level
                        materials["void_essence"] = target_level
                    elif target_level <= 6:
                        materials["upgrade_stone_mid"] = target_level - 3
                        materials["demon_heart"] = 1
                    elif target_level <= 9:
                        materials["upgrade_stone_high"] = target_level - 6
                        materials["time_dust"] = target_level - 6
                    else:  # target_level == 10
                        materials["upgrade_stone_supreme"] = 1
                        materials["world_fragment"] = 1

                elif rarity == 'purple' or required_level >= 100:
                    # 紫色装备：使用中级材料
                    if target_level <= 3:
                        materials["upgrade_stone_low"] = target_level
                        materials["soul_crystal"] = target_level
                    elif target_level <= 6:
                        materials["upgrade_stone_mid"] = target_level - 3
                        materials["cursed_mirror_shard"] = target_level - 3
                    elif target_level <= 9:
                        materials["upgrade_stone_high"] = target_level - 6
                        materials["demon_heart"] = 1
                    else:  # target_level == 10
                        materials["upgrade_stone_supreme"] = 1
                        materials["void_essence"] = 2

                elif rarity == 'blue' or required_level >= 60:
                    # 蓝色装备：使用低级材料
                    if target_level <= 3:
                        materials["upgrade_stone_low"] = target_level
                        materials["phantom_thread"] = target_level * 2
                    elif target_level <= 6:
                        materials["upgrade_stone_mid"] = target_level - 3
                        materials["soul_crystal"] = target_level - 3
                    elif target_level <= 9:
                        materials["upgrade_stone_high"] = target_level - 6
                        materials["cursed_mirror_shard"] = target_level - 6
                    else:  # target_level == 10
                        materials["upgrade_stone_supreme"] = 1
                        materials["demon_heart"] = 1
                else:
                    # 绿色/白色装备：只需要升阶石
                    if target_level <= 3:
                        materials["upgrade_stone_low"] = target_level
                    elif target_level <= 6:
                        materials["upgrade_stone_mid"] = target_level - 3
                    elif target_level <= 9:
                        materials["upgrade_stone_high"] = target_level - 6
                    else:  # target_level == 10
                        materials["upgrade_stone_supreme"] = 1
        else:
            # 普通装备（有配方的装备）只需要升阶石
            if target_level <= 3:
                materials["upgrade_stone_low"] = target_level
            elif target_level <= 6:
                materials["upgrade_stone_mid"] = target_level - 3
            elif target_level <= 9:
                materials["upgrade_stone_high"] = target_level - 6
            else:  # target_level == 10
                materials["upgrade_stone_supreme"] = 1

        return materials

    def get_upgrade_gold_cost(self, current_level: int) -> int:
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

    def get_success_rate(self, current_level: int, use_protection: bool = False, player_luck: int = 0) -> float:
        """获取升阶成功率"""
        if current_level >= 10:
            return 0.0

        target_level = current_level + 1
        base_rate = self.SUCCESS_RATES.get(target_level, 0.0)

        # 运气加成（最多20%）
        from ..utils import luck_prob
        luck_bonus = luck_prob(player_luck) * 0.2  # 运气值转换为0-20%的加成
        base_rate = min(1.0, base_rate + luck_bonus)

        # 稳定水晶提升成功率
        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)

        return base_rate

    async def can_upgrade(self, equipment: ItemInstance, player: Player) -> Tuple[bool, str]:
        """检查是否可以升阶（装备合成模式）"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"

        if equipment.upgrade_level >= 10:
            return False, "装备已达最高等级"

        if equipment.equipped:
            return False, "请先卸下装备再进行升阶"

        # 检查相同装备数量
        required_equipment_count = self.get_equipment_requirements(equipment.upgrade_level, equipment.item_id)
        available_equipment = await self._item_repo.get_available_equipment_for_upgrade(
            player.id, equipment.item_id, equipment.upgrade_level
        )

        if len(available_equipment) < required_equipment_count:
            # 稀有装备的提示更友好
            if self.is_rare_equipment(equipment.item_id):
                # 稀有装备只需要1个（装备本身），所以这个检查应该总是通过
                pass
            else:
                return False, f"需要 {required_equipment_count} 个 +{equipment.upgrade_level}阶 {equipment.config.name}，当前只有 {len(available_equipment)} 个"

        # 检查升阶石材料
        required_materials = self.get_upgrade_materials(equipment.upgrade_level, equipment.item_id)
        for material_id, required_qty in required_materials.items():
            total_qty = await self._item_repo.get_material_total_quantity(player.id, material_id)
            if total_qty < required_qty:
                material_config = config.items_config["by_id"].get(material_id)
                material_name = material_config.name if material_config else material_id
                return False, f"缺少材料：{material_name} x{required_qty}"

        # 检查金币
        required_gold = self.get_upgrade_gold_cost(equipment.upgrade_level)
        if player.gold < required_gold:
            return False, f"金币不足，需要 {required_gold} 金币"

        return True, "可以升阶"

    async def perform_upgrade(self, equipment: ItemInstance, player: Player, use_protection: bool = False) -> Tuple[bool, str, Dict]:
        """执行装备升阶（装备合成模式）"""
        # 再次检查是否可以升阶
        can_upgrade, reason = await self.can_upgrade(equipment, player)
        if not can_upgrade:
            return False, reason, {}

        # 获取升阶信息
        current_level = equipment.upgrade_level
        target_level = current_level + 1
        required_materials = self.get_upgrade_materials(current_level, equipment.item_id)
        required_gold = self.get_upgrade_gold_cost(current_level)
        success_rate = self.get_success_rate(current_level, use_protection, player.luck)

        # 获取需要消耗的装备
        required_equipment_count = self.get_equipment_requirements(current_level, equipment.item_id)

        # 稀有装备（没有配方的装备）不需要消耗多个装备
        equipment_to_consume = []
        if not self.is_rare_equipment(equipment.item_id):
            available_equipment = await self._item_repo.get_available_equipment_for_upgrade(
                player.id, equipment.item_id, current_level
            )

            # 选择要消耗的装备（排除主装备本身）
            for eq in available_equipment:
                if eq.id != equipment.id and len(equipment_to_consume) < required_equipment_count - 1:
                    equipment_to_consume.append(eq)

            if len(equipment_to_consume) < required_equipment_count - 1:
                return False, "可用装备数量不足", {}

        # 消耗升阶石材料
        consumed_materials = {}
        for material_id, required_qty in required_materials.items():
            success = await self._item_repo.consume_item(player.id, material_id, required_qty)
            if not success:
                return False, "扣除材料失败", {}
            consumed_materials[material_id] = required_qty

        # 消耗稳定水晶（如果使用）
        if use_protection:
            protection_success = await self._item_repo.consume_item(player.id, "stabilizer_crystal", 1)
            if not protection_success:
                return False, "缺少稳定水晶", {}
            consumed_materials["stabilizer_crystal"] = 1

        # 消耗装备（先回收副装备上的宝石，避免宝石静默丢失）
        consumed_equipment_names = []
        gems_from_consumed: List[str] = []
        for eq in equipment_to_consume:
            consumed_equipment_names.append(f"{eq.config.name}(ID:{eq.id})")
            if eq.gem_slots_data:
                recovered = await self._recover_gems_from_equipment(eq, player, all_survive=True)
                gems_from_consumed.extend(recovered)
            await self._item_repo.delete_item_instance(eq)

        player.gold -= required_gold
        await self._player_repo.update(player)

        # 判断升阶结果
        is_success = random.random() < success_rate
        result_info = {
            "target_level": target_level,
            "success_rate": success_rate,
            "consumed_materials": consumed_materials,
            "consumed_equipment": consumed_equipment_names,
            "consumed_gold": required_gold,
            "used_protection": use_protection,
            "recovered_from_consumed": gems_from_consumed,
        }
        gems_suffix = f"\n💎 副装备回收宝石：{', '.join(gems_from_consumed)}" if gems_from_consumed else ""

        if is_success:
            # 升阶成功
            equipment.upgrade_level = target_level
            result_info["result"] = "success"
            result_info["new_level"] = target_level
            return True, f"升阶成功！装备升级到 +{target_level} 阶{gems_suffix}", result_info
        else:
            # 升阶失败
            consequence = self.FAILURE_CONSEQUENCES.get(target_level, {"downgrade": 0, "destroy": 0.0})

            # 稳定水晶保护
            if use_protection:
                result_info["result"] = "failed_protected"
                return False, f"升阶失败，但稳定水晶保护了装备{gems_suffix}", result_info

            # 检查是否损坏
            if random.random() < consequence["destroy"]:
                # 装备损坏前，先回收镶嵌的宝石（每个宝石独立50%存活率）
                recovered_gems = await self._recover_gems_from_equipment(equipment, player, all_survive=False)

                # 删除装备
                await self._item_repo.delete_item_instance(equipment)
                result_info["result"] = "destroyed"

                message = "升阶失败，装备已损坏！"
                if recovered_gems:
                    message += f"\n回收镶嵌物：{', '.join(recovered_gems)}"
                else:
                    message += "\n装备上的镶嵌物全部损毁"
                message += gems_suffix

                return False, message, result_info

            # 装备降级
            downgrade_levels = consequence["downgrade"]
            if downgrade_levels > 0:
                new_level = max(0, current_level - downgrade_levels)
                equipment.upgrade_level = new_level
                result_info["result"] = "downgraded"
                result_info["new_level"] = new_level
                return False, f"升阶失败，装备降级到 +{new_level} 阶{gems_suffix}", result_info
            else:
                result_info["result"] = "failed_no_change"
                return False, f"升阶失败，装备等级不变{gems_suffix}", result_info

    async def _recover_gems_from_equipment(self, equipment: ItemInstance, player: Player, all_survive: bool = False) -> List[str]:
        """
        从装备中回收镶嵌的宝石
        - all_survive=True：全量回收（用于消耗副装备前的清理）
        - all_survive=False：每个宝石独立50%存活率（用于装备意外损坏时）
        返回成功回收的宝石名称列表
        """
        recovered_gems = []

        if not equipment.is_equipment or not equipment.gem_slots_data:
            return recovered_gems

        for gem_item_id in equipment.gem_slots_data.values():
            if not gem_item_id:
                continue

            # 非全量模式下，每个宝石独立50%存活
            if not all_survive and random.random() < 0.5:
                continue

            gem_config = config.items_config["by_id"].get(gem_item_id)
            gem_name = gem_config.name if gem_config else gem_item_id

            try:
                await self._item_repo.add_item(player.id, gem_item_id, 1)
                recovered_gems.append(gem_name)
            except ValueError:
                # 背包空间不足，转换为金币
                gold_value = gem_config.price if (gem_config and gem_config.price) else 1000
                player.gold += gold_value
                recovered_gems.append(f"{gem_name}(转为{gold_value}金币)")

        return recovered_gems
