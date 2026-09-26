"""战斗属性的只读来源汇总；数值与上限复用战斗计算器。"""
from typing import Iterable

from .battle_attributes import BattleAttributeCalculator


MAIN_ATTRIBUTE_NAMES = {
    "max_hp": "最大生命", "max_mp": "最大理智", "attack": "攻击力",
    "defense": "防御力", "agility": "敏捷", "luck": "运气",
}
BATTLE_ATTRIBUTE_NAMES = {
    "critical_rate": "暴击率", "critical_power": "暴击力",
    "combo_rate": "连击率", "counter_rate": "反击率",
    "dodge_rate": "闪避率", "accuracy_rate": "命中率",
    "skill_crit_rate": "灵爆率", "penetration_rate": "穿透率",
    "anti_crit_rate": "抗暴率", "anti_combo_rate": "抗连击率",
    "anti_counter_rate": "抗反击率", "lifesteal_rate": "吸血率",
    "immobilize_rate": "定身率", "true_damage_rate": "真伤率",
    "regen_rate": "回复率",
}
ATTRIBUTE_NAMES = {**MAIN_ATTRIBUTE_NAMES, **BATTLE_ATTRIBUTE_NAMES}


def format_attribute_value(value: float) -> str:
    """最多显示两位小数，保留宠物和词缀的小数收益。"""
    return f"{value:.2f}".rstrip("0").rstrip(".") if value else "0"


def summarize_battle_attributes(
    effective_attrs: dict, equipped_items: Iterable = (), level: int = 1,
) -> dict[str, dict]:
    """在真源上叠加词缀、套装；不改玩家或装备对象。"""
    from ..item.affix_service import get_affixes_from_equipment, get_t1_battle_bonuses
    from ..item.set_bonus_service import get_set_t1_bonuses

    items = list(equipped_items)
    affix_bonus = {}
    for item in items:
        affixes = get_affixes_from_equipment(getattr(item, "extra_attrs", None))
        for name, value in get_t1_battle_bonuses(affixes).items():
            affix_bonus[name] = affix_bonus.get(name, 0) + value
    set_bonus = get_set_t1_bonuses([getattr(item, "item_id", "") for item in items])
    combined = dict(affix_bonus)
    for name, value in set_bonus.items():
        combined[name] = combined.get(name, 0) + value
    rows = BattleAttributeCalculator.calculate_attribute_breakdown(effective_attrs, level, combined)
    for name, row in rows.items():
        row["affix"] = affix_bonus.get(name, 0)
        row["set"] = set_bonus.get(name, 0)
    return rows


async def get_battle_attribute_summary(
    player, session=None, *, effective_attrs: dict | None = None,
    equipped_items: list | None = None,
) -> dict[str, dict]:
    """收集当前装备与有效属性，提供与开战相同的数值来源。"""
    if effective_attrs is None:
        effective_attrs = await player.get_effective_attributes(session)
    if equipped_items is None:
        equipped_items = []
        if session is not None:
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..item.equipment_service import EQUIP_ITEM_IDS
            equipped_items = await ItemRepository(session).get_equipped_equipment(player.id, EQUIP_ITEM_IDS)
    return summarize_battle_attributes(effective_attrs, equipped_items, player.level)


def format_battle_attribute_line(name: str, row: dict) -> str:
    """区分原始数值、开战生效值及超出硬上限的部分。"""
    fmt = format_attribute_value
    suffix = "点" if name == "critical_power" else "%"
    text = f"{BATTLE_ATTRIBUTE_NAMES[name]}：原始{fmt(row['raw'])}{suffix} → 生效{fmt(row['effective'])}{suffix}"
    notes = []
    if row["cap"] is not None:
        notes.append(f"上限{fmt(row['cap'])}{suffix}")
    if row["overflow"] > 0:
        unit = "点" if name == "critical_power" else "个百分点"
        notes.append(f"溢出{fmt(row['overflow'])}{unit}")
    if name in {"immobilize_rate", "true_damage_rate"} and row["effective"] >= 100:
        notes.append("触发概率最多100%")
    if notes:
        text += f"（{'，'.join(notes)}）"
    return text
