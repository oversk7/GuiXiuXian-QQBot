"""
冥返系统服务模块 (DI架构版本)

实现冥返机制的核心逻辑，包括：
1. 冥返检查
2. 冥返执行
3. 丹药加成计算
4. VIP装备永久加成获取
5. 装备加成重新计算

重构说明：
- 所有@staticmethod改为实例方法
- 通过构造函数注入Repository依赖
- 不再接收session参数，改为使用注入的仓储
- 移除service内部的session.commit()调用（事务由调用方控制）
- 保持业务逻辑完全一致
"""

from typing import Dict
from ..models.player import Player
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.elixir_usage_repository import ElixirUsageRepository
from ..infrastructure.repositories.vip_equipment_bonus_repository import VIPEquipmentBonusRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..config import config


class ReincarnationService:
    """冥返系统服务类 - DI版本

    通过构造函数注入所需的Repository，不再使用静态方法
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        elixir_usage_repo: ElixirUsageRepository,
        vip_equipment_bonus_repo: VIPEquipmentBonusRepository,
        item_repo: ItemRepository,
    ):
        """
        初始化冥返服务

        Args:
            player_repo: 玩家仓储
            elixir_usage_repo: 丹药使用记录仓储
            vip_equipment_bonus_repo: VIP装备永久加成仓储
            item_repo: 物品仓储
        """
        self._player_repo = player_repo
        self._elixir_usage_repo = elixir_usage_repo
        self._vip_equipment_bonus_repo = vip_equipment_bonus_repo
        self._item_repo = item_repo

    async def can_reincarnate(self, player: Player) -> bool:
        """检查玩家是否可以冥返（仅检查等级）"""
        required_level = self.get_required_level_for_reincarnation(player.reincarnation_level)
        return player.level >= required_level

    @staticmethod
    def get_reincarnation_resentment_cost(level: int) -> int:
        """计算冥返所需怨念值 = 当前等级突破镇厄消耗的10倍"""
        cfg_break = config.game_config.get("cultivate", {}).get("breakthrough", {})
        guardian_cost_base = cfg_break.get("guardian_cost_base", 50)
        guardian_cost_per_level = cfg_break.get("guardian_cost_per_level", 15)
        return 10 * (guardian_cost_base + level * guardian_cost_per_level)

    async def perform_reincarnation(self, player: Player) -> str:
        """执行冥返操作"""
        if not await self.can_reincarnate(player):
            required_level = self.get_required_level_for_reincarnation(player.reincarnation_level)
            return f"⛔ 尚未达到冥返要求，需要达到 {required_level} 级才能进行第{player.reincarnation_level + 1}次冥返"

        # 检查怨念值是否足够
        resentment_cost = self.get_reincarnation_resentment_cost(player.level)
        if player.resentment < resentment_cost:
            return (
                f"⛔ 怨念不足，无法冥返！\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 当前怨念：{player.resentment}\n"
                f"✧ 冥返需要：{resentment_cost}\n"
                f"✧ 还差：{resentment_cost - player.resentment}\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 冥返代价 = 当前等级突破镇厄消耗 × 10\n"
                f"⬇️ 【献祭】获取怨念值"
            )

        # 扣除怨念值
        player.resentment -= resentment_cost

        # 获取丹药加成
        elixir_bonus = await self._get_elixir_bonus(player.id)

        # 获取VIP装备永久加成
        vip_bonus = await self._get_vip_equipment_bonus(player.id)

        # 初始基础属性
        INIT_ATTRS = {
            "max_hp": 20,
            "max_mp": 20,
            "attack": 1,
            "defense": 0,
            "agility": 5,
            "luck": 1,
        }

        # 记录冥返前的信息
        old_level = player.level
        old_reincarnation = player.reincarnation_level

        # 重置属性为基础值 + 丹药加成 + VIP装备永久加成
        for attr_name, base_value in INIT_ATTRS.items():
            total_bonus = elixir_bonus.get(attr_name, 0) + vip_bonus.get(attr_name, 0)
            setattr(player, attr_name, base_value + total_bonus)

        # 重置等级和经验
        player.level = 1
        player.exp = 0
        player.attribute_points = 0

        # 清零加点追踪（转生后重新分配时从零开始精确追踪）
        player.allocated_attrs = {}

        # 增加转数
        player.reincarnation_level += 1

        # 恢复满血满蓝
        player.hp = player.max_hp
        player.mp = player.max_mp

        # 重新计算装备加成
        await self._recalculate_equipment_bonus(player)

        # 使用仓储更新玩家（不调用commit）
        await self._player_repo.update(player)

        # 构建冥返消息
        next_required_level = self.get_required_level_for_reincarnation(player.reincarnation_level)
        next_reincarnation_count = player.reincarnation_level + 1

        msg = (
            f"🌟 冥返成功！踏入第{player.reincarnation_level}转轮回\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 从 Lv.{old_level} 重塑为 Lv.1\n"
            f"✧ 转数：{old_reincarnation} → {player.reincarnation_level}\n"
            f"✧ 消耗怨念：{resentment_cost}（剩余 {player.resentment}）\n"
            f"✧ 每级属性点：{self.get_attribute_points_per_level(player.reincarnation_level)}\n"
            f"✧ 修炼效率加成：+{self.get_cultivation_efficiency_bonus(player.reincarnation_level):.0%}\n"
            f"✧ 闭关效率加成：+{self.get_seclusion_efficiency_bonus(player.reincarnation_level):.0%}\n"
            "━━━━━━━━━━━━━\n"
            f"✧ 下次冥返：需达到 Lv.{next_required_level} (第{next_reincarnation_count}次)\n"
            "━━━━━━━━━━━━━\n"
            "⬇️ 【修炼】重新踏上修仙之路\n"
            "⬇️ 【面板】查看新的属性"
        )

        return msg

    async def _get_elixir_bonus(self, player_id: str) -> dict:
        """获取玩家的丹药加成"""
        logs = await self._elixir_usage_repo.get_all_player_usage(player_id)

        elixir_bonus = {}
        for log in logs:
            for attr_name, bonus in log.get_attribute_bonus().items():
                elixir_bonus[attr_name] = elixir_bonus.get(attr_name, 0) + bonus

        return elixir_bonus

    async def _get_vip_equipment_bonus(self, player_id: str) -> dict:
        """获取玩家的VIP装备永久加成"""
        record = await self._vip_equipment_bonus_repo.get_by_player_id(player_id)

        if not record:
            return {}

        return record.get_total_bonus()

    async def _recalculate_equipment_bonus(self, player: Player):
        """重新计算装备加成（冥返专用）"""
        # 获取所有已装备的装备
        equipped_items = await self._item_repo.get_equipped_items(player.id)

        # 过滤装备类型
        equipment_item_ids = config.items_config["by_type"]["EQUIPMENT"]
        equipped_items = [
            eq for eq in equipped_items
            if eq.item_id in equipment_item_ids
        ]

        # 冥返时，玩家属性已经被重置为基础值，不需要减去旧的装备加成
        # 直接清除所有装备的持久化记录，然后重新计算

        # 1. 清除所有装备的持久化记录，但保持装备状态
        for eq in equipped_items:
            # 清除持久化记录
            if "_persist_bonus" in (eq.extra_attrs or {}):
                extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
                eq.extra_attrs = extra_new

        # 2. 获取玩家当前基础属性（已经是冥返后的重置属性）
        base_attrs = {
            "attack": player.attack,
            "defense": player.defense,
            "agility": player.agility,
            "luck": player.luck,
            "max_hp": player.max_hp,
            "max_mp": player.max_mp,
        }

        # 3. 重新计算并应用所有装备的加成
        for eq in equipped_items:
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
            await self._item_repo.update(eq)

    @staticmethod
    def get_attribute_points_per_level(reincarnation_level: int) -> int:
        """获取每级获得的属性点数：(转数+1)*10"""
        base_points = config.game_config["game"]["points_per_level"]
        return int((reincarnation_level*0.5 + 1) * base_points)

    @staticmethod
    def get_cultivation_efficiency_bonus(reincarnation_level: int) -> float:
        """获取修炼效率加成"""
        bonus_per_level = config.game_config["game"]["reincarnation"]["cultivation_efficiency_bonus"]
        return reincarnation_level * bonus_per_level

    @staticmethod
    def get_seclusion_efficiency_bonus(reincarnation_level: int) -> float:
        """获取闭关效率加成"""
        bonus_per_level = config.game_config["game"]["reincarnation"]["seclusion_efficiency_bonus"]
        return reincarnation_level * bonus_per_level

    @staticmethod
    def get_required_level_for_reincarnation(current_reincarnation_level: int) -> int:
        """
        计算下次冥返所需的等级
        第一次冥返：300级
        第二次冥返：500级
        第三次冥返：1000级
        之后每次递增500级
        """
        if current_reincarnation_level == 0:
            # 第一次冥返需要300级
            return 300
        elif current_reincarnation_level == 1:
            # 第二次冥返需要500级
            return 500
        elif current_reincarnation_level == 2:
            # 第三次冥返需要1000级
            return 1000
        else:
            # 第四次及以后，每次递增500级
            # 第三次是1000级，第四次是1500级，第五次是2000级...
            return 1000 + (current_reincarnation_level - 2) * 500
