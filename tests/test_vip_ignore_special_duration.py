"""VIP 定制装备的无视特殊属性效果应持续整场战斗。"""
from pathlib import Path

import yaml

from plugins.xiuxian_game.battle.battle_effects import (
    BattleEffectManager,
    EffectType,
    TriggerType,
    parse_triggers_from_yaml,
)


ITEMS_PATH = Path("plugins/xiuxian_game/data/items.yaml")
TARGET_ITEM_IDS = {"vip_blade_zhanlongshan", "vip_ghost_dice"}


def _find_items(node, found):
    if isinstance(node, dict):
        item_id = node.get("item_id")
        if item_id in TARGET_ITEM_IDS:
            found[item_id] = node
        for value in node.values():
            _find_items(value, found)
    elif isinstance(node, list):
        for value in node:
            _find_items(value, found)


def test_vip_ignore_special_remains_active_after_turn_tick():
    with ITEMS_PATH.open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    items = {}
    _find_items(data, items)
    assert set(items) == TARGET_ITEM_IDS

    for item_id, item in items.items():
        raw_effect = next(
            effect
            for effect in item["special_effects"]
            if effect.get("effect") == EffectType.IGNORE_SPECIAL.value
        )
        assert raw_effect["duration"] == -1, item_id

        [trigger] = parse_triggers_from_yaml([raw_effect])
        assert trigger.trigger == TriggerType.PASSIVE
        assert trigger.duration == -1

        manager = BattleEffectManager()
        manager.register_triggers(item_id, [trigger])
        [effect] = manager.check_triggers(
            item_id,
            TriggerType.PASSIVE,
            {"source": "战斗开始"},
        )
        manager.add_effect(item_id, effect)

        assert manager.tick_effects(item_id) == []
        [active_effect] = manager.get_active_effects(item_id, EffectType.IGNORE_SPECIAL)
        assert active_effect.duration == -1
