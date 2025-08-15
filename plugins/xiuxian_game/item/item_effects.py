from __future__ import annotations

"""道具效果执行器注册表
所有可使用道具的真正逻辑在此统一处理。
新增效果时，只需编写带 @register 装饰器的协程函数。
"""

from typing import Callable, Awaitable, Dict, Tuple
from ..models.player import Player
from ..models.inventory import ItemEffectType, ItemConfig, ItemInstance, ItemType
from ..models.elixir_usage import ElixirUsageLog
from datetime import date

# 类型别名
EffectHandler = Callable[[Player, ItemConfig, int, str, object], Awaitable[Tuple[bool, str]]]

# 注册表
_REGISTRY: Dict[ItemEffectType, EffectHandler] = {}


def register(effect_type: ItemEffectType):
    """装饰器：注册效果处理函数"""
    def decorator(func: EffectHandler):
        _REGISTRY[effect_type] = func
        return func
    return decorator



async def apply_effect(player: Player, item_cfg: ItemConfig, quantity: int = 1, ctx: str = "world", session=None) -> Tuple[bool, str]:
    """根据 item_cfg 调用对应处理器

    参数
    ------
    player : Player
        目标玩家实例（已绑定到 SQLAlchemy Session）
    item_cfg : ItemConfig
        物品配置
    quantity : int
        使用数量
    ctx : str
        使用场景。可选示例："world"、"battle"、"death" 等
    session : AsyncSession
        数据库会话，用于耐药性处理

    返回值
    ------
    (success, message) : Tuple[bool,str]
        success 为 False 时表示效果未生效（例如血量已满），调用方可据此决定是否扣除物品。
    """
    handler = _REGISTRY.get(item_cfg.effect_type)
    if not handler:
        # 未实现效果
        return False, "❓ 该道具效果尚未实现"
    return await handler(player, item_cfg, quantity, ctx, session)


async def update_elixir_usage(session, player: Player, item_cfg: ItemConfig, quantity: int = 1):
    """更新丹药使用记录

    Args:
        session: 数据库会话
        player: 玩家对象
        item_cfg: 物品配置
        quantity: 使用数量
    """
    # 只有丹药才需要记录使用量
    if item_cfg.item_id.endswith("_elixir"):
        log = await ElixirUsageLog.get_or_create_log(session, player.id, item_cfg.item_id)
        log.quantity += quantity


# ---------------- 具体效果实现 ----------------

@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"
    if player.hp >= player.max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"
    player.hp = min(player.max_hp, player.hp + value)
    return True, f"❤️ 恢复 {value} 点生命值 (当前 {player.hp}/{player.max_hp})"


@register(ItemEffectType.RESTORE_MP)
async def _restore_mp(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复理智"
    if player.mp >= player.max_mp:
        return False, "🧐 你的理智值已满，不需要使用此物品"
    player.mp = min(player.max_mp, player.mp + value)
    return True, f"🧠 恢复 {value} 点理智 (当前 {player.mp}/{player.max_mp})"


@register(ItemEffectType.RESTORE_HP_PERCENT)
async def _restore_hp_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"
    if player.hp >= player.max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"

    # 计算恢复量（效果不减弱）
    percent = float(cfg.effect_params.get("percent", 0)) * qty
    value = int(player.max_hp * percent)
    player.hp = min(player.max_hp, player.hp + value)

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    percent_display = int(percent * 100)
    return True, f"❤️ 恢复 {percent_display}% 生命值 ({value}点) (当前 {player.hp}/{player.max_hp})"


@register(ItemEffectType.RESTORE_MP_PERCENT)
async def _restore_mp_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复理智"
    if player.mp >= player.max_mp:
        return False, "🧐 你的理智值已满，不需要使用此物品"

    # 计算恢复量（效果不减弱）
    percent = float(cfg.effect_params.get("percent", 0)) * qty
    value = int(player.max_mp * percent)
    player.mp = min(player.max_mp, player.mp + value)

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    percent_display = int(percent * 100)
    return True, f"🧠 恢复 {percent_display}% 理智值 ({value}点) (当前 {player.mp}/{player.max_mp})"

# 原地复活，与复活指令效果不同
@register(ItemEffectType.REVIVE)
async def _revive(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    if player.hp > 0:
        return False, "🧐 你尚未死亡，无需复活"
    ratio = float(cfg.effect_params.get("rate", 1.0))
    player.hp = max(1, int(player.max_hp * ratio))
    player.mp = max(1, int(player.max_mp * ratio))
    return True, "✨ 你死而复生，继续前进吧！"


@register(ItemEffectType.BUFF)
async def _buff(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """临时 BUFF：直接把属性累加到玩家本体上。复杂持续时间逻辑以后实现。"""
    attrs = cfg.effect_params or {}
    if not attrs:
        return False, "⛔ 该道具没有任何增益"

    # 简单累加（效果不减弱）
    ATTRIBUTE_MAP = {
        "max_hp": "体",
        "max_mp": "智",
        "attack": "力",
        "agility": "敏",
        "luck": "运",
        "defense": "防",
    }

    changed = []
    for k, v in attrs.items():
        if not hasattr(player, k):
            continue
        old = getattr(player, k)
        new_val = old + int(v) * qty
        setattr(player, k, new_val)
        changed.append(f"{ATTRIBUTE_MAP.get(k, k)}+{int(v)*qty}")

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    if not changed:
        return False, "⛔ 增益属性无效"
    return True, f"✨ 获得增益：{', '.join(changed)}"

@register(ItemEffectType.GAIN_EXP)
async def _gain_exp(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """直接获得经验值，道具参数 value 指定单份经验量。"""
    base_value = int(cfg.effect_params.get("value", 0))
    if base_value <= 0:
        return False, "⛔ 该丹药配置错误"

    # 计算经验值（效果不减弱）
    actual_value = base_value * qty
    player.exp += actual_value

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    return True, f"📚 获得 {actual_value} 点经验"


@register(ItemEffectType.GAIN_RESENTMENT)
async def _gain_resentment(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """直接获得怨念值，道具参数 value 指定单份怨念量。"""
    base_value = int(cfg.effect_params.get("value", 0))
    if base_value <= 0:
        return False, "⛔ 该道具配置错误"

    # 计算怨念值（效果不减弱）
    actual_value = base_value * qty
    player.resentment += actual_value

    return True, f"💀 获得 {actual_value} 点怨念值 (当前 {player.resentment})"

@register(ItemEffectType.SWEEP_DUNGEON)
async def _sweep_dungeon(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """扫荡当前诡域，获得经验和材料奖励

    扫荡逻辑：
    1. 根据玩家mp、hp、装备耐久度计算能探索的格子数
    2. 按格子概率分配经验、材料、金币格子
    3. 单个格子经验取决于区域怪物等级
    4. 材料受幸运加成影响，增加高级奖励估算
    """
    import random
    from ..config import config
    from ..utils import luck_prob, damage_reduction_rate
    from ..models.inventory import ItemInstance
    from sqlalchemy import select as _select

    # 检查是否在诡域中
    if player.region == "大都会":
        return False, "⛔ 你在现实世界中，无法使用扫荡令"

    # 检查咒抗是否足够
    if player.stamina < qty:
        return False, f"⛔ 咒抗不足，需要 {qty} 点咒抗"

    # 获取当前诡域配置
    region_config = config.map_config["regions"].get(player.region)
    if not region_config:
        return False, "⛔ 未知的诡域，无法扫荡"

    # 消耗咒抗
    player.stamina -= qty

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
    from ..world import calculate_monster_attributes
    monster_attrs = calculate_monster_attributes(avg_level, is_elite=False)
    monster_damage = monster_attrs["attack"]

    # 计算免伤率
    damage_reduction = damage_reduction_rate(player.defense)
    actual_damage_per_hit = max(1, int(monster_damage * (1 - damage_reduction)))

    # 计算各种限制下的最大格子数
    # 1. 理智限制：player.mp / 每格mp消耗
    mp_limit = player.mp // mp_cost_per_tile

    # 2. 血量限制：player.hp / (怪物单次伤害 * (1-免伤率)) / x
    hp_limit = int(player.hp / actual_damage_per_hit / monster_ratio) if monster_ratio > 0 else float('inf')

    # 3. 装备耐久度限制：查询已装备装备的最低耐久度 / x
    # 注意：装备耐久度不能低于5，避免装备意外损坏
    durability_limit = float('inf')
    if session:
        result_eq = await session.execute(
            _select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
            )
        )
        equipped_items = result_eq.scalars().all()
        if equipped_items:
            min_durability = min(eq.durability for eq in equipped_items)
            # 确保装备耐久度不会低于5，所以可用耐久度 = min_durability - 5
            available_durability = max(0, min_durability - 5)
            durability_limit = int(available_durability / monster_ratio) if monster_ratio > 0 and available_durability > 0 else 0

    # 取最小值作为实际能探索的格子数，再乘以扫荡令数量
    base_tiles = min(mp_limit, hp_limit, durability_limit)
    total_tiles = base_tiles * qty

    # 检查是否因为装备耐久度过低而无法扫荡
    if durability_limit == 0 and equipped_items:
        min_durability = min(eq.durability for eq in equipped_items)
        return False, f"⛔ 装备耐久度过低，无法进行扫荡！最低装备耐久度为{min_durability}，建议修理后再使用扫荡令"

    # 确保至少有1个格子
    total_tiles = max(1, total_tiles)

    results.append(f"🗺️ 探索格子共计: {total_tiles}个")
    results.append(f"📊 限制因素: MP({mp_limit}) HP({hp_limit}) 耐久({durability_limit if durability_limit != float('inf') else '∞'})")

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
        from ..world import get_materials_by_rarity

        # 模拟打怪掉落，估算高级材料获得
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
        from ..world import get_region_materials, get_materials_by_rarity
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
                await ItemInstance.add_item(session, player.id, material_id, count)
                material_config = config.items_config["by_id"].get(material_id)
                if material_config:
                    high_grade_rewards.append(f"{material_config.get_display_name()} ✖️{count}")
            except ValueError:
                # 背包满了，跳过
                pass

        if high_grade_rewards:
            results.append(f"✨ 打怪获得高级奖励: {', '.join(high_grade_rewards)}")

    # 计算材料奖励 - 扫荡主要获得基础材料
    materials_gained = []
    if material_tiles > 0:
        from ..world import get_region_materials, get_materials_by_rarity

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

    # 计算金币奖励（来自宝藏格子）
    total_gold = 0
    if treasure_tiles > 0:
        for _ in range(treasure_tiles):
            # 单个宝藏格子金币
            base_gold = random.randint(50, 200)
            # 幸运加成
            if random.random() < luck_prob(player.luck):
                base_gold = int(base_gold * 1.3)  # 幸运1.3倍
            total_gold += base_gold

        player.gold += total_gold
        results.append(f"💰 发现宝藏获得金币: {total_gold} (宝藏格子×{treasure_tiles})")

    # 处理材料奖励 - 合并相同材料
    if materials_gained:
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

        if material_info:
            results.append(f"💎 采集材料: {', '.join(material_info)} (材料格子×{material_tiles})")
            # 将合并后的材料信息存储到player的临时属性中，供调用方处理
            if not hasattr(player, '_sweep_materials'):
                player._sweep_materials = []
            player._sweep_materials.extend(merged_materials)

    # 休息格子只展示数量，因为扫荡本就不耗状态
    if rest_tiles > 0:
        results.append(f"🛌 (遇到驿站×{rest_tiles}次)")

    # 扣除装备耐久度（基于怪物格子数）
    # 注意：装备耐久度不能低于5，避免装备意外损坏
    if session and monster_tiles > 0:
        result_eq = await session.execute(
            _select(ItemInstance).where(
                ItemInstance.player_id == player.id,
                ItemInstance.equipped == True,
                ItemInstance.item_id.in_(config.items_config["by_type"]["EQUIPMENT"])
            )
        )
        equipped_items = result_eq.scalars().all()
        durability_warnings = []

        for eq in equipped_items:
            # 每个怪物格子消耗1点耐久度，但不能让耐久度低于5
            durability_loss = monster_tiles
            max_loss = max(0, eq.durability - 5)  # 最多只能扣到剩余5点耐久
            actual_loss = min(durability_loss, max_loss)

            if actual_loss > 0:
                eq.durability -= actual_loss
                if eq.durability <= 10:  # 耐久度警告阈值
                    durability_warnings.append(f"⚠️ {eq.config.name} 耐久度较低({eq.durability}/{eq.config.durability})，建议及时修理")

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
    player.hp = max(0, player.hp - hp_consumed)

    results.append(f"⚡ 消耗咒抗: {qty} (剩余: {player.stamina})")
    results.append(f"🧠 消耗理智: {mp_consumed} (剩余: {player.mp})")
    results.append(f"❤️ 消耗血量: {hp_consumed} (剩余: {player.hp})")

    return True, "\n".join(results)

# ---------------- 重置属性 ----------------

@register(ItemEffectType.RESET_ATTR)
async def _reset_attr(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None):
    """重置已分配属性点，保留装备加成和丹药加成。仅允许 qty=1。"""
    if qty != 1:
        return False, "⛔ 重启符一次只能使用 1 个"

    from ..config import config as gcfg
    from sqlalchemy import select
    from ..models.elixir_usage import ElixirUsageLog

    # 初始基础属性
    INIT = {
        "max_hp": 20,
        "max_mp": 20,
        "attack": 1,
        "defense": 5,
        "agility": 5,
        "luck": 1,
    }

    # 累计装备 bonus
    equipment_bonus = {k: 0 for k in INIT}
    # 从 Session 中预加载玩家装备
    eq_list = player.__dict__.get("item_instances")
    if eq_list:
        for eq in eq_list:
            if getattr(eq, "equipped", False) and eq.config and eq.config.type == ItemType.EQUIPMENT:
                delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                for k, v in delta.items():
                    if k in equipment_bonus:
                        equipment_bonus[k] += int(v)

    # 计算丹药加成
    elixir_bonus = {k: 0 for k in INIT}
    if session:
        # 获取所有丹药使用记录（不限日期，因为丹药效果是永久的）
        stmt = select(ElixirUsageLog).where(ElixirUsageLog.player_id == player.id)
        logs = (await session.execute(stmt)).scalars().all()

        # 统计每种丹药的总使用量
        elixir_usage_total = {}
        for log in logs:
            if log.item_id not in elixir_usage_total:
                elixir_usage_total[log.item_id] = 0
            elixir_usage_total[log.item_id] += log.quantity

        # 计算丹药属性加成
        for item_id, total_qty in elixir_usage_total.items():
            item_cfg = gcfg.items_config["by_id"].get(item_id)
            if item_cfg and item_cfg.effect_type == ItemEffectType.BUFF:
                effect_params = item_cfg.effect_params or {}
                for attr, value in effect_params.items():
                    if attr in elixir_bonus:
                        elixir_bonus[attr] += int(value) * total_qty

    # 重置属性为基础值 + 丹药 bonus（先不加装备加成）
    for k, base_v in INIT.items():
        setattr(player, k, base_v + elixir_bonus.get(k, 0))

    # 重新计算可分配点（考虑转数加成）
    from ..cultivate.reincarnation import ReincarnationService
    pts_per_lvl = ReincarnationService.get_attribute_points_per_level(player.reincarnation_level)
    player.attribute_points = (player.level - 1) * pts_per_lvl

    # 重新计算装备加成（基于新的基础属性）
    if session:
        from sqlalchemy import select
        from ..models.inventory import ItemInstance

        # 获取所有已装备的装备
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

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
            session.add(eq)

    # 保证当前 HP/MP 不超上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    # 生成详细的重置信息
    bonus_info = []

    # 检查是否有装备加成（重新计算后的）
    has_equipment_bonus = False
    if session:
        # 重新获取装备加成信息用于显示
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"])
        )
        equipped_items = (await session.execute(stmt)).scalars().all()
        for eq in equipped_items:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            if any(delta.values()):
                has_equipment_bonus = True
                break

    if has_equipment_bonus:
        bonus_info.append("装备加成已保留")

    if any(elixir_bonus.values()):
        elixir_details = []
        for k, v in elixir_bonus.items():
            if v > 0:
                attr_name = {"max_hp": "体", "max_mp": "智", "attack": "力", "defense": "防", "agility": "敏", "luck": "运"}.get(k, k)
                elixir_details.append(f"{attr_name}+{v}")
        if elixir_details:
            bonus_info.append(f"丹药加成已保留({', '.join(elixir_details)})")

    bonus_msg = f"，{', '.join(bonus_info)}" if bonus_info else ""
    return True, f"🔄 属性已重置，所有点数已退还，可重新分配{bonus_msg}"


@register(ItemEffectType.EXPAND_TERRITORY)
async def _expand_territory(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """扩张公会势力范围 - 这个效果需要特殊处理，因为需要修改Guild对象"""
    # 检查玩家是否加入公会
    if not player.guild_id:
        return False, "⛔ 你尚未加入任何公会，无法使用公会扩张令"

    # 这个效果需要在调用处特殊处理，因为需要访问Guild对象
    # 返回特殊标记，让调用方知道需要特殊处理
    return False, "EXPAND_TERRITORY_SPECIAL_HANDLING"


@register(ItemEffectType.WORLD_BOSS_CHEST)
async def _world_boss_chest(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """世界BOSS宝箱开启效果"""
    import random
    from datetime import datetime

    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    tier = cfg.effect_params.get("tier", "participant")

    # 不同等级宝箱的奖励池
    reward_pools = {
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

    pool = reward_pools.get(tier, reward_pools["participant"])
    rewards = []

    # 处理多个宝箱
    for _ in range(qty):
        # 金币奖励（必得）
        gold_min, gold_max = pool["gold"]
        gold_reward = random.randint(gold_min, gold_max)
        player.gold += gold_reward
        rewards.append(f"💰 {gold_reward:,} 金币")

        # 镶嵌物奖励
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
                    session.add(gem_item)

                    # 获取物品配置以显示名称
                    from ..config import config
                    gem_config = config.items_config["by_id"].get(gem_id)
                    if gem_config:
                        rewards.append(f"💎 {gem_config.get_display_name()} x{gem_qty}")

        # 材料奖励
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
                    session.add(material_item)

                    # 获取物品配置以显示名称
                    from ..config import config
                    material_config = config.items_config["by_id"].get(material_id)
                    if material_config:
                        rewards.append(f"🔮 {material_config.get_display_name()} x{material_qty}")

    if not rewards:
        rewards.append("💰 少量金币")

    # 构建结果消息
    chest_names = {
        "overlord": "深渊霸主宝箱",
        "king": "深渊王者宝箱",
        "warrior": "深渊勇士宝箱",
        "explorer": "深渊探索者宝箱",
        "challenger": "深渊挑战者宝箱",
        "participant": "深渊参与者宝箱"
    }

    chest_name = chest_names.get(tier, "神秘宝箱")
    qty_text = f" x{qty}" if qty > 1 else ""

    result_lines = [
        f"🎁 开启 {chest_name}{qty_text}",
        "✨ 获得奖励：",
        *[f"  {reward}" for reward in rewards]
    ]

    # 添加一些克苏鲁风格的描述
    flavor_texts = [
        "🌀 宝箱中散发出深渊的气息，仿佛在低语着古老的秘密...",
        "👁️ 无数眼球在宝箱内闪烁，见证着你的收获...",
        "🔮 扭曲的能量从宝箱中涌出，化作珍贵的奖励...",
        "⚡ 虚空的力量凝聚成实体，成为你战斗的助力...",
        "🌊 深渊的馈赠降临，带来不可名状的力量..."
    ]

    result_lines.append("")
    result_lines.append(random.choice(flavor_texts))

    return True, "\n".join(result_lines)
