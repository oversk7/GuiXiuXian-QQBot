from __future__ import annotations

"""道具效果执行器注册表
所有可使用道具的真正逻辑在此统一处理。
新增效果时，只需编写带 @register 装饰器的协程函数。
"""

from typing import Callable, Awaitable, Dict, Tuple
from ..models.player import Player
from ..models.inventory import ItemEffectType, ItemConfig
from ..models.equipment import EquipmentInstance

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
    return True, "✨ 你死而复生，继续前进吧！"


@register(ItemEffectType.BUFF)
async def _buff(player: Player, cfg: ItemConfig, qty: int, ctx: str) -> Tuple[bool, str]:
    """临时 BUFF：直接把属性累加到玩家本体上。复杂持续时间逻辑以后实现。"""
    attrs = cfg.effect_params or {}
    if not attrs:
        return False, "⛔ 该道具没有任何增益"
    # 简单累加
    changed = []
    for k, v in attrs.items():
        if not hasattr(player, k):
            continue
        old = getattr(player, k)
        new_val = old + int(v) * qty
        setattr(player, k, new_val)
        changed.append(f"{k}+{int(v)*qty}")
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
    for eq in getattr(player, "equip_instances", []):
        if eq.equipped:
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
