from __future__ import annotations

"""道具效果执行器注册表
所有可使用道具的真正逻辑在此统一处理。
新增效果时，只需编写带 @register 装饰器的协程函数。
"""

from typing import Callable, Awaitable, Dict, Tuple
import time
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from ..models.player import Player
from ..models.inventory import ItemEffectType, ItemConfig, ItemInstance, ItemType
# 从装备服务模块导入（已解耦，不再依赖命令层）
from .equipment_service import recalc_equipment_attributes
from ..models.elixir_usage import ElixirUsageLog
from datetime import date, datetime, timedelta

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的EquipmentService，False使用旧版本
# 设置为True使用新版DI架构的复杂效果Service（SWEEP_DUNGEON、RESET_ATTR、WORLD_BOSS_CHEST），False使用旧版本
# =====================================================

# 类型别名
EffectHandler = Callable[[Player, ItemConfig, int, object, object], Awaitable[Tuple[bool, str]]]

# 注册表
_REGISTRY: Dict[ItemEffectType, EffectHandler] = {}


def register(effect_type: ItemEffectType):
    """装饰器：注册效果处理函数"""
    def decorator(func: EffectHandler):
        _REGISTRY[effect_type] = func
        return func
    return decorator



async def apply_effect(player: Player, item_cfg: ItemConfig, quantity: int = 1, ctx: object = "world", session=None) -> Tuple[bool, str]:
    """根据 item_cfg 调用对应处理器

    参数
    ------
    player : Player
        目标玩家实例（已绑定到 SQLAlchemy Session）
    item_cfg : ItemConfig
        物品配置
    quantity : int
        使用数量
    ctx : object
        使用场景或额外参数。常见示例："world"、"battle"，也可以传递包含额外数据的字典
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

    effective_max_hp = player.max_hp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_hp = effective_attrs.get("max_hp", effective_max_hp)

    if player.hp >= effective_max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"

    player.hp = min(effective_max_hp, player.hp + value)
    return True, f"❤️ 恢复 {value} 点生命值 (当前 {player.hp}/{effective_max_hp})"


@register(ItemEffectType.RESTORE_MP)
async def _restore_mp(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    value = int(cfg.effect_params.get("value", 0)) * qty
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复理智"

    effective_max_mp = player.max_mp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_mp = effective_attrs.get("max_mp", effective_max_mp)

    if player.mp >= effective_max_mp:
        return False, "🧐 你的理智值已满，不需要使用此物品"

    player.mp = min(effective_max_mp, player.mp + value)
    return True, f"🧠 恢复 {value} 点理智 (当前 {player.mp}/{effective_max_mp})"


@register(ItemEffectType.RESTORE_HP_PERCENT)
async def _restore_hp_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复生命"

    effective_max_hp = player.max_hp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_hp = effective_attrs.get("max_hp", effective_max_hp)

    if player.hp >= effective_max_hp:
        return False, "🧐 你的生命值已满，不需要使用此物品"

    # 计算恢复量（效果不减弱）
    percent = float(cfg.effect_params.get("percent", 0)) * qty
    value = int(effective_max_hp * percent)
    player.hp = min(effective_max_hp, player.hp + value)

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    percent_display = int(percent * 100)
    return True, f"❤️ 恢复 {percent_display}% 生命值 ({value}点) (当前 {player.hp}/{effective_max_hp})"


@register(ItemEffectType.RESTORE_MP_PERCENT)
async def _restore_mp_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    if player.hp <= 0:
        return False, "🧐 你已经死亡，无法恢复理智"

    effective_max_mp = player.max_mp
    if session:
        effective_attrs = await player.get_effective_attributes(session)
        effective_max_mp = effective_attrs.get("max_mp", effective_max_mp)

    if player.mp >= effective_max_mp:
        return False, "🧐 你的理智值已满，不需要使用此物品"

    # 计算恢复量（效果不减弱）
    percent = float(cfg.effect_params.get("percent", 0)) * qty
    value = int(effective_max_mp * percent)
    player.mp = min(effective_max_mp, player.mp + value)

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    percent_display = int(percent * 100)
    return True, f"🧠 恢复 {percent_display}% 理智值 ({value}点) (当前 {player.mp}/{effective_max_mp})"

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

    # 属性发生变化后重新计算装备加成，确保百分比加成基于最新基础值
    if session:
        await _recalculate_equipment_bonus(session, player)

    # 使用新上限修正当前血量/理智值
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    if not changed:
        return False, "⛔ 增益属性无效"
    return True, f"✨ 获得增益：{', '.join(changed)}"


@register(ItemEffectType.TEMPORARY_BUFF)
async def _temporary_buff(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """临时属性加成丹药：创建有时间限制的临时buff"""
    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    # 获取丹药配置
    effect_params = cfg.effect_params or {}
    if not effect_params:
        return False, "⛔ 该丹药没有任何增益效果"

    # 获取持续时间（分钟）
    duration_minutes = effect_params.get("duration_minutes", 30)  # 默认30分钟
    buff_name = effect_params.get("buff_name", cfg.name)

    # 提取属性加成
    attribute_bonuses = {}
    for key, value in effect_params.items():
        if key not in ["duration_minutes", "buff_name"] and hasattr(player, key):
            attribute_bonuses[key] = int(value) * qty

    if not attribute_bonuses:
        return False, "⛔ 该丹药没有有效的属性加成"

    # 创建临时buff
    from ..models.temporary_buff import TemporaryBuff

    buff_id = f"{cfg.item_id}_buff"
    buff = await TemporaryBuff.create_buff(
        session=session,
        player_id=player.id,
        buff_id=buff_id,
        buff_name=buff_name,
        attribute_bonuses=attribute_bonuses,
        duration_minutes=duration_minutes,
        source_item_id=cfg.item_id,
        source_description=f"使用{cfg.name}获得"
    )

    # 格式化属性加成显示
    ATTRIBUTE_MAP = {
        "max_hp": "体",
        "max_mp": "智",
        "attack": "力",
        "defense": "防",
        "agility": "敏",
        "luck": "运",
        "critical_rate": "暴击率",
        "critical_power": "暴击力",
        "combo_rate": "连击率",
        "counter_rate": "反击率",
        "dodge_rate": "闪避率",
        "accuracy_rate": "命中率",
        "skill_crit_rate": "灵爆率",
        "penetration_rate": "穿透率",
        "anti_crit_rate": "抗暴率"
    }

    bonus_strs = []
    for attr, value in attribute_bonuses.items():
        attr_name = ATTRIBUTE_MAP.get(attr, attr)
        if value > 0:
            bonus_strs.append(f"{attr_name}+{value}")
        elif value < 0:
            bonus_strs.append(f"{attr_name}{value}")

    # 格式化时间显示
    if duration_minutes >= 60:
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        time_str = f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
    else:
        time_str = f"{duration_minutes}分钟"

    bonus_text = ", ".join(bonus_strs)

    # 临时buff不需要记录到ElixirUsageLog（该表仅用于永久BUFF类型）
    # 临时buff通过TemporaryBuff表管理，会自动过期

    return True, f"✨ 获得临时增益：{bonus_text}\n⏰ 持续时间：{time_str}"


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


@register(ItemEffectType.GAIN_EXP_SCALED)
async def _gain_exp_scaled(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """按等级伸缩的经验丹：base_value + level * scale_factor"""
    base_value = int(cfg.effect_params.get("base_value", 0))
    scale_factor = float(cfg.effect_params.get("scale_factor", 0))

    if base_value <= 0:
        return False, "⛔ 该丹药配置错误"

    # 计算伸缩经验值
    level_bonus = int(player.level * scale_factor)
    actual_value = (base_value + level_bonus) * qty
    player.exp += actual_value

    # 更新使用记录
    if session:
        await update_elixir_usage(session, player, cfg, qty)

    return True, f"📚 获得 {actual_value} 点经验（基础{base_value}+等级加成{level_bonus}）"


@register(ItemEffectType.BUFF_PERCENT)
async def _buff_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """永久百分比属性加成：按当前基础属性的百分比增加"""
    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    attrs = cfg.effect_params or {}
    if not attrs:
        return False, "⛔ 该道具没有任何增益"

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
        if k.endswith("_pct") and hasattr(player, k.replace("_pct", "")):
            attr_name = k.replace("_pct", "")
            old_value = getattr(player, attr_name)
            # 计算百分比增量
            percent = float(v) / 100.0
            increase = int(old_value * percent * qty)
            if increase == 0 and percent > 0:
                increase = 1  # 至少增加1点
            new_value = old_value + increase
            setattr(player, attr_name, new_value)
            changed.append(f"{ATTRIBUTE_MAP.get(attr_name, attr_name)}+{increase}({int(float(v)*qty)}%)")

    # 属性发生变化后重新计算装备加成
    await _recalculate_equipment_bonus(session, player)

    # 使用新上限修正当前血量/理智值
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    # 更新使用记录
    await update_elixir_usage(session, player, cfg, qty)

    if not changed:
        return False, "⛔ 增益属性无效"
    return True, f"✨ 获得永久增益：{', '.join(changed)}"


@register(ItemEffectType.TEMPORARY_BUFF_PERCENT)
async def _temporary_buff_percent(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """临时百分比属性加成：按当前基础属性的百分比创建临时buff"""
    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    effect_params = cfg.effect_params or {}
    if not effect_params:
        return False, "⛔ 该丹药没有任何增益效果"

    duration_minutes = effect_params.get("duration_minutes", 30)
    buff_name = effect_params.get("buff_name", cfg.name)

    # 计算实际属性加成值
    attribute_bonuses = {}
    bonus_display = []

    ATTRIBUTE_MAP = {
        "max_hp": "体", "max_mp": "智", "attack": "力",
        "defense": "防", "agility": "敏", "luck": "运",
        "critical_rate": "暴击率", "critical_power": "暴击力",
        "combo_rate": "连击率", "counter_rate": "反击率",
        "dodge_rate": "闪避率", "accuracy_rate": "命中率",
    }

    for key, value in effect_params.items():
        if key in ["duration_minutes", "buff_name"]:
            continue

        if key.endswith("_pct"):
            attr_name = key.replace("_pct", "")
            if hasattr(player, attr_name):
                base_value = getattr(player, attr_name)
                percent = float(value) / 100.0
                increase = int(base_value * percent * qty)
                if increase == 0 and percent > 0:
                    increase = 1
                attribute_bonuses[attr_name] = increase
                bonus_display.append(f"{ATTRIBUTE_MAP.get(attr_name, attr_name)}+{increase}({int(float(value)*qty)}%)")

    if not attribute_bonuses:
        return False, "⛔ 该丹药没有有效的属性加成"

    # 创建临时buff
    from ..models.temporary_buff import TemporaryBuff

    buff_id = f"{cfg.item_id}_buff"
    await TemporaryBuff.create_buff(
        session=session,
        player_id=player.id,
        buff_id=buff_id,
        buff_name=buff_name,
        attribute_bonuses=attribute_bonuses,
        duration_minutes=duration_minutes,
        source_item_id=cfg.item_id,
        source_description=f"使用{cfg.name}获得"
    )

    # 格式化时间显示
    if duration_minutes >= 60:
        hours = duration_minutes // 60
        minutes = duration_minutes % 60
        time_str = f"{hours}小时{minutes}分钟" if minutes > 0 else f"{hours}小时"
    else:
        time_str = f"{duration_minutes}分钟"

    # 临时buff不需要记录到ElixirUsageLog（该表仅用于永久BUFF类型）
    # 临时buff通过TemporaryBuff表管理，会自动过期

    return True, f"✨ 获得临时增益：{', '.join(bonus_display)}\n⏰ 持续时间：{time_str}"


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


@register(ItemEffectType.REFORGE_ATTR)
async def _reforge_attr(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """洗髓丹药：将指定属性的百分比转换为可分配属性点

    配置格式：
    effect_params:
        source_attr: "attack"  # 源属性（attack/defense/agility/max_hp/max_mp）
        percent: 3  # 转换百分比（3表示3%）
        attr_name: "力量"  # 属性显示名称
    """
    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    source_attr = cfg.effect_params.get("source_attr")
    percent = float(cfg.effect_params.get("percent", 0))
    attr_name = cfg.effect_params.get("attr_name", source_attr)

    if not source_attr or percent <= 0:
        return False, "⛔ 该丹药配置错误"

    if not hasattr(player, source_attr):
        return False, f"⛔ 无效的属性：{source_attr}"

    # 获取当前属性值
    current_value = getattr(player, source_attr)
    if current_value <= 0:
        return False, f"⛔ {attr_name}不足，无法洗髓"

    # 计算去除装备加成后的基础属性值
    base_value = Decimal(str(current_value))
    from ..config import config as gcfg
    attributes_base = (
        gcfg.game_config.get("cultivate", {}).get("attributes_base", {})
        if hasattr(gcfg, "game_config")
        else {}
    )

    if session:
        from sqlalchemy import select

        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(gcfg.items_config["by_type"]["EQUIPMENT"]),
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

        for eq in equipped_items:
            delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
            bonus = delta.get(source_attr)
            if isinstance(bonus, (int, float, Decimal)):
                base_value -= Decimal(str(bonus))

    base_value = base_value.to_integral_value(rounding=ROUND_HALF_UP)
    base_value_int = int(base_value)

    if base_value_int <= 0:
        return False, f"⛔ {attr_name}基础值不足，无法洗髓"

    # 计算转换量（每次使用转换一次，仅针对基础属性值）
    percent_ratio = Decimal(str(percent)) / Decimal("100")
    convert_amount_decimal = Decimal(base_value_int) * percent_ratio * Decimal(qty)
    convert_amount = int(convert_amount_decimal.to_integral_value(rounding=ROUND_DOWN))

    # 检查是否会导致属性过低
    min_value = 1
    if source_attr in ["max_hp", "max_mp"]:
        min_value = 10  # 生命和理智至少保留10点

    max_convertible = base_value_int - min_value
    if max_convertible <= 0:
        return False, f"⛔ {attr_name}过低，无法继续洗髓（至少需保留{min_value}点）"

    ratio_raw = attributes_base.get(source_attr, 1)
    try:
        convert_ratio = int(ratio_raw)
    except (TypeError, ValueError):
        convert_ratio = 1
    if convert_ratio <= 0:
        convert_ratio = 1

    if convert_ratio > 1:
        max_points = max_convertible // convert_ratio
        if max_points <= 0:
            return False, f"⛔ {attr_name}过低，无法继续洗髓（至少需保留{min_value}点）"

        if convert_amount <= 0:
            convert_amount = convert_ratio
        points_gain = convert_amount // convert_ratio
        if points_gain <= 0:
            points_gain = 1
        if points_gain > max_points:
            points_gain = max_points
        convert_amount = points_gain * convert_ratio
    else:
        if convert_amount <= 0:
            convert_amount = 1  # 至少转换1点
        if convert_amount > max_convertible:
            convert_amount = max_convertible
        points_gain = convert_amount

    if convert_amount <= 0 or points_gain <= 0:
        return False, f"⛔ {attr_name}过低，无法继续洗髓（至少需保留{min_value}点）"

    if base_value_int - convert_amount < min_value:
        return False, f"⛔ {attr_name}过低，无法继续洗髓（至少需保留{min_value}点）"

    # 扣除源属性
    setattr(player, source_attr, current_value - convert_amount)

    # 增加可分配属性点
    player.attribute_points += points_gain

    gain_display = points_gain

    # 如果是生命或理智上限，需要调整当前值
    if source_attr == "max_hp" and player.hp > player.max_hp:
        player.hp = player.max_hp
    elif source_attr == "max_mp" and player.mp > player.max_mp:
        player.mp = player.max_mp

    # 重新计算装备加成
    await _recalculate_equipment_bonus(session, player)

    # 更新使用记录
    await update_elixir_usage(session, player, cfg, qty)

    return True, (
        f"🔄 洗髓成功！\n"
        f"━━━━━━━━━━━━━\n"
        f"转换：{attr_name} -{convert_amount} ({int(percent * qty)}%)\n"
        f"获得：可分配属性点 +{gain_display}\n"
        f"━━━━━━━━━━━━━\n"
        f"当前{attr_name}：{getattr(player, source_attr)}\n"
        f"可分配属性点：{player.attribute_points}\n"
        f"💡 使用【加点】指令分配属性点"
    )

@register(ItemEffectType.SWEEP_DUNGEON)
async def _sweep_dungeon(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """扫荡当前诡域，获得经验和材料奖励"""
    # 新版本：使用DI架构的Service
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from ..infrastructure.repositories.item_repository import ItemRepository
    from .sweep_dungeon_service import SweepDungeonService
    from .equipment_service_new import EquipmentService

    sweep_service = SweepDungeonService(
        player_repo=PlayerRepository(session),
        item_repo=ItemRepository(session),
        equipment_service=EquipmentService(
            item_repo=ItemRepository(session),
            player_repo=PlayerRepository(session)
        )
    )
    result = await sweep_service.execute(player, cfg, qty, str(ctx))
    return result.success, result.message
# ---------------- 重置属性 ----------------

@register(ItemEffectType.RESET_ATTR)
async def _reset_attr(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None):
    """重置已分配属性点，保留装备加成、丹药加成和VIP装备永久加成"""
    # 新版本：使用DI架构的Service
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from ..infrastructure.repositories.item_repository import ItemRepository
    from ..infrastructure.repositories.elixir_usage_repository import ElixirUsageRepository
    from ..infrastructure.repositories.vip_equipment_bonus_repository import VIPEquipmentBonusRepository
    from .reset_attr_service import ResetAttrService

    reset_service = ResetAttrService(
        player_repo=PlayerRepository(session),
        item_repo=ItemRepository(session),
        elixir_usage_repo=ElixirUsageRepository(session),
        vip_equipment_bonus_repo=VIPEquipmentBonusRepository(session)
    )
    result = await reset_service.execute(player, cfg, qty, str(ctx))
    return result.success, result.message
async def _recalculate_equipment_bonus(session, player: Player):
    """重新计算装备持久化加成，确保百分比加成与最新基础属性同步"""
    if not session:
        return

    # 新版本: 使用DI架构的EquipmentService
    from ..infrastructure.repositories.item_repository import ItemRepository
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from .equipment_service_new import EquipmentService

    equipment_service = EquipmentService(
        item_repo=ItemRepository(session),
        player_repo=PlayerRepository(session)
    )
    await equipment_service.recalc_equipment_attributes(player)
@register(ItemEffectType.EXPAND_TERRITORY)
async def _expand_territory(player: Player, cfg: ItemConfig, qty: int, ctx: object, session=None) -> Tuple[bool, str]:
    """扩张公会势力范围 - 这个效果需要特殊处理，因为需要修改Guild对象"""
    # 检查玩家是否加入公会
    if not player.guild_id:
        return False, "⛔ 你尚未加入任何公会，无法使用公会扩张令"

    # 这个效果需要在调用处特殊处理，因为需要访问Guild对象
    # 返回特殊标记，让调用方知道需要特殊处理
    return False, "EXPAND_TERRITORY_SPECIAL_HANDLING"


@register(ItemEffectType.WORLD_BOSS_CHEST)
async def _world_boss_chest(player: Player, cfg: ItemConfig, qty: int, ctx: object, session=None) -> Tuple[bool, str]:
    """世界BOSS宝箱开启效果"""
    # 新版本：使用DI架构的Service
    from ..infrastructure.repositories.player_repository import PlayerRepository
    from ..infrastructure.repositories.item_repository import ItemRepository
    from .world_boss_chest_service import WorldBossChestService

    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    chest_service = WorldBossChestService(
        player_repo=PlayerRepository(session),
        item_repo=ItemRepository(session)
    )
    result = await chest_service.execute(player, cfg, qty, str(ctx))
    return result.success, result.message
@register(ItemEffectType.DIVINE_PUNISHMENT)
async def _divine_punishment(player: Player, cfg: ItemConfig, qty: int, ctx: object, session=None) -> Tuple[bool, str]:
    """天罚符：强制击杀指定UID的玩家"""

    if not session:
        return False, "⛔ 系统错误：缺少数据库会话"

    target_uid = None
    if isinstance(ctx, dict):
        target_uid = ctx.get("target_uid")

    try:
        target_uid = int(target_uid)
    except (TypeError, ValueError):
        return False, "⛔ 请提供有效的目标UID，例如：使用 天罚符 12345"

    from sqlalchemy import select

    target_stmt = select(Player).where(Player.uid == target_uid)
    target_result = await session.execute(target_stmt)
    target = target_result.scalars().first()

    if not target:
        return False, f"⛔ 未找到UID为 {target_uid} 的玩家"

    if target.id == player.id:
        return False, "⛔ 你不能对自己使用天罚符"

    if target.hp <= 0:
        return False, "⛔ 目标已处于濒死状态，无需再次击杀"

    # 直接将目标击杀
    target.hp = 0
    target.mp = 0

    from ..world import attack_command as attack_module

    now_ts = time.time()
    last_ts = attack_module._last_pvp_drop_time.get(target.id, 0)
    if now_ts - last_ts < attack_module.DROP_PROTECTION_SECONDS:
        drop_message = "🛡️ 掉落保护生效：短时间内不再掉落物品"
    else:
        drop_result = await attack_module.handle_wilderness_drops(session, target, player)
        attack_module._last_pvp_drop_time[target.id] = now_ts
        drop_message = drop_result or f"💀 {target.nickname} 没有掉落任何物品"

    session.add(target)

    result_lines = [
        f"⚡ 天罚降临！{target.nickname}[UID:{target.uid}] 当场毙命。",
        drop_message,
    ]

    return True, "\n".join(line for line in result_lines if line)


# ============== 临时buff管理功能 ==============

async def get_player_buff_status(session, player: Player) -> str:
    """获取玩家的临时buff状态信息"""
    from ..models.temporary_buff import TemporaryBuff

    # 清理过期buff
    await TemporaryBuff.cleanup_expired_buffs(session, player.id)

    # 获取激活的buff
    active_buffs = await TemporaryBuff.get_active_buffs(session, player.id)

    if not active_buffs:
        return "🌟 当前没有任何临时增益效果"

    lines = [
        "✨ 当前临时增益状态",
        "━━━━━━━━━━━━━"
    ]

    for buff in active_buffs:
        lines.append(buff.format_display())

    # 显示总属性加成
    total_bonuses = await TemporaryBuff.get_total_attribute_bonuses(session, player.id)
    if total_bonuses:
        lines.append("")
        lines.append("📊 总属性加成：")

        attr_map = {
            "max_hp": "体",
            "max_mp": "智",
            "attack": "力",
            "defense": "防",
            "agility": "敏",
            "luck": "运",
            "critical_rate": "暴击率",
            "critical_power": "暴击力",
            "combo_rate": "连击率",
            "counter_rate": "反击率",
            "dodge_rate": "闪避率",
            "accuracy_rate": "命中率",
            "skill_crit_rate": "灵爆率",
            "penetration_rate": "穿透率",
            "anti_crit_rate": "抗暴率"
        }

        bonus_strs = []
        for attr, value in total_bonuses.items():
            attr_name = attr_map.get(attr, attr)
            if value > 0:
                bonus_strs.append(f"{attr_name}+{value}")
            elif value < 0:
                bonus_strs.append(f"{attr_name}{value}")

        if bonus_strs:
            lines.append(f"  {', '.join(bonus_strs)}")

    lines.append("")
    lines.append("💡 提示：临时增益会在时间到期后自动消失")

    return "\n".join(lines)


@register(ItemEffectType.MONTHLY_CARD_BOX)
async def _monthly_card_box(player: Player, cfg: ItemConfig, qty: int, ctx: str, session=None) -> Tuple[bool, str]:
    """月卡宝箱：随机获得一种材料10-50个"""
    import random
    from ..config import config
    from ..models.inventory import ItemInstance

    # 获取所有材料类型的物品
    material_items = config.items_config["by_type"].get("MATERIAL", [])
    if not material_items:
        return False, "⛔ 系统错误：未找到材料配置"

    results = []

    for _ in range(qty):
        # 随机选择一种材料
        material_id = random.choice(material_items)
        material_config = config.items_config["by_id"].get(material_id)
        if not material_config:
            continue

        # 随机数量10-50个
        quantity = random.randint(10, 50)

        # 添加材料到背包
        try:
            await ItemInstance.add_item(session, player.id, material_id, quantity)
            # 使用get_display_name()方法获取带稀有度emoji的材料名称
            results.append(f"💎 {material_config.get_display_name()} ×{quantity}")
        except ValueError as e:
            results.append(f"⚠️ {material_config.get_display_name()} 添加失败：{e}")

    if not results:
        return False, "⛔ 月卡宝箱开启失败"

    result_msg = f"✨ 月卡宝箱开启成功！\n━━━━━━━━━━━━━\n" + "\n".join(results)
    return True, result_msg


@register(ItemEffectType.SANTA_TELEPORT)
async def _santa_teleport(player: Player, cfg: ItemConfig, qty: int, ctx: dict, session=None) -> Tuple[bool, str]:
    """圣诞老人代驾券：瞬移到任意位置"""
    if not isinstance(ctx, dict) or "target" not in ctx:
        return False, "⛔ 参数错误，请提供目标位置"

    target_args = ctx["target"]

    # 判断是传送坐标还是传送诡域
    # 格式1：使用 圣诞老人代驾券 x y (传送坐标)
    # 格式2：使用 圣诞老人代驾券 N层诡域 (传送诡域)

    # 检查是否是诡域传送
    if len(target_args) >= 1 and "层诡域" in target_args[-1]:
        # 诡域传送
        target_str = target_args[-1]
        try:
            level_str = target_str.replace("层诡域", "")
            if level_str.startswith("第"):
                level_str = level_str[1:]
            dungeon_level = int(level_str)
        except ValueError:
            return False, "⛔ 诡域层级格式错误，请使用：N层诡域 或 第N层诡域"

        # 验证层级范围
        if dungeon_level <= 0:
            return False, "⛔ 诡域层级必须大于0"

        # 检查是否已解锁该层级
        if not player.can_enter_dungeon_level(dungeon_level):
            max_level = player.max_dungeon_level or 0
            return False, (
                f"⛔ 你还未解锁第{dungeon_level}重诡域！\n"
                f"━━━━━━━━━━━━━\n"
                f"📊 当前最深探索：第{max_level}重诡域\n"
                f"💡 需要逐重击败诡异解锁更深的诡域"
            )

        # 执行传送
        from ..world.dungeon_battle import get_or_create_tile
        player.enter_dungeon(dungeon_level)

        # 获取新位置描述
        tile = await get_or_create_tile(session, f"{dungeon_level}层诡域", player.dungeon_x, player.dungeon_y)
        tile_desc = await _get_tile_description_from_tile(session, player, tile)

        session.add(player)
        await session.commit()

        msg_lines = [
            "🎅✨ 圣诞裂隙缓缓展开...",
            "━━━━━━━━━━━━━",
            f"❄️ 你穿过了扭曲的时空，抵达了第{dungeon_level}重诡域",
            f"📍 当前位置：({player.dungeon_x}, {player.dungeon_y})",
            "━━━━━━━━━━━━━",
            tile_desc,
            "🎄 圣诞快乐！愿你心想事成！"
        ]

        return True, "\n".join(msg_lines)

    else:
        # 坐标传送（现实世界）
        if len(target_args) < 2:
            return False, "⛔ 请提供完整坐标，例如：使用 圣诞老人代驾券 100 -200"

        try:
            target_x = int(target_args[0])
            target_y = int(target_args[1])
        except ValueError:
            return False, "⛔ 坐标必须是整数"

        # 坐标范围检查（可根据需要调整）
        if not (-1000 <= target_x <= 1000 and -1000 <= target_y <= 1000):
            return False, "⛔ 目标坐标超出范围（-1000到1000）"

        # 退出诡域（如果在诡域中）
        was_in_dungeon = player.is_in_dungeon()

        # 推进导航进度
        from ..models.navigation_task import NavigationTask
        from ..world.navigation import _update_nav_position
        nav_task = await session.get(NavigationTask, player.id)
        if nav_task:
            reached = await _update_nav_position(player, nav_task, session)
            if reached:
                await session.delete(nav_task)

        player.exit_dungeon()
        player.x = target_x
        player.y = target_y

        session.add(player)
        await session.commit()

        msg_lines = [
            "🎅✨ 圣诞裂隙缓缓展开...",
            "━━━━━━━━━━━━━",
            f"❄️ 你穿过了扭曲的时空，抵达了现实世界坐标 ({target_x}, {target_y})",
        ]

        if was_in_dungeon:
            msg_lines.append("🌍 你已从诡域穿越回表世界")

        msg_lines.extend([
            "━━━━━━━━━━━━━",
            "🎄 圣诞快乐！愿你心想事成！"
        ])

        return True, "\n".join(msg_lines)


async def _get_tile_description_from_tile(session, player: Player, tile) -> str:
    """根据tile对象生成描述（辅助函数）"""
    from ..world.teleport import get_tile_description
    region = f"{player.dungeon_level}层诡域" if player.is_in_dungeon() else player.region
    return await get_tile_description(session, player, region, player.dungeon_x if player.is_in_dungeon() else player.x, player.dungeon_y if player.is_in_dungeon() else player.y)
