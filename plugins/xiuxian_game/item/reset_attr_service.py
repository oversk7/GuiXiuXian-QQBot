"""
重置属性服务模块

从item_effects.py中提取的RESET_ATTR效果，遵循DI架构模式
"""
from typing import Dict

from ..models.player import Player
from ..models.inventory import ItemInstance, ItemType, ItemConfig
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.elixir_usage_repository import ElixirUsageRepository
from ..infrastructure.repositories.vip_equipment_bonus_repository import VIPEquipmentBonusRepository
from ..domain.effects import EffectResult
from ..cultivate.reincarnation_service_new import ReincarnationService


class ResetAttrService:
    """
    重置属性服务

    负责处理重启符的使用逻辑：
    1. 重置玩家已分配属性点
    2. 保留装备加成
    3. 保留丹药加成（从ElixirUsageLog查询所有历史记录）
    4. 保留VIP装备永久加成
    5. 重新计算装备属性（基于新的基础属性）
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        item_repo: ItemRepository,
        elixir_usage_repo: ElixirUsageRepository,
        vip_equipment_bonus_repo: VIPEquipmentBonusRepository
    ):
        """
        初始化重置属性服务

        Args:
            player_repo: 玩家仓储
            item_repo: 物品仓储
            elixir_usage_repo: 丹药使用记录仓储
            vip_equipment_bonus_repo: VIP装备加成仓储
        """
        self._player_repo = player_repo
        self._item_repo = item_repo
        self._elixir_usage_repo = elixir_usage_repo
        self._vip_equipment_bonus_repo = vip_equipment_bonus_repo

    async def execute(
        self,
        player: Player,
        item_cfg: ItemConfig,
        quantity: int,
        context_type: str = "world"
    ) -> EffectResult:
        """
        执行重置属性效果

        Args:
            player: 玩家对象
            item_cfg: 物品配置
            quantity: 使用数量
            context_type: 上下文类型（world/battle/dungeon）

        Returns:
            EffectResult: 执行结果
        """
        # 数量检查（仅允许qty=1）
        if quantity != 1:
            return EffectResult(
                success=False,
                message="⛔ 重启符一次只能使用 1 个"
            )

        from ..config import config as gcfg

        # 初始基础属性
        INIT = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 0,
            "agility": 5,
            "luck": 1,
        }

        # 计算丹药加成
        elixir_bonus = {k: 0 for k in INIT}
        # 获取所有丹药使用记录（不限日期，因为丹药效果是永久的）
        logs = await self._elixir_usage_repo.get_all_player_usage(player.id)

        from ..models.inventory import ItemEffectType

        # 统计每种丹药的总使用量
        elixir_usage_total = {}
        for log in logs:
            if log.item_id not in elixir_usage_total:
                elixir_usage_total[log.item_id] = 0
            elixir_usage_total[log.item_id] += log.quantity

        # 计算丹药属性加成
        for item_id, total_qty in elixir_usage_total.items():
            item_cfg_data = gcfg.items_config["by_id"].get(item_id)
            if item_cfg_data and item_cfg_data.effect_type == ItemEffectType.BUFF:
                effect_params = item_cfg_data.effect_params or {}
                for attr, value in effect_params.items():
                    if attr in elixir_bonus:
                        elixir_bonus[attr] += int(value) * total_qty

        # 获取VIP装备永久加成
        vip_bonus = {k: 0 for k in INIT}
        vip_record = await self._vip_equipment_bonus_repo.get_by_player_id(player.id)
        if vip_record:
            for attr, value in vip_record.get_total_bonus().items():
                if attr in vip_bonus:
                    vip_bonus[attr] = int(value)

        # 重置属性为基础值 + 丹药加成 + VIP装备永久加成（先不加装备加成）
        for k, base_v in INIT.items():
            total_bonus = elixir_bonus.get(k, 0) + vip_bonus.get(k, 0)
            setattr(player, k, base_v + total_bonus)

        # 重新计算可分配点（考虑转数加成）
        pts_per_lvl = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
        player.attribute_points = (player.level - 1) * pts_per_lvl

        # 重新计算装备加成（基于新的基础属性）
        # 获取所有已装备的装备
        equipped_items = await self._item_repo.get_equipped_equipment(
            player.id,
            gcfg.items_config["by_type"]["EQUIPMENT"]
        )

        # 1. 先卸下所有装备，恢复基础属性
        for eq in equipped_items:
            # 恢复玩家属性
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            for k, v in delta.items():
                setattr(player, k, getattr(player, k) - v)

            # 清除持久化记录并标记未穿戴
            if "_persist_bonus" in (eq.extra_attrs or {}):
                extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
                eq.extra_attrs = extra_new

            eq.equipped = False

        # 2. 获取玩家基础属性（无装备加成）
        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        # 3. 重新穿戴所有装备，每件都基于基础属性计算
        for eq in equipped_items:
            # 标记为已装备
            eq.equipped = True

            # 基于基础属性计算装备加成
            attrs_temp = base_attrs.copy()
            eq.apply_attr_bonus(attrs_temp, base_attrs)
            new_delta = {}
            for k in attrs_temp:
                if k in base_attrs:
                    if attrs_temp[k] != base_attrs[k]:
                        new_delta[k] = attrs_temp[k] - base_attrs[k]
                else:
                    # 对于base_attrs中不存在的属性，直接使用新值作为加成
                    if attrs_temp[k] != 0:
                        new_delta[k] = attrs_temp[k]

            # 应用到玩家属性
            for k, v in new_delta.items():
                setattr(player, k, getattr(player, k) + v)

            # 保存新的持久化加成
            extra = eq.extra_attrs or {}
            extra["_persist_bonus"] = new_delta
            eq.extra_attrs = extra

        # 批量更新装备的extra_attrs（基础加成部分）
        await self._item_repo.update_extra_attrs_batch(equipped_items)

        # 处理 mp_from_hp / hp_from_attack 等特效装备，并更新玩家记录
        # recalc_equipment_attributes 会：
        # 1. 先移除刚刚应用的加成，再重新计算（结果一致）
        # 2. 额外处理 mp_from_hp/hp_from_attack 特效
        # 3. 确保 HP/MP 不超上限
        from .equipment_service_new import EquipmentService
        equipment_service = EquipmentService(
            item_repo=self._item_repo,
            player_repo=self._player_repo
        )
        await equipment_service.recalc_equipment_attributes(player, equipped_items)

        # 生成详细的重置信息
        bonus_info = []

        # 检查是否有装备加成（用已处理好的列表，无需再次查询DB）
        has_equipment_bonus = any(
            any((eq.extra_attrs or {}).get("_persist_bonus", {}).values())
            for eq in equipped_items
        )

        if has_equipment_bonus:
            bonus_info.append("装备加成已保留")

        if any(elixir_bonus.values()):
            elixir_details = []
            for k, v in elixir_bonus.items():
                if v > 0:
                    attr_name = {
                        "max_hp": "体",
                        "max_mp": "智",
                        "attack": "力",
                        "defense": "防",
                        "agility": "敏",
                        "luck": "运"
                    }.get(k, k)
                    elixir_details.append(f"{attr_name}+{v}")
            if elixir_details:
                bonus_info.append(f"丹药加成已保留({', '.join(elixir_details)})")

        bonus_msg = f"，{', '.join(bonus_info)}" if bonus_info else ""
        message = f"🔄 属性已重置，所有点数已退还，可重新分配{bonus_msg}"

        return EffectResult(
            success=True,
            message=message
        )
