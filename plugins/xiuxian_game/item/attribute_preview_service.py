"""装备属性投影原语：与真实重算共享逐件加成与转换取整。"""
from copy import deepcopy

from ..models.inventory import ItemInstance
from ..models.player import Player

MAIN_ATTRS = ("max_hp", "max_mp", "attack", "defense", "agility", "luck")


def snapshot_equipment(item: ItemInstance, *, equipped: bool = True) -> ItemInstance:
    """构造无 session 的装备副本；JSON 嵌套值必须独立。"""
    return ItemInstance(
        id=item.id, player_id=item.player_id, item_id=item.item_id,
        equipped=equipped, durability=item.durability,
        upgrade_level=item.upgrade_level,
        extra_attrs=deepcopy(item.extra_attrs or {}),
        gem_slots_data=deepcopy(item.gem_slots_data or {}),
    )


def remove_persisted(attrs: dict, item: ItemInstance) -> None:
    for key, value in (item.extra_attrs or {}).get("_persist_bonus", {}).items():
        attrs[key] = max(0, attrs.get(key, 0) - int(value or 0))


def equipment_delta(item: ItemInstance, base: dict) -> dict:
    """与 ItemInstance.apply_attr_bonus 同源；各件始终使用同一 base。"""
    after = base.copy()
    item.apply_attr_bonus(after, base)
    return {key: value - base.get(key, 0) for key, value in after.items()
            if value != base.get(key, 0)}


def apply_equipment_deltas(attrs: dict, items: list[ItemInstance]) -> None:
    base = {key: attrs[key] for key in MAIN_ATTRS}
    for item in items:
        delta = equipment_delta(item, base)
        for key, value in delta.items():
            attrs[key] = attrs.get(key, 0) + value
        item.extra_attrs = {**(item.extra_attrs or {}), "_persist_bonus": delta}


def conversion_parts(items: list[ItemInstance], effect: str, base_value: int) -> list[tuple[ItemInstance, int]]:
    """保留总额一次取整、每件取整且末件收尾的真实分摊方式。"""
    effects = []
    total_pct = 0.0
    total_flat = 0
    for item in items:
        if not item.equipped or not item.config:
            continue
        for entry in item.config.special_effects or []:
            if entry.get("effect") != effect:
                continue
            is_pct = bool(entry.get("is_percentage", True))
            if effect == "hp_from_attack" and not is_pct:
                continue
            value = float(entry.get("value", 0) or 0) if is_pct else int(entry.get("value", 0) or 0)
            if value <= 0:
                continue
            effects.append((item, value, is_pct))
            if is_pct:
                total_pct += value
            else:
                total_flat += value
    multiplier = 3 if effect == "hp_from_attack" else 1
    total = int(base_value * total_pct / 100.0 * multiplier) + total_flat
    if total <= 0:
        return []
    remaining = total
    result = []
    for index, (item, value, is_pct) in enumerate(effects):
        part = int(base_value * value / 100.0 * multiplier) if is_pct else int(value)
        part = remaining if index == len(effects) - 1 else min(part, remaining)
        if part > 0:
            remaining = max(0, remaining - part)
            result.append((item, part))
    return result


def apply_conversion(attrs: dict, items: list[ItemInstance], effect: str) -> None:
    target = "max_mp" if effect == "mp_from_hp" else "max_hp"
    source = "max_hp" if effect == "mp_from_hp" else "attack"
    for item, part in conversion_parts(items, effect, max(1, int(attrs.get(source, 0) or 0))):
        attrs[target] = int(attrs.get(target, 0)) + part
        extra = item.extra_attrs or {}
        persist = dict(extra.get("_persist_bonus", {}))
        persist[target] = int(persist.get(target, 0)) + part
        item.extra_attrs = {**extra, "_persist_bonus": persist}


def project_equipment(player, equipped: list[ItemInstance], target: ItemInstance,
                      removed: ItemInstance | None = None) -> tuple[dict, list[ItemInstance]]:
    """模拟卸下后重新穿戴的存储值，绝不触碰 ORM 实例。"""
    attrs = {key: getattr(player, key) for key in Player.INIT_ATTRS}
    if removed is not None:
        remove_persisted(attrs, removed)
    remaining = [item for item in equipped if removed is None or item.id != removed.id]
    for item in remaining:
        remove_persisted(attrs, item)
    copies = [snapshot_equipment(item) for item in remaining] + [snapshot_equipment(target)]
    apply_equipment_deltas(attrs, copies)
    apply_conversion(attrs, copies, "mp_from_hp")
    apply_conversion(attrs, copies, "hp_from_attack")
    return attrs, copies
