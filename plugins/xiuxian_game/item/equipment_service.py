"""
装备业务逻辑服务

提供装备相关的核心业务逻辑：
1. 重新计算装备属性加成
2. 处理 mp_from_hp 特效
3. 处理 hp_from_attack 特效（诡面骰）
4. 装备相关常量定义

注：此模块从 equipment_commands.py 中提取，解决模块耦合问题
"""

from sqlalchemy import select
from ..models import Player, ItemInstance
from ..config import config


# 获取所有装备物品ID
EQUIP_ITEM_IDS = config.items_config["by_type"]["EQUIPMENT"]


def _apply_mp_from_hp_effects(player: Player, equipped_items: list[ItemInstance], session) -> None:
    """将拥有 mp_from_hp 特效的装备的加成重新应用到玩家身上。"""
    if not equipped_items:
        return

    mp_from_hp_effects: list[tuple[ItemInstance, float, int, bool]] = []
    total_pct = 0.0
    total_flat = 0

    for eq in equipped_items:
        if not getattr(eq, "equipped", False):
            continue
        cfg = eq.config if hasattr(eq, "config") else None
        if not cfg or not getattr(cfg, "special_effects", None):
            continue

        for eff in cfg.special_effects:
            if eff.get("effect") != "mp_from_hp":
                continue
            is_pct = bool(eff.get("is_percentage", True))
            if is_pct:
                val_pct = float(eff.get("value", 0) or 0)
                if val_pct > 0:
                    total_pct += val_pct
                    mp_from_hp_effects.append((eq, val_pct, 0, True))
            else:
                val_flat = int(eff.get("value", 0) or 0)
                if val_flat > 0:
                    total_flat += val_flat
                    mp_from_hp_effects.append((eq, 0.0, val_flat, False))

    if not mp_from_hp_effects:
        return

    # 使用穿装备后的总生命值来计算MP（符合客户需求）
    # 之前的逻辑会减去装备自身的HP，导致计算基数错误
    current_hp_after_all = int(getattr(player, "max_hp", 0) or 0)
    base_for_convert = max(1, current_hp_after_all)  # 直接使用总HP，不减去装备HP
    bonus_from_pct = int(base_for_convert * total_pct / 100.0) if total_pct > 0 else 0
    total_bonus_mp = bonus_from_pct + int(total_flat)
    if total_bonus_mp <= 0:
        return

    remaining = total_bonus_mp
    for idx, (eq, pct, flat, is_pct) in enumerate(mp_from_hp_effects):
        part = 0
        if is_pct and pct > 0:
            part = int(base_for_convert * pct / 100.0)
        elif (not is_pct) and flat > 0:
            part = int(flat)

        if idx == len(mp_from_hp_effects) - 1:
            part = remaining
        else:
            part = min(part, remaining)

        if part <= 0:
            continue

        remaining = max(0, remaining - part)
        player.max_mp = int(getattr(player, "max_mp", 0)) + part

        extra = eq.extra_attrs or {}
        persist = dict(extra.get("_persist_bonus", {}))
        persist["max_mp"] = int(persist.get("max_mp", 0)) + part
        extra["_persist_bonus"] = persist
        eq.extra_attrs = extra
        session.add(eq)


def _apply_hp_from_attack_effects(player: Player, equipped_items: list[ItemInstance], session) -> None:
    """将拥有 hp_from_attack 特效的装备的加成持久写入玩家属性。

    以穿装备后的总攻击力为基数，按百分比计算 max_hp 加成，
    写入 player.max_hp 并记录到 _persist_bonus["max_hp"]。
    """
    if not equipped_items:
        return

    hp_from_attack_effects: list[tuple[ItemInstance, float]] = []
    total_pct = 0.0

    for eq in equipped_items:
        if not getattr(eq, "equipped", False):
            continue
        cfg = eq.config if hasattr(eq, "config") else None
        if not cfg or not getattr(cfg, "special_effects", None):
            continue

        for eff in cfg.special_effects:
            if eff.get("effect") != "hp_from_attack":
                continue
            if bool(eff.get("is_percentage", True)):
                val_pct = float(eff.get("value", 0) or 0)
                if val_pct > 0:
                    total_pct += val_pct
                    hp_from_attack_effects.append((eq, val_pct))

    if not hp_from_attack_effects:
        return

    # 以穿装备后的总攻击力为基数（此时 player.attack 已含诡面骰自身加成）
    current_attack = int(getattr(player, "attack", 0) or 0)
    base_for_convert = max(1, current_attack)
    total_bonus_hp = int(base_for_convert * total_pct / 100.0)
    if total_bonus_hp <= 0:
        return

    remaining = total_bonus_hp
    for idx, (eq, pct) in enumerate(hp_from_attack_effects):
        part = int(base_for_convert * pct / 100.0)
        if idx == len(hp_from_attack_effects) - 1:
            part = remaining
        else:
            part = min(part, remaining)

        if part <= 0:
            continue

        remaining = max(0, remaining - part)
        player.max_hp = int(getattr(player, "max_hp", 0)) + part

        extra = eq.extra_attrs or {}
        persist = dict(extra.get("_persist_bonus", {}))
        persist["max_hp"] = int(persist.get("max_hp", 0)) + part
        extra["_persist_bonus"] = persist
        eq.extra_attrs = extra
        session.add(eq)


async def recalc_equipment_attributes(
    session,
    player: Player,
    equipped_items: list[ItemInstance] | None = None,
) -> None:
    """重新计算玩家当前装备提供的属性加成（包含 mp_from_hp 特效）。"""

    if equipped_items is None:
        stmt = select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
            ItemInstance.item_id.in_(EQUIP_ITEM_IDS),
        )
        equipped_items = (await session.execute(stmt)).scalars().all()

    if not equipped_items:
        if player.hp > player.max_hp:
            player.hp = player.max_hp
        if player.mp > player.max_mp:
            player.mp = player.max_mp
        session.add(player)
        return

    # 1. 先移除所有已记录的装备加成
    # 注意：只处理equipped=True的装备，跳过已卸下的（equipped=False）
    # 因为"卸下装备"命令会在调用recalc前手动移除属性
    for eq in equipped_items:
        if not getattr(eq, "equipped", False):
            continue
        delta = (eq.extra_attrs or {}).get("_persist_bonus", {})
        for k, v in delta.items():
            current_value = getattr(player, k, 0)
            setattr(player, k, max(0, current_value - int(v or 0)))

        if "_persist_bonus" in (eq.extra_attrs or {}):
            extra_new = {k: v for k, v in eq.extra_attrs.items() if k != "_persist_bonus"}
            eq.extra_attrs = extra_new

        eq.equipped = False

    # 2. 基于当前基础属性重新应用装备加成
    # 注意：此时player属性已经是真实的无装备基础属性
    base_attrs = {
        "attack": player.attack,
        "defense": player.defense,
        "agility": player.agility,
        "luck": player.luck,
        "max_hp": player.max_hp,
        "max_mp": player.max_mp,
    }

    # 3. 重新应用装备加成
    for eq in equipped_items:
        eq.equipped = True

        attrs_temp = base_attrs.copy()
        eq.apply_attr_bonus(attrs_temp, base_attrs)
        new_delta = {}
        for k in attrs_temp:
            if k in base_attrs:
                if attrs_temp[k] != base_attrs[k]:
                    new_delta[k] = attrs_temp[k] - base_attrs[k]
            else:
                if attrs_temp[k] != 0:
                    new_delta[k] = attrs_temp[k]

        for k, v in new_delta.items():
            setattr(player, k, getattr(player, k) + v)

        extra = eq.extra_attrs or {}
        extra["_persist_bonus"] = new_delta
        eq.extra_attrs = extra
        session.add(eq)

    # 4. 再处理 mp_from_hp 类全局被动（只处理equipped=True的装备）
    equipped_only = [eq for eq in equipped_items if getattr(eq, "equipped", False)]
    _apply_mp_from_hp_effects(player, equipped_only, session)

    # 4b. 再处理 hp_from_attack 类全局被动（诡面骰骰相·命，以总攻击力为基数）
    _apply_hp_from_attack_effects(player, equipped_only, session)

    # 5. 确保当前 HP/MP 不超过新的上限
    if player.hp > player.max_hp:
        player.hp = player.max_hp
    if player.mp > player.max_mp:
        player.mp = player.max_mp

    session.add(player)
