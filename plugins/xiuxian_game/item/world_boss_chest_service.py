"""
世界BOSS宝箱服务 - DI版本

从item_effects.py中提取的WORLD_BOSS_CHEST效果，采用依赖注入架构
"""
import random
from typing import List, Tuple
from datetime import datetime

from ..models.player import Player
from ..models.inventory import ItemInstance, ItemConfig
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.item_repository import ItemRepository
from ..domain.effects.interfaces import EffectResult


class WorldBossChestService:
    """
    世界BOSS宝箱开启服务

    负责处理世界BOSS宝箱的开启逻辑：
    - 根据宝箱等级（tier）分配不同的奖励池
    - 金币奖励（必得）
    - 镶嵌物奖励（概率性）
    - 材料奖励（概率性）
    - 克苏鲁风格描述
    """

    # 不同等级宝箱的奖励池配置
    REWARD_POOLS = {
        "overlord": {  # 深渊霸主宝箱
            "gems": [
                ("critical_bead_4", 1, 0.1),
                ("combo_bead_4", 1, 0.1),
                ("dodge_bead_4", 1, 0.1),
                ("counter_jade_4", 1, 0.1),
                ("critical_power_agate_4", 1, 0.1),
                ("penetration_crystal_4", 1, 0.1),
                ("spirit_burst_amethyst_4", 1, 0.1),
                ("anti_crit_rune_4", 1, 0.1),
            ],
            "materials": [
                ("upgrade_stone_supreme", 3, 0.3),
                ("stabilizer_crystal", 5, 0.1),
            ],
            "gold": (20000, 50000)
        },
        "king": {  # 深渊王者宝箱
            "gems": [
                ("critical_bead_3", 1, 0.1),
                ("combo_bead_3", 1, 0.1),
                ("dodge_bead_3", 1, 0.1),
                ("counter_jade_3", 1, 0.1),
                ("critical_power_agate_3", 1, 0.1),
                ("penetration_crystal_3", 1, 0.1),
                ("spirit_burst_amethyst_3", 1, 0.1),
                ("anti_crit_rune_3", 1, 0.1),
            ],
            "materials": [
                ("upgrade_stone_supreme", 2, 0.3),
                ("stabilizer_crystal", 3, 0.1),
            ],
            "gold": (10000, 20000)
        },
        "warrior": {  # 深渊勇士宝箱
            "gems": [
                ("critical_bead_2", 1, 0.1),
                ("combo_bead_2", 1, 0.1),
                ("dodge_bead_2", 1, 0.1),
                ("counter_jade_2", 1, 0.1),
                ("critical_power_agate_2", 1, 0.1),
                ("penetration_crystal_2", 1, 0.1),
                ("spirit_burst_amethyst_2", 1, 0.1),
                ("anti_crit_rune_2", 1, 0.1),
            ],
            "materials": [
                ("upgrade_stone_supreme", 1, 0.1),
                ("stabilizer_crystal", 2, 0.1),
            ],
            "gold": (10000, 20000)
        },
        "explorer": {  # 深渊探索者宝箱
            "gems": [
                ("critical_bead_1", 1, 0.2),
                ("combo_bead_1", 1, 0.2),
                ("accuracy_bead_1", 1, 0.2),
                ("counter_jade_1", 1, 0.2),
                ("penetration_crystal_1", 1, 0.2),
                ("anti_crit_rune_1", 1, 0.2),
            ],
            "materials": [
                ("stabilizer_crystal", 1, 0.1),
            ],
            "gold": (10000, 20000)
        },
        "challenger": {  # 深渊挑战者宝箱
            "gems": [
                ("critical_bead_1", 1, 0.1),
                ("accuracy_bead_1", 1, 0.1),
                ("dodge_bead_1", 1, 0.1),
                ("counter_jade_1", 1, 0.1),
                ("critical_power_agate_1", 1, 0.2),
                ("anti_crit_rune_1", 1, 0.1),
            ],
            "gold": (5000, 15000)
        },
        "participant": {  # 深渊参与者宝箱
            "gems": [
                ("critical_bead_1", 1, 0.1),
                ("accuracy_bead_1", 1, 0.1),
                ("anti_crit_rune_1", 1, 0.1),
            ],
            "materials": [
                ("upgrade_stone_low", 1, 0.2),
            ],
            "gold": (2000, 8000)
        }
    }

    # 宝箱名称映射
    CHEST_NAMES = {
        "overlord": "深渊霸主宝箱",
        "king": "深渊王者宝箱",
        "warrior": "深渊勇士宝箱",
        "explorer": "深渊探索者宝箱",
        "challenger": "深渊挑战者宝箱",
        "participant": "深渊参与者宝箱"
    }

    # 克苏鲁风格描述
    FLAVOR_TEXTS = [
        "🌀 宝箱中散发出深渊的气息，仿佛在低语着古老的秘密...",
        "👁️ 无数眼球在宝箱内闪烁，见证着你的收获...",
        "🔮 扭曲的能量从宝箱中涌出，化作珍贵的奖励...",
        "⚡ 虚空的力量凝聚成实体，成为你战斗的助力...",
        "🌊 深渊的馈赠降临，带来不可名状的力量..."
    ]

    def __init__(
        self,
        player_repo: PlayerRepository,
        item_repo: ItemRepository
    ):
        """
        初始化世界BOSS宝箱服务

        Args:
            player_repo: 玩家仓储
            item_repo: 物品仓储
        """
        self._player_repo = player_repo
        self._item_repo = item_repo

    async def execute(
        self,
        player: Player,
        item_cfg: ItemConfig,
        quantity: int,
        context_type: str = "world"
    ) -> EffectResult:
        """
        执行世界BOSS宝箱开启效果

        Args:
            player: 玩家对象
            item_cfg: 物品配置
            quantity: 宝箱数量
            context_type: 上下文类型（默认"world"）

        Returns:
            EffectResult: 执行结果，包含奖励详情
        """
        # 获取宝箱等级
        tier = item_cfg.effect_params.get("tier", "participant")

        # 获取对应等级的奖励池
        pool = self.REWARD_POOLS.get(tier, self.REWARD_POOLS["participant"])
        rewards: List[str] = []

        # 处理多个宝箱
        for _ in range(quantity):
            # 1. 金币奖励（必得）
            gold_min, gold_max = pool["gold"]
            gold_reward = random.randint(gold_min, gold_max)
            player.gold += gold_reward
            rewards.append(f"💰 {gold_reward:,} 金币")

            # 2. 镶嵌物奖励（概率性）
            if "gems" in pool:
                for gem_id, gem_qty, probability in pool["gems"]:
                    if random.random() < probability:
                        # 创建镶嵌物实例
                        gem_item = ItemInstance(
                            player_id=player.id,
                            item_id=gem_id,
                            quantity=gem_qty,
                            created_at=datetime.now()
                        )
                        await self._item_repo.add(gem_item)

                        # 获取物品配置以显示名称
                        from ..config import config
                        gem_config = config.items_config["by_id"].get(gem_id)
                        if gem_config:
                            rewards.append(f"💎 {gem_config.get_display_name()} x{gem_qty}")

            # 3. 材料奖励（概率性）
            if "materials" in pool:
                for material_id, material_qty, probability in pool["materials"]:
                    if random.random() < probability:
                        # 创建材料实例
                        material_item = ItemInstance(
                            player_id=player.id,
                            item_id=material_id,
                            quantity=material_qty,
                            created_at=datetime.now()
                        )
                        await self._item_repo.add(material_item)

                        # 获取物品配置以显示名称
                        from ..config import config
                        material_config = config.items_config["by_id"].get(material_id)
                        if material_config:
                            rewards.append(f"🔮 {material_config.get_display_name()} x{material_qty}")

        # 如果没有任何奖励（理论上不会发生，因为金币必得）
        if not rewards:
            rewards.append("💰 少量金币")

        # 更新玩家信息
        await self._player_repo.update(player)

        # 构建结果消息
        chest_name = self.CHEST_NAMES.get(tier, "神秘宝箱")
        qty_text = f" x{quantity}" if quantity > 1 else ""

        result_lines = [
            f"🎁 开启 {chest_name}{qty_text}",
            "✨ 获得奖励：",
            *[f"  {reward}" for reward in rewards]
        ]

        # 添加克苏鲁风格的描述
        result_lines.append("")
        result_lines.append(random.choice(self.FLAVOR_TEXTS))

        # 构建 EffectResult
        return EffectResult(
            success=True,
            message="\n".join(result_lines),
            attribute_changes={
                "gold": sum(
                    random.randint(pool["gold"][0], pool["gold"][1])
                    for _ in range(quantity)
                )
            },
            extra_data={
                "tier": tier,
                "chest_name": chest_name,
                "quantity": quantity,
                "rewards": rewards
            }
        )
