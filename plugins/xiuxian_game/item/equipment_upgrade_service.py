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
from pathlib import Path

import yaml

from ..models.inventory import ItemInstance
from ..models.player import Player
from ..config import config
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .affix_service import get_affixes_from_equipment

# -------- 从 YAML 加载升阶配置（模块级缓存） --------
_upgrade_config: Optional[dict] = None


def _load_upgrade_config() -> dict:
    global _upgrade_config
    if _upgrade_config is not None:
        return _upgrade_config
    cfg_path = Path(__file__).parent.parent / "data" / "equipment_upgrade.yaml"
    with open(cfg_path, "r", encoding="utf-8") as f:
        _upgrade_config = yaml.safe_load(f)
    return _upgrade_config


class EquipmentUpgradeService:
    """装备升阶服务类（装备合成模式） - DI架构版本"""

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

    @staticmethod
    def _has_affixes(eq: ItemInstance) -> bool:
        """判断装备是否有词缀"""
        return bool(get_affixes_from_equipment(eq.extra_attrs))

    @staticmethod
    def _sort_consume_priority(equipment_list: List[ItemInstance]) -> List[ItemInstance]:
        """排序装备列表，无词缀的排前面（优先被消耗），有词缀的排后面（优先保留）"""
        return sorted(equipment_list, key=lambda eq: (
            1 if get_affixes_from_equipment(eq.extra_attrs) else 0,  # 无词缀=0（前面），有词缀=1（后面）
            eq.durability or 0,  # 同等条件下按耐久度升序
        ))

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
        """获取升阶所需的相同装备数量"""
        if current_level >= 10:
            return 0
        if item_id and self.is_rare_equipment(item_id):
            return 1
        return _load_upgrade_config().get("equipment_count", 2)

    @staticmethod
    def _get_rare_material_tier(item_config) -> str:
        """根据稀有装备的稀有度/等级返回材料表键名。"""
        if not item_config:
            return "rare_default"
        rarity = getattr(item_config, "rarity", "white")
        req_lv = getattr(item_config, "required_level", 1)
        if rarity == "orange" or req_lv >= 150:
            return "rare_orange"
        if rarity == "purple" or req_lv >= 100:
            return "rare_purple"
        if rarity == "blue" or req_lv >= 60:
            return "rare_blue"
        return "rare_default"

    def get_upgrade_materials(self, current_level: int, item_id: str = None) -> Dict[str, int]:
        """获取升阶所需材料（从 equipment_upgrade.yaml 查表）"""
        if current_level >= 10:
            return {}

        target_level = current_level + 1
        cfg = _load_upgrade_config()
        mat_tables = cfg["materials"]

        if item_id and self.is_rare_equipment(item_id):
            tier = self._get_rare_material_tier(config.items_config["by_id"].get(item_id))
        else:
            tier = "normal"

        return dict(mat_tables.get(tier, mat_tables["normal"]).get(target_level, {}))

    def get_upgrade_gold_cost(self, current_level: int) -> int:
        """获取升阶所需金币（从 equipment_upgrade.yaml 查表）"""
        if current_level >= 10:
            return 0
        return _load_upgrade_config()["gold_costs"].get(current_level + 1, 0)

    @staticmethod
    def apply_gold_discount(gold_cost: int, discount: float = 0.0) -> int:
        """应用升阶金币折扣"""
        if discount <= 0:
            return gold_cost
        return int(gold_cost * (1 - min(0.20, discount)))

    def get_success_rate(
        self,
        current_level: int,
        use_protection: bool = False,
        player_luck: int = 0,
        extra_bonus: float = 0.0,
    ) -> float:
        """获取升阶成功率"""
        if current_level >= 10:
            return 0.0

        target_level = current_level + 1
        base_rate = _load_upgrade_config()["success_rates"].get(target_level, 0.0)

        # 运气加成（最多20%）
        from ..utils import luck_prob
        luck_bonus = luck_prob(player_luck) * 0.2  # 运气值转换为0-20%的加成
        base_rate = min(1.0, base_rate + luck_bonus)

        # 稳定水晶提升成功率
        if use_protection:
            base_rate = min(1.0, base_rate + 0.2)

        if extra_bonus > 0:
            base_rate = min(1.0, base_rate + min(0.15, extra_bonus))

        return base_rate

    async def can_upgrade(
        self, equipment: ItemInstance, player: Player, gold_discount: float = 0.0
    ) -> Tuple[bool, str]:
        """检查是否可以升阶（装备合成模式）"""
        if not equipment.is_equipment:
            return False, "该物品不是装备"

        if equipment.upgrade_level >= 10:
            return False, "装备已达最高等级"

        if equipment.equipped:
            return False, "请先卸下装备再进行升阶"

        # 检查装备是否在市场中挂牌（被冻结）
        extra_attrs = equipment.extra_attrs or {}
        if extra_attrs.get("_frozen_for_trade") or extra_attrs.get("_frozen_for_auction"):
            return False, "该装备正在交易/拍卖中，请先撤牌再进行升阶"
        if extra_attrs.get("_player_locked"):
            return False, "该装备已锁定，请先【解锁装备】再进行升阶"

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
        required_gold = self.apply_gold_discount(
            self.get_upgrade_gold_cost(equipment.upgrade_level),
            gold_discount,
        )
        if player.gold < required_gold:
            return False, f"金币不足，需要 {required_gold} 金币"

        return True, "可以升阶"

    async def perform_upgrade(
        self,
        equipment: ItemInstance,
        player: Player,
        use_protection: bool = False,
        success_rate_bonus: float = 0.0,
        gold_discount: float = 0.0,
    ) -> Tuple[bool, str, Dict]:
        """执行装备升阶（装备合成模式）"""
        # 再次检查是否可以升阶
        can_upgrade, reason = await self.can_upgrade(equipment, player, gold_discount)
        if not can_upgrade:
            return False, reason, {}

        # 获取升阶信息
        current_level = equipment.upgrade_level
        target_level = current_level + 1
        required_materials = self.get_upgrade_materials(current_level, equipment.item_id)
        base_required_gold = self.get_upgrade_gold_cost(current_level)
        required_gold = self.apply_gold_discount(base_required_gold, gold_discount)
        success_rate = self.get_success_rate(
            current_level,
            use_protection,
            player.luck,
            success_rate_bonus,
        )

        # 获取需要消耗的装备
        required_equipment_count = self.get_equipment_requirements(current_level, equipment.item_id)

        # 稀有装备（没有配方的装备）不需要消耗多个装备
        equipment_to_consume = []
        if not self.is_rare_equipment(equipment.item_id):
            available_equipment = await self._item_repo.get_available_equipment_for_upgrade(
                player.id, equipment.item_id, current_level
            )

            # 选择要消耗的装备（排除主装备本身和冻结装备，优先消耗无词缀的）
            candidates = [
                eq for eq in available_equipment
                if eq.id != equipment.id
                and not (eq.extra_attrs or {}).get("_frozen_for_trade")
                and not (eq.extra_attrs or {}).get("_frozen_for_auction")
                and not (eq.extra_attrs or {}).get("_player_locked")
            ]
            candidates = self._sort_consume_priority(candidates)
            equipment_to_consume = candidates[:required_equipment_count - 1]

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
            "base_gold": base_required_gold,
            "gold_discount": min(0.20, gold_discount),
            "success_rate_bonus": min(0.15, success_rate_bonus),
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
            consequence = _load_upgrade_config()["failure_consequences"].get(target_level, {"downgrade": 0, "destroy": 0.0})

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

    async def _get_side_pieces(
        self, player_id: str, item_id: str, level: int, exclude_id: int
    ) -> List[ItemInstance]:
        """获取指定等级的辅助装备（排除主装备和冻结装备）"""
        all_pieces = await self._item_repo.get_available_equipment_for_upgrade(
            player_id, item_id, level
        )
        return [
            eq for eq in all_pieces
            if eq.id != exclude_id
            and not (eq.extra_attrs or {}).get("_frozen_for_trade")
            and not (eq.extra_attrs or {}).get("_frozen_for_auction")
            and not (eq.extra_attrs or {}).get("_player_locked")
        ]

    async def _prepare_one_side_piece(
        self,
        target_level: int,
        item_id: str,
        player: Player,
        exclude_id: int,
        logs: List[str],
        stats: Dict,
        depth: int = 0,
        use_protection: bool = False,
    ) -> bool:
        """
        递归准备一个target_level阶的辅助装备。
        use_protection: 是否使用稳定水晶保护辅助装备升阶。
        返回True表示成功准备了一个target_level阶装备。
        """
        MAX_DEPTH = 10
        if depth > MAX_DEPTH or target_level == 0:
            return False  # 无法无中生有0阶装备

        lower_level = target_level - 1
        needed = self.get_equipment_requirements(lower_level, item_id)

        # 获取lower_level的辅助装备，不足则递归准备
        lower_pieces = await self._get_side_pieces(player.id, item_id, lower_level, exclude_id)

        fill_attempts = 0
        while len(lower_pieces) < needed and fill_attempts < 20:
            fill_attempts += 1
            ok = await self._prepare_one_side_piece(
                lower_level, item_id, player, exclude_id, logs, stats, depth + 1, use_protection
            )
            if not ok:
                break
            lower_pieces = await self._get_side_pieces(player.id, item_id, lower_level, exclude_id)

        if len(lower_pieces) < needed:
            return False  # 无法凑足素材

        # 挑选候选装备（优先选无词缀的，避免有词缀装备被当材料消耗）
        sorted_pieces = self._sort_consume_priority(lower_pieces)
        candidate = sorted_pieces[0]

        # 检查升阶石/金币是否足够
        can_up, reason = await self.can_upgrade(candidate, player)
        if not can_up:
            logs.append(f"  ⛔ 素材准备受阻：{reason}")
            return False

        success, _, info = await self.perform_upgrade(candidate, player, use_protection)
        stats["attempts"] = stats.get("attempts", 0) + 1

        result_type = info.get("result", "")
        if success:
            stats["successes"] = stats.get("successes", 0) + 1
            logs.append(f"  📦 {candidate.config.name} +{lower_level}→+{target_level} ✅")
            return True
        else:
            stats["failures"] = stats.get("failures", 0) + 1
            if result_type == "destroyed":
                logs.append(f"  💀 {candidate.config.name} 损坏，继续尝试其他装备")
                return False
            elif result_type == "downgraded":
                logs.append(f"  📉 {candidate.config.name} 降级到+{info.get('new_level')}阶")
                return False
            elif result_type == "failed_protected":
                logs.append(f"  🛡️ {candidate.config.name} 水晶保护(+{candidate.upgrade_level}阶)")
                return False
            else:
                logs.append(f"  ❌ {candidate.config.name} 升阶失败（等级不变）")
                return False

    async def _recover_gems_from_equipment(self, equipment: ItemInstance, player: Player, all_survive: bool = False) -> List[str]:
        """从装备中回收镶嵌的宝石和铭文"""
        recovered = []

        if not equipment.is_equipment or not equipment.gem_slots_data:
            return recovered

        for slot_val in equipment.gem_slots_data.values():
            if not slot_val:
                continue

            if not all_survive and random.random() < 0.5:
                continue

            if isinstance(slot_val, dict):
                # 铭文恢复
                insc_id = slot_val.get("item_id", "")
                insc_values = slot_val.get("values", {})
                insc_cfg = config.items_config["by_id"].get(insc_id)
                insc_name = insc_cfg.name if insc_cfg else insc_id
                inst = ItemInstance(
                    player_id=player.id,
                    item_id=insc_id,
                    quantity=1,
                    extra_attrs={"_inscription_values": insc_values},
                )
                self._item_repo._session.add(inst)
                recovered.append(insc_name)
            else:
                # 宝石恢复（原有逻辑）
                gem_config = config.items_config["by_id"].get(slot_val)
                gem_name = gem_config.name if gem_config else slot_val
                try:
                    await self._item_repo.add_item(player.id, slot_val, 1)
                    recovered.append(gem_name)
                except ValueError:
                    gold_value = gem_config.price if (gem_config and gem_config.price) else 1000
                    player.gold += gold_value
                    recovered.append(f"{gem_name}(转为{gold_value}金币)")

        return recovered
