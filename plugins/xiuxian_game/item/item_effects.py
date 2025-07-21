from __future__ import annotations

"""道具效果执行器注册表
所有可使用道具的真正逻辑在此统一处理。
新增效果时，只需编写带 @register 装饰器的协程函数。
"""

from typing import Callable, Awaitable, Dict, Tuple
from ..models.player import Player
from ..models.inventory import ItemEffectType, ItemConfig, ItemInstance, ItemType

# 类型别名
EffectHandler = Callable[[Player, ItemConfig, int, str], Awaitable[Tuple[bool, str]]]

# 注册表
_REGISTRY: Dict[ItemEffectType, EffectHandler] = {}


def register(effect_type: ItemEffectType):
    """装饰器：注册效果处理函数"""
    def decorator(func: EffectHandler):
        _REGISTRY[effect_type] = func
        return func
    return decorator


async def apply_effect(player: Player, item_cfg: ItemConfig, quantity: int = 1, ctx: str = "world") -> Tuple[bool, str]:
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

    返回值
    ------
    (success, message) : Tuple[bool,str]
        success 为 False 时表示效果未生效（例如血量已满），调用方可据此决定是否扣除物品。
    """
    handler = _REGISTRY.get(item_cfg.effect_type)
    if not handler:
        # 未实现效果
        return False, "❓ 该道具效果尚未实现"
    return await handler(player, item_cfg, quantity, ctx)


# ---------------- 具体效果实现 ----------------

@register(ItemEffectType.RESTORE_HP)
async def _restore_hp(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"
    if player.hp >= player.max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"
    player.hp = min(player.max_hp, player.hp + value)
    return True, f"❤️ 恢复 {value} 点生命值 (当前 {player.hp}/{player.max_hp})"


@register(ItemEffectType.RESTORE_MP)
async def _restore_mp(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复理智"
    if player.mp >= player.max_mp:
        return False, "🧐 你的理智值已满，不需要使用此物品"
    player.mp = min(player.max_mp, player.mp + value)
    return True, f"🧠 恢复 {value} 点理智 (当前 {player.mp}/{player.max_mp})"

# 原地复活，与复活指令效果不同
@register(ItemEffectType.REVIVE)
async def _revive(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    if player.hp > 0:
        return False, "🧐 你尚未死亡，无需复活"
    ratio = float(cfg.effect_params.get("rate", 1.0))
    player.hp = max(1, int(player.max_hp * ratio))
    player.mp = max(1, int(player.max_mp * ratio))
    return True, "✨ 你死而复生，继续前进吧！"


@register(ItemEffectType.BUFF)
async def _buff(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    """临时 BUFF：直接把属性累加到玩家本体上。复杂持续时间逻辑以后实现。"""
    attrs = cfg.effect_params or {}
    if not attrs:
        return False, "⛔ 该道具没有任何增益"
    # 简单累加
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
        changed.append(f"{ATTRIBUTE_MAP[k]}+{int(v)*qty}")
    if not changed:
        return False, "⛔ 增益属性无效"
    return True, "✨ 获得增益：" + ", ".join(changed)

@register(ItemEffectType.GAIN_EXP)
async def _gain_exp(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    """直接获得经验值，道具参数 value 指定单份经验量。"""
    value = int(cfg.effect_params.get("value", 0)) * qty
    if value <= 0:
        return False, "⛔ 该丹药配置错误"
    player.exp += value
    return True, f"📚 获得 {value} 点经验"

@register(ItemEffectType.SWEEP_DUNGEON)
async def _sweep_dungeon(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    """扫荡当前诡域，获得经验和材料奖励"""
    import random
    from ..config import config
    from ..models.inventory import ItemInstance
    from ..utils import luck_prob
    from sqlalchemy.ext.asyncio import AsyncSession

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

    # 计算奖励（受玩家理智、生命影响）
    level_range = region_config["level_range"]
    avg_level = (level_range[0] + level_range[1]) // 2

    # 基础经验计算（类似正常刷副本）
    base_exp = random.randint(1, 3) * avg_level * qty
    # 理智影响经验获得（理智越高，扫荡效率越高）
    sanity_bonus = 1 + (player.mp / player.max_mp) * 0.5  # 最多1.5倍
    # 生命影响经验获得（生命越高，扫荡持续时间越长）
    hp_bonus = 1 + (player.hp / player.max_hp) * 0.3  # 最多1.3倍

    final_exp = int(base_exp * sanity_bonus * hp_bonus)
    player.exp += final_exp
    results.append(f"📚 扫荡获得经验: {final_exp}")

    # 材料掉落（基于诡域材料概率和玩家属性）
    materials_gained = []

    # 获取诡域特产材料
    region_materials = region_config.get("materials", [])
    # 获取通用材料（排除鬼怪碎片）
    common_materials = [mat for mat in config.items_config["by_type"]["MATERIAL"]
                       if "fragment" not in mat]

    # 合并材料池
    all_materials = region_materials + common_materials[:5]  # 限制通用材料数量

    if all_materials:
        # 扫荡可能获得多种材料
        material_count = random.randint(1, min(3, len(all_materials))) * qty

        for _ in range(material_count):
            # 优先掉落区域特产
            if region_materials and random.random() < 0.7:
                material_id = random.choice(region_materials)
            else:
                material_id = random.choice(all_materials)

            # 数量受幸运值影响
            base_quantity = random.randint(1, 2)
            if random.random() < luck_prob(player.luck):
                base_quantity *= 2  # 幸运翻倍

            materials_gained.append((material_id, base_quantity))

    # 添加材料到背包
    if materials_gained:
        # 需要获取session来添加物品，这里需要特殊处理
        # 由于这是在effect处理器中，我们返回特殊标记让调用方处理
        material_info = []
        for material_id, quantity in materials_gained:
            item_config = config.items_config["by_id"].get(material_id)
            if item_config:
                material_info.append(f"{item_config.name} ✖️{quantity}")

        if material_info:
            results.append(f"💎 扫荡获得材料: {', '.join(material_info)}")
            # 将材料信息存储到player的临时属性中，供调用方处理
            if not hasattr(player, '_sweep_materials'):
                player._sweep_materials = []
            player._sweep_materials.extend(materials_gained)

    results.append(f"⚡ 消耗咒抗: {qty} (剩余: {player.stamina})")

    return True, "\n".join(results)

# ---------------- 重置属性 ----------------

@register(ItemEffectType.RESET_ATTR)
async def _reset_attr(player: Player, cfg: ItemConfig, qty: int, ctx: str):
    """重置已分配属性点，保留装备加成。仅允许 qty=1。"""
    if qty != 1:
        return False, "⛔ 重启符一次只能使用 1 个"

    from ..config import config as gcfg
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
    bonus = {k: 0 for k in INIT}
    # 从 Session 中预加载玩家装备
    eq_list = player.__dict__.get("item_instances")
    if eq_list:
        for eq in eq_list:
            if getattr(eq, "equipped", False) and eq.config and eq.config.type == ItemType.EQUIPMENT:
                delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
                for k, v in delta.items():
                    if k in bonus:
                        bonus[k] += int(v)

    # 重置属性为基础 + 装备 bonus
    for k, base_v in INIT.items():
        setattr(player, k, base_v + bonus.get(k, 0))

    # 重新计算可分配点
    pts_per_lvl = gcfg.game_config["game"]["points_per_level"]
    player.attribute_points = (player.level - 1) * pts_per_lvl

    # 保证当前 HP/MP 不超上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    return True, "🔄 属性已重置，所有点数已退还，可重新分配"


@register(ItemEffectType.EXPAND_TERRITORY)
async def _expand_territory(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    """扩张公会势力范围 - 这个效果需要特殊处理，因为需要修改Guild对象"""
    # 检查玩家是否加入公会
    if not player.guild_id:
        return False, "⛔ 你尚未加入任何公会，无法使用公会扩张令"

    # 这个效果需要在调用处特殊处理，因为需要访问Guild对象
    # 返回特殊标记，让调用方知道需要特殊处理
    return False, "EXPAND_TERRITORY_SPECIAL_HANDLING"
