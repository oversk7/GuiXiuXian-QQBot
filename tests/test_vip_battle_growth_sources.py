"""战后成长携带稳定装备来源，修改描述不改变结算归属。"""
from types import SimpleNamespace

import pytest

from plugins.xiuxian_game.battle.enhanced_engine import EnhancedBattleEngine
from plugins.xiuxian_game.config import config


@pytest.mark.parametrize("item_id", [
    "vip_blade_zhanlongshan", "vip_gui_yu", "vip_chrono_watch", "vip_ghost_dice",
])
def test_kill_growth_keeps_equipment_id_when_description_changes(item_id):
    template = config.items_config["by_id"][item_id]
    effects = [dict(effect, description="重新措辞的技能介绍") for effect in template.special_effects]
    equipment = SimpleNamespace(
        item_id=item_id, upgrade_level=0, extra_attrs={}, gem_slots_data={},
        config=SimpleNamespace(name=template.name, special_effects=effects),
    )
    player = SimpleNamespace(id="P1", nickname="测试", hp=100, max_hp=100)
    engine = EnhancedBattleEngine(seed="vip-growth-source")
    engine._register_equipment_triggers(player.id, [equipment])
    engine._equipped_items_cache[player.id] = [equipment]

    result = engine.trigger_on_kill(player, {"name": "木桩"})

    assert result["post_battle_effects"]
    assert all(effect["source_item_id"] == item_id for effect in result["post_battle_effects"])
