"""
扫荡诡域业务逻辑服务（DI架构版本）

提供扫荡诡域的核心业务逻辑：
1. 诡域配置解析（支持层级诡域和命名诡域）
2. 资源消耗计算（理智、血量、装备耐久度限制）
3. 格子分配（材料、宝藏、怪物、休息）
4. 奖励计算（经验、材料、金币）
5. 幸运值影响
6. 装备耐久度扣除和自动卸下
7. Feature Flag集成（USE_NEW_EQUIPMENT_SERVICE）

此版本采用依赖注入架构，通过Repository访问数据。
"""

import random
from typing import List, Tuple, Optional
from ..models import Player
from ..models.inventory import ItemConfig, ItemInstance
from ..config import config
from ..utils import luck_prob, apply_defense_mitigation
from ..world.dungeon_battle import calculate_monster_attributes, get_region_materials, get_materials_by_rarity
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..domain.effects.interfaces import EffectResult

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的EquipmentService，False使用旧版本
# =====================================================


class SweepDungeonService:
    """扫荡诡域服务（DI架构）"""

    def __init__(
        self,
        player_repo: PlayerRepository,
        item_repo: ItemRepository,
        equipment_service=None  # Optional[EquipmentService], 延迟导入避免循环依赖
    ):
        """
        初始化扫荡诡域服务

        Args:
            player_repo: 玩家仓储
            item_repo: 物品仓储
            equipment_service: 装备服务（可选，用于recalc_equipment_attributes）
        """
        self._player_repo = player_repo
        self._item_repo = item_repo
        self._equipment_service = equipment_service

    async def execute(
        self,
        player: Player,
        item_cfg: ItemConfig,
        quantity: int,
        context_type: str = "world"
    ) -> EffectResult:
        """
        执行扫荡诡域效果

        Args:
            player: 玩家对象
            item_cfg: 物品配置（扫荡令）
            quantity: 使用数量
            context_type: 上下文类型（默认"world"）

        Returns:
            EffectResult: 执行结果
        """
        # 检查是否在诡域中
        if player.region == "大都会":
            return EffectResult(
                success=False,
                message="⛔ 你在现实世界中，无法使用扫荡令"
            )

        # 检查咒抗是否足够
        if player.stamina < quantity:
            return EffectResult(
                success=False,
                message=f"⛔ 咒抗不足，需要 {quantity} 点咒抗"
            )

        # 获取当前诡域配置（支持无限层诡域）
        region_config = await self._get_region_config(player.region)
        if not region_config:
            return EffectResult(
                success=False,
                message="⛔ 未知的诡域，无法扫荡"
            )

        # 消耗咒抗
        player.stamina -= quantity

        # 霸气宣言
        sweep_declarations = [
            "⚡ 「此地诡异，皆为我所驭！」",
            "⚡ 「区区邪祟，岂敢阻我道路！」",
            "⚡ 「天地万物，尽在掌握之中！」",
            "⚡ 「诡域之力，为我所用！」",
            "⚡ 「鬼神退避，唯我独尊！」"
        ]
        declaration = random.choice(sweep_declarations)
        results = [declaration, ""]

        # 获取诡域基础信息
        level_range = region_config["level_range"]
        avg_level = (level_range[0] + level_range[1]) // 2
        mp_cost_per_tile = region_config.get("mp_cost", 1)  # 每格理智消耗

        # 计算怪物格子比例 (x)
        tile_weights = [15, 5, 75, 5]  # 材料、宝藏、怪物、休息
        monster_ratio = tile_weights[2] / 100  # 怪物格子比例 x = 0.75

        # 计算怪物平均伤害
        monster_attrs = calculate_monster_attributes(avg_level, is_elite=False)
        monster_damage = monster_attrs["attack"]

        # 计算免伤率
        mitigation = apply_defense_mitigation(monster_damage, player.defense)
        actual_damage_per_hit = mitigation["final_damage"]

        # 计算各种限制下的最大格子数
        # 1. 理智限制：player.mp / 每格mp消耗
        mp_limit = player.mp // mp_cost_per_tile

        # 2. 血量限制：已取消，扫荡令不再受血量限制
        # hp_limit = int(player.hp / actual_damage_per_hit / monster_ratio) if monster_ratio > 0 else float('inf')

        # 3. 装备耐久度限制：查询已装备装备的最低耐久度 / x
        # 新规则：允许降至0；0则自动卸下且无法穿戴
        durability_limit = float('inf')
        equipped_items = await self._item_repo.get_equipped_equipment(
            player.id,
            config.items_config["by_type"]["EQUIPMENT"]
        )

        if equipped_items:
            min_durability = min(eq.durability for eq in equipped_items)
            available_durability = max(0, min_durability)
            durability_limit = int(available_durability / monster_ratio) if monster_ratio > 0 and available_durability > 0 else 0

        # 取最小值作为实际能探索的格子数（不再考虑hp限制），再乘以扫荡令数量
        base_tiles = min(mp_limit, durability_limit)
        total_tiles = base_tiles * quantity

        # 检查是否因为装备耐久度过低而无法扫荡
        if durability_limit == 0 and equipped_items:
            min_durability = min(eq.durability for eq in equipped_items)
            return EffectResult(
                success=False,
                message=f"⛔ 装备耐久度过低，无法进行扫荡！最低装备耐久度为{min_durability}，建议修理后再使用扫荡令"
            )

        # 确保至少有1个格子
        total_tiles = max(1, total_tiles)

        results.append(f"🗺️ 探索格子共计: {total_tiles}个")
        results.append(f"📊 限制因素: 理智({mp_limit}) 耐久({durability_limit if durability_limit != float('inf') else '∞'}) (生命限制已取消)")

        # 按世界地图格子概率分配格子类型
        tile_weights = [15, 5, 75, 5]  # 材料、宝藏、怪物(避开)、休息
        tile_types = ["MATERIAL", "TREASURE", "EMPTY", "REST"]

        # 分配各类型格子数量
        material_tiles = tile_weights[0] * total_tiles // 100
        treasure_tiles = tile_weights[1] * total_tiles // 100
        monster_tiles = tile_weights[2] * total_tiles // 100
        rest_tiles = tile_weights[3] * total_tiles // 100

        # 探索经验
        exploration_exp = monster_tiles * random.randint(1, 4) * avg_level
        player.exp += exploration_exp
        results.append(f"📚 探索获得经验: {exploration_exp} (探索格子×{monster_tiles})")

        # 估算打怪获得的高级奖励（基于怪物格子数）
        high_grade_rewards = []
        if monster_tiles > 0:
            high_grade_rewards = await self._calculate_high_grade_rewards(
                player, avg_level, monster_tiles
            )
            if high_grade_rewards:
                results.append(f"✨ 打怪获得高级奖励: {', '.join(high_grade_rewards)}")

        # 计算材料奖励 - 扫荡主要获得基础材料
        materials_gained = []
        if material_tiles > 0:
            materials_gained = await self._calculate_material_rewards(
                player, material_tiles
            )

        # 计算金币奖励（来自宝藏格子）
        total_gold = 0
        if treasure_tiles > 0:
            total_gold = self._calculate_treasure_rewards(player, treasure_tiles)
            player.gold += total_gold
            results.append(f"💰 发现宝藏获得金币: {total_gold} (宝藏格子×{treasure_tiles})")

        # 处理材料奖励 - 合并相同材料
        if materials_gained:
            material_info = await self._process_material_rewards(
                player, materials_gained, material_tiles
            )
            if material_info:
                results.append(f"💎 采集材料: {', '.join(material_info)} (材料格子×{material_tiles})")

        # 休息格子只展示数量，因为扫荡本就不耗状态
        if rest_tiles > 0:
            results.append(f"🛌 (遇到驿站×{rest_tiles}次)")

        # 扣除装备耐久度（基于怪物格子数）
        durability_warnings = []
        if monster_tiles > 0:
            durability_warnings = await self._handle_equipment_durability(
                player, equipped_items, monster_tiles
            )
            if durability_warnings:
                results.extend(durability_warnings)

        # 扣除理智值（基于总格子数和每格消耗）
        mp_consumed = total_tiles * mp_cost_per_tile
        player.mp = max(0, player.mp - mp_consumed)
        if player.mp == 0 and player.hp > 0:
            player.hp = 0  # 理智耗尽即"疯狂身亡"
            results.append("💀 理智耗尽，陷入疯狂！")

        # 扣除血量（基于怪物格子数和实际伤害）
        hp_consumed = monster_tiles * actual_damage_per_hit
        player.hp = max(1, player.hp - hp_consumed)

        results.append(f"⚡ 消耗咒抗: {quantity} (剩余: {player.stamina})")
        results.append(f"🧠 消耗理智: {mp_consumed} (剩余: {player.mp})")
        results.append(f"❤️ 消耗血量: {hp_consumed} (剩余: {player.hp})")

        # 更新玩家
        await self._player_repo.update(player)

        return EffectResult(
            success=True,
            message="\n".join(results),
            attribute_changes={
                "exp": exploration_exp,
                "gold": total_gold,
                "stamina": -quantity,
                "mp": -mp_consumed,
                "hp": -hp_consumed
            }
        )

    async def _get_region_config(self, region: str) -> Optional[dict]:
        """
        获取诡域配置（支持层级诡域和命名诡域）

        Args:
            region: 区域名称

        Returns:
            区域配置字典，如果不存在则返回None
        """
        region_config = None
        if "层诡域" in region:
            # 新的层级制诡域
            try:
                level_str = region.replace("层诡域", "")
                # 兼容"第N层诡域"格式，移除开头的"第"字
                if level_str.startswith("第"):
                    level_str = level_str[1:]
                level = int(level_str)
                # 优先从预生成配置获取，如果不存在则动态生成（支持无限层）
                region_config = config.map_config.get("dungeon_levels", {}).get(level)
                if not region_config:
                    # 动态生成超过100层的配置
                    region_config = config._generate_dungeon_level_config(
                        level, config.map_config.get("dungeon_generation_rules", {})
                    )
            except ValueError:
                return None
        else:
            # 兼容旧的命名诡域
            region_config = config.map_config["regions"].get(region)

        return region_config

    async def _calculate_high_grade_rewards(
        self,
        player: Player,
        avg_level: int,
        monster_tiles: int
    ) -> List[str]:
        """
        估算打怪获得的高级奖励（基于怪物格子数）

        Args:
            player: 玩家对象
            avg_level: 怪物平均等级
            monster_tiles: 怪物格子数

        Returns:
            高级奖励列表（显示用）
        """
        high_grade_rewards = []
        estimated_drops = {}

        # 根据怪物等级确定掉落概率
        if avg_level <= 20:
            drop_rates = {"white": 0.30, "green": 0.10}
        elif avg_level <= 60:
            drop_rates = {"white": 0.40, "green": 0.20, "blue": 0.05}
        elif avg_level <= 100:
            drop_rates = {"white": 0.30, "green": 0.25, "blue": 0.15, "purple": 0.03}
        else:
            drop_rates = {"white": 0.20, "green": 0.20, "blue": 0.20, "purple": 0.08, "orange": 0.01}

        # 获取当前区域材料配置
        region_materials = get_region_materials(player.region)

        # 估算每种稀有度材料的获得数量
        for rarity, base_rate in drop_rates.items():
            if rarity == "white":  # 白色材料不算高级奖励
                continue

            # 考虑幸运值影响
            final_rate = base_rate * (1 + luck_prob(player.luck))
            expected_count = int(monster_tiles * final_rate)

            if expected_count > 0:
                # 优先从区域商人材料中选择（与战斗掉落逻辑一致）
                candidate_materials = []
                for material_id in region_materials["merchant"]:
                    item_config = config.items_config["by_id"].get(material_id)
                    if item_config and item_config.rarity == rarity:
                        candidate_materials.append(material_id)

                # 如果区域没有对应稀有度的材料，从全局材料中选择
                if not candidate_materials:
                    candidate_materials = get_materials_by_rarity(rarity)

                if candidate_materials:
                    material_id = random.choice(candidate_materials)
                    estimated_drops[material_id] = expected_count

        # 添加估算的高级材料到背包
        for material_id, count in estimated_drops.items():
            try:
                await self._item_repo.add_item(player.id, material_id, count)
                material_config = config.items_config["by_id"].get(material_id)
                if material_config:
                    high_grade_rewards.append(f"{material_config.get_display_name()} ✖️{count}")
            except ValueError:
                # 背包满了，跳过
                pass

        return high_grade_rewards

    async def _calculate_material_rewards(
        self,
        player: Player,
        material_tiles: int
    ) -> List[Tuple[str, int]]:
        """
        计算材料奖励 - 扫荡主要获得基础材料

        Args:
            player: 玩家对象
            material_tiles: 材料格子数

        Returns:
            材料列表 [(material_id, quantity), ...]
        """
        materials_gained = []
        region_materials = get_region_materials(player.region)
        basic_materials = region_materials["basic"]

        if basic_materials:
            for _ in range(material_tiles):
                material_id = random.choice(basic_materials)

                # 基础数量2-4个（扫荡效率更高）
                base_quantity = random.randint(2, 4)

                # 幸运加成
                if random.random() < luck_prob(player.luck):
                    base_quantity = int(base_quantity * 1.5)  # 幸运1.5倍

                materials_gained.append((material_id, base_quantity))
        else:
            # 如果没有配置基础材料，从白色材料中随机选择
            white_materials = get_materials_by_rarity("white")
            for _ in range(material_tiles):
                if white_materials:
                    material_id = random.choice(white_materials)
                    base_quantity = random.randint(2, 4)
                    if random.random() < luck_prob(player.luck):
                        base_quantity = int(base_quantity * 1.5)
                    materials_gained.append((material_id, base_quantity))

        return materials_gained

    def _calculate_treasure_rewards(
        self,
        player: Player,
        treasure_tiles: int
    ) -> int:
        """
        计算金币奖励（来自宝藏格子）

        Args:
            player: 玩家对象
            treasure_tiles: 宝藏格子数

        Returns:
            总金币数量
        """
        total_gold = 0
        for _ in range(treasure_tiles):
            # 单个宝藏格子金币
            base_gold = random.randint(50, 200)
            # 幸运加成
            if random.random() < luck_prob(player.luck):
                base_gold = int(base_gold * 1.3)  # 幸运1.3倍
            total_gold += base_gold

        return total_gold

    async def _process_material_rewards(
        self,
        player: Player,
        materials_gained: List[Tuple[str, int]],
        material_tiles: int
    ) -> List[str]:
        """
        处理材料奖励 - 合并相同材料并添加到背包

        Args:
            player: 玩家对象
            materials_gained: 材料列表 [(material_id, quantity), ...]
            material_tiles: 材料格子数

        Returns:
            材料信息列表（显示用）
        """
        # 合并相同材料的数量
        material_summary = {}
        for material_id, quantity in materials_gained:
            if material_id in material_summary:
                material_summary[material_id] += quantity
            else:
                material_summary[material_id] = quantity

        # 生成显示信息
        material_info = []
        merged_materials = []
        for material_id, total_quantity in material_summary.items():
            item_config = config.items_config["by_id"].get(material_id)
            if item_config:
                material_info.append(f"{item_config.get_display_name()} ✖️{total_quantity}")
                merged_materials.append((material_id, total_quantity))

        if merged_materials:
            # 将合并后的材料信息存储到player的临时属性中，供调用方处理
            if not hasattr(player, '_sweep_materials'):
                player._sweep_materials = []
            player._sweep_materials.extend(merged_materials)

        return material_info

    async def _handle_equipment_durability(
        self,
        player: Player,
        equipped_items: List[ItemInstance],
        monster_tiles: int
    ) -> List[str]:
        """
        扣除装备耐久度（基于怪物格子数）
        新规则：允许降至0；降至0将自动卸下且需修理后才能穿戴

        Args:
            player: 玩家对象
            equipped_items: 已装备物品列表
            monster_tiles: 怪物格子数

        Returns:
            耐久度警告列表
        """
        durability_warnings = []
        needs_recalc = False

        for eq in equipped_items:
            durability_loss = monster_tiles
            actual_loss = min(durability_loss, eq.durability)

            if actual_loss > 0:
                eq.durability -= actual_loss
                if eq.durability == 0:
                    # 自动卸下并回退属性加成
                    delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                    for k, v in delta.items():
                        current_value = getattr(player, k, 0)
                        setattr(player, k, max(0, current_value - v))
                    eq.equipped = False
                    needs_recalc = True
                    durability_warnings.append(
                        f"💔 {eq.config.name} 耐久耗尽已自动卸下\n"
                        f"   ⚠️ 需修理后才能再次穿戴"
                    )
                elif eq.durability <= 10:
                    durability_warnings.append(
                        f"⚠️ {eq.config.name} 耐久度较低 ({eq.durability}/{eq.config.durability})，建议及时修理"
                    )

        # 批量更新装备
        if equipped_items:
            await self._item_repo.update_extra_attrs_batch(equipped_items)

        if needs_recalc:
            # 新版本: 使用DI架构的EquipmentService
            await self._equipment_service.recalc_equipment_attributes(player)
        return durability_warnings
