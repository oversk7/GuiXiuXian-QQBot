"""
扫荡诡域业务逻辑服务（DI架构版本）

提供扫荡诡域的核心业务逻辑：
1. 诡域配置解析（支持层级诡域和命名诡域）
2. 资源消耗计算（理智、血量、装备耐久度限制）
3. 格子分配（材料、怪物、休息）——不含宝箱和商人格子，鼓励手动探索
4. 奖励计算（经验、材料）
5. 幸运值影响
6. 装备耐久度扣除（至少保留1点，不自动卸下）
7. Feature Flag集成（USE_NEW_EQUIPMENT_SERVICE）

此版本采用依赖注入架构，通过Repository访问数据。
"""

import random
from typing import List, Tuple, Optional
from ..models import Player
from ..models.inventory import ItemConfig, ItemInstance
from ..config import config
from ..utils import luck_prob, apply_defense_mitigation
from ..utils_markdown import cmd
from ..world.dungeon_generation_service import calculate_monster_attributes, get_region_materials, get_materials_by_rarity
from ..infrastructure.repositories.item_repository import ItemRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..domain.effects.interfaces import EffectResult
from .sweep_preferences import RARITY_ORDER, get_keep_rarities, preference_label

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

        # ===== 装备状态预检（在消耗咒抗之前） =====
        equipped_items = await self._item_repo.get_equipped_equipment(
            player.id,
            config.items_config["by_type"]["EQUIPMENT"]
        )

        # 计算怪物格子比例
        monster_ratio = 0.75  # 75%怪物格子
        mp_cost_per_tile = region_config.get("mp_cost", 1)
        mp_limit = player.mp // mp_cost_per_tile
        no_equip_warning = ""

        if not equipped_items:
            # 无装备：不拦截，但在结果中提醒
            durability_limit = float('inf')
            no_equip_warning = "⚠️ 你当前未穿戴任何装备，防御较低，扫荡伤害会更高\n💡 穿戴装备或使用「修理装备」可提升扫荡效果\n"
        else:
            min_durability = min(eq.durability for eq in equipped_items)
            min_dur_equip = min(equipped_items, key=lambda e: e.durability)

            # 耐久为0：拦截
            if min_durability == 0:
                return EffectResult(
                    success=False,
                    message=(
                        f"⛔ 装备「{min_dur_equip.config.name}」耐久度为0，无法扫荡！\n"
                        f"💡 点击 {cmd('一键修理')} 修复后再使用扫荡令"
                    ),
                    extra_data={"use_markdown": True}
                )

            durability_limit = int(min_durability / monster_ratio)

            # 耐久过低预警（可探索格子≤5格）
            if durability_limit <= 5 and durability_limit <= mp_limit:
                return EffectResult(
                    success=False,
                    message=(
                        f"⛔ 装备耐久度过低，扫荡收益极少！\n"
                        f"🔧 「{min_dur_equip.config.name}」耐久仅剩 **{min_durability}**，"
                        f"最多只能探索 **{durability_limit * quantity}** 格\n"
                        f"💡 点击 {cmd('一键修理')} 修复后再扫荡，避免浪费扫荡令"
                    ),
                    extra_data={"use_markdown": True}
                )

        base_tiles = min(mp_limit, durability_limit)

        # ===== 预检通过，消耗咒抗 =====
        player.stamina -= quantity

        # 获取诡域基础信息
        level_range = region_config["level_range"]
        avg_level = (level_range[0] + level_range[1]) // 2

        # 计算怪物平均伤害
        monster_attrs = calculate_monster_attributes(avg_level, is_elite=False)
        monster_damage = monster_attrs["attack"]

        # 计算免伤率
        mitigation = apply_defense_mitigation(monster_damage, player.defense)
        actual_damage_per_hit = mitigation["final_damage"]

        # 计算实际探索格子数
        total_tiles = max(1, base_tiles * quantity)

        # 按世界地图格子概率分配格子类型（不含宝箱和商人格子）
        material_tiles = 20 * total_tiles // 100
        monster_tiles = 75 * total_tiles // 100
        rest_tiles = 5 * total_tiles // 100

        # ===== 计算收获 =====
        # 经验
        exploration_exp = monster_tiles * random.randint(1, 4) * avg_level
        player.exp += exploration_exp

        # 先生成所有来源掉落，保持原抽样顺序，再合并、筛选并统一入包。
        materials_gained = []
        if monster_tiles > 0:
            materials_gained.extend(await self._calculate_high_grade_rewards(
                player, avg_level, monster_tiles
            ))
        if material_tiles > 0:
            materials_gained.extend(await self._calculate_material_rewards(
                player, material_tiles
            ))
        material_info, overflow_info, discarded_info = await self._process_material_rewards(
            player, materials_gained
        )

        # ===== 计算消耗 =====
        # 装备耐久
        durability_warnings = []
        if monster_tiles > 0:
            durability_warnings = await self._handle_equipment_durability(
                player, equipped_items, monster_tiles
            )

        # 理智
        mp_consumed = total_tiles * mp_cost_per_tile
        player.mp = max(0, player.mp - mp_consumed)
        died = False
        if player.mp == 0 and player.hp > 0:
            player.hp = 0
            player.dungeon_kill_streak = 0  # 死亡清空无伤连杀
            died = True

        # 血量（已疯狂身亡则不再保底回血）
        hp_consumed = monster_tiles * actual_damage_per_hit
        if not died:
            player.hp = max(1, player.hp - hp_consumed)

        # 更新玩家
        await self._player_repo.update(player)

        # ===== 构建 Markdown 消息 =====
        msg = self._build_sweep_markdown(
            player=player,
            region=player.region,
            quantity=quantity,
            total_tiles=total_tiles,
            monster_tiles=monster_tiles,
            material_tiles=material_tiles,
            rest_tiles=rest_tiles,
            exploration_exp=exploration_exp,
            material_info=material_info,
            mp_consumed=mp_consumed,
            hp_consumed=hp_consumed,
            durability_limit=durability_limit,
            mp_limit=mp_limit,
            durability_warnings=durability_warnings,
            no_equip_warning=no_equip_warning,
            died=died,
            overflow_info=overflow_info,
            discarded_info=discarded_info,
        )

        return EffectResult(
            success=True,
            message=msg,
            attribute_changes={
                "exp": exploration_exp,
                "stamina": -quantity,
                "mp": -mp_consumed,
                "hp": -hp_consumed
            },
            extra_data={"use_markdown": True}
        )

    def _build_sweep_markdown(
        self, *, player, region, quantity, total_tiles,
        monster_tiles, material_tiles, rest_tiles,
        exploration_exp, material_info,
        mp_consumed, hp_consumed,
        durability_limit, mp_limit,
        durability_warnings, no_equip_warning, died,
        overflow_info, discarded_info,
    ) -> str:
        """构建扫荡结果的 Markdown 消息"""
        # 霸气宣言
        declarations = [
            "「此地诡异，皆为我所驭！」",
            "「区区邪祟，岂敢阻我道路！」",
            "「天地万物，尽在掌握之中！」",
            "「诡域之力，为我所用！」",
            "「鬼神退避，唯我独尊！」",
        ]
        lines = [f"⚡ {random.choice(declarations)}", ""]

        # ── 无装备提醒 ──
        if no_equip_warning:
            lines.append("⚠️ 未穿戴装备，防御较低，伤害更高")
            lines.append("")

        # ── 探索概况 ──
        lines.append(f"**━━ 扫荡报告 · {region} ━━**")
        lines.append(f"🗺️ 探索 **{total_tiles}** 格（怪物{monster_tiles} / 材料{material_tiles} / 驿站{rest_tiles}）")
        if durability_limit != float('inf') and durability_limit < mp_limit:
            lines.append(f"📊 耐久 **{durability_limit}** ← 瓶颈 | 理智 {mp_limit}")
        else:
            dur_display = durability_limit if durability_limit != float('inf') else "∞"
            lines.append(f"📊 理智 **{mp_limit}** | 耐久 {dur_display}")
        lines.append("")

        lines.append(f"保留品质：**{preference_label(get_keep_rarities(player))}**")
        if discarded_info:
            lines.append(f"**按品质设置舍弃**：{' | '.join(discarded_info)}")
        lines.append("")

        # ── 收获 ──
        lines.append("**━━ 收获 ━━**")
        lines.append(f"📚 经验 **+{exploration_exp:,}**")
        if material_info:
            lines.append(f"💎 {' | '.join(material_info)}")
        if overflow_info:
            lines.append(f"⚠️ **背包已满，溢出丢失**：{' | '.join(overflow_info)}")
            lines.append(f"💡 {cmd('整理背包')} 或献祭/存入仓库腾出空间后再扫荡")
        lines.append("")

        # ── 消耗 ──
        lines.append("**━━ 消耗 ━━**")
        lines.append(
            f"⚡咒抗 -{quantity}（剩{player.stamina}）"
            f" 🧠理智 -{mp_consumed}（剩{player.mp}）"
            f" ❤️血量 -{hp_consumed}（剩{player.hp}）"
        )
        if died:
            lines.append("💀 **理智耗尽，陷入疯狂！**")
        lines.append("")

        # ── 装备状态 ──
        if durability_warnings:
            lines.append("**━━ 装备警告 ━━**")
            for w in durability_warnings:
                # 将原有的多行警告压缩为单行 markdown
                lines.append(w.replace("\n   ", " "))
            lines.append("")

        # ── 瓶颈提示 ──
        if durability_limit != float('inf') and durability_limit < mp_limit:
            lines.append(f"🔧 修理装备后扫荡格子可从 {durability_limit} 提升至 {mp_limit}")
            lines.append("")

        # ── 快捷操作按钮 ──
        buttons = [
            cmd("再次扫荡", "使用 扫荡令"),
            cmd("一键修理", "一键修理"),
            cmd("背包", "背包"),
            cmd("扫荡设置", "扫荡设置"),
        ]
        lines.append(" | ".join(buttons))

        return "\n".join(lines)

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
    ) -> List[Tuple[str, int]]:
        """
        估算打怪获得的高级奖励（基于怪物格子数），仅生成掉落

        Args:
            player: 玩家对象
            avg_level: 怪物平均等级
            monster_tiles: 怪物格子数

        Returns:
            材料列表 [(material_id, quantity), ...]
        """
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
                # 橙色除外：只从档位商人池掉落，与战斗掉落及图鉴标注保持一致
                if not candidate_materials and rarity != "orange":
                    candidate_materials = get_materials_by_rarity(rarity)

                if candidate_materials:
                    material_id = random.choice(candidate_materials)
                    estimated_drops[material_id] = expected_count

        return list(estimated_drops.items())

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

    async def _process_material_rewards(
        self,
        player: Player,
        materials_gained: List[Tuple[str, int]],
    ) -> Tuple[List[str], List[str], List[str]]:
        """
        合并所有来源材料，按白名单筛选掉落，按真实品质降序入包

        背包放不下的部分记录为溢出，报告中只显示实际入库数量。

        Args:
            player: 玩家对象
            materials_gained: 材料列表 [(material_id, quantity), ...]

        Returns:
            (实际入包列表, 容量溢出列表, 按设置舍弃列表)
        """
        # 合并相同材料的数量
        material_summary = {}
        for material_id, quantity in materials_gained:
            if material_id in material_summary:
                material_summary[material_id] += quantity
            else:
                material_summary[material_id] = quantity

        # 实际入库并生成显示信息
        material_info = []
        overflow_info = []
        discarded_info = []
        keep_rarities = get_keep_rarities(player)
        by_id = config.items_config["by_id"]
        sorted_materials = sorted(
            material_summary.items(),
            key=lambda entry: RARITY_ORDER.get(getattr(by_id.get(entry[0]), "rarity", "white"), 0),
            reverse=True,
        )
        for material_id, total_quantity in sorted_materials:
            item_config = config.items_config["by_id"].get(material_id)
            if not item_config:
                continue
            if item_config.rarity not in keep_rarities:
                discarded_info.append(f"{item_config.get_display_name()} ✖️{total_quantity}")
                continue
            added = await self._item_repo.add_item_partial(player.id, material_id, total_quantity)
            if added > 0:
                material_info.append(f"{item_config.get_display_name()} ✖️{added}")
            lost = total_quantity - added
            if lost > 0:
                overflow_info.append(f"{item_config.get_display_name()} ✖️{lost}")

        return material_info, overflow_info, discarded_info

    async def _handle_equipment_durability(
        self,
        player: Player,
        equipped_items: List[ItemInstance],
        monster_tiles: int
    ) -> List[str]:
        """
        扣除装备耐久度（基于怪物格子数）
        扫荡最多扣至1点耐久，保留穿戴状态和装备属性。

        Args:
            player: 玩家对象
            equipped_items: 已装备物品列表
            monster_tiles: 怪物格子数

        Returns:
            耐久度警告列表
        """
        durability_warnings = []

        for eq in equipped_items:
            actual_loss = min(monster_tiles, max(0, eq.durability - 1))
            eq.durability -= actual_loss

            if eq.durability == 1:
                durability_warnings.append(
                    f"⚠️ {eq.config.name} 耐久仅剩1，仍保持穿戴，请及时一键修理"
                )
            elif eq.durability <= 10:
                durability_warnings.append(
                    f"⚠️ {eq.config.name} 耐久度较低 ({eq.durability}/{eq.config.durability})，建议及时修理"
                )

        # 批量更新装备
        if equipped_items:
            await self._item_repo.update_extra_attrs_batch(equipped_items)

        return durability_warnings
