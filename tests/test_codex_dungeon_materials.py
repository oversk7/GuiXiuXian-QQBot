import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.item import codex_world, codex_service, codex_sources, catalog
from plugins.xiuxian_game.world import dungeon_generation_service as dungeon
from plugins.xiuxian_game.models.inventory import ItemInstance


def ids_for(entry, prefix):
    return {key for line in entry['lines'] if line.startswith(prefix)
            for key in re.findall(r'text="图鉴 item:([^"]+)"', line)}


@pytest.mark.parametrize('depth', [1, 4, 5, 12, 13, 20, 21, 40, 41, 50, 100, 200, 201, 999, 1000])
def test_depth_lists_actual_battle_candidates_including_global_fallback(depth):
    entry = codex_world.dungeon_entry(depth)
    rules = dungeon.config.map_config['dungeon_generation_rules']
    level = dungeon.config._generate_dungeon_level_config(depth, rules)
    pools = dungeon.get_region_materials(f'{depth}层诡域')
    expected = {key for rarity in dungeon.get_monster_material_rates(level['level_range'][1])
                for key in dungeon.get_monster_material_candidates(pools, rarity)}
    assert ids_for(entry, '战斗材料：') == expected
    extras = {key for rarity in dungeon.get_merchant_extra_rarities(level['tier'])
              for key in dungeon.get_materials_by_rarity(rarity)}
    assert ids_for(entry, '商人随机补充：') == extras
    assert dungeon.FRAGMENT_ITEM_ID in ids_for(entry, '精英独立材料：')


def test_global_fallback_respects_local_priority_and_orange_exclusion():
    assert dungeon.get_monster_material_candidates({'basic': ['grave_soil'], 'merchant': []}, 'orange') == []
    assert 'soul_crystal' in dungeon.get_monster_material_candidates({'basic': [], 'merchant': []}, 'blue')
    assert dungeon.get_monster_material_candidates({'basic': [], 'merchant': ['soul_crystal']}, 'blue') == ['soul_crystal']
    assert dungeon.get_monster_material_candidates({'basic': ['flesh_crystal'], 'merchant': []}, 'white') == ['flesh_crystal']


def test_non_drop_materials_are_not_added_to_global_random_pools():
    entry = codex_world.dungeon_entry(50)
    random_pool = ids_for(entry, '商人随机补充：')
    assert dungeon.FRAGMENT_ITEM_ID not in random_pool
    assert dungeon.TREASURE_MATERIAL_ITEM_ID not in random_pool
    assert dungeon.TREASURE_MATERIAL_ITEM_ID in ids_for(entry, '探索宝箱独立材料：')
    for item_id in random_pool:
        item = dungeon.config.items_config['by_id'][item_id]
        assert not {'no_drop', 'event_only', 'inner_realm_only'}.intersection(item.tags)


@pytest.mark.parametrize('level, expected', [
    (20, {'white': .30, 'green': .10}),
    (21, {'white': .40, 'green': .20, 'blue': .05}),
    (60, {'white': .40, 'green': .20, 'blue': .05}),
    (61, {'white': .30, 'green': .25, 'blue': .15, 'purple': .03}),
    (101, {'white': .20, 'green': .20, 'blue': .20, 'purple': .08, 'orange': .01}),
    (201, {'white': .15, 'green': .15, 'blue': .25, 'purple': .12, 'orange': .03}),
])
def test_extraction_keeps_existing_drop_rates(level, expected):
    assert dungeon.get_monster_material_rates(level) == expected


async def test_actual_drop_settlement_uses_the_shared_candidates(monkeypatch):
    add_item = AsyncMock()
    monkeypatch.setattr(ItemInstance, 'add_item', add_item)
    monkeypatch.setattr(dungeon, '_roll_additional_equipment', lambda *args: None)
    # Lv.80: 四次材料成功判定，各随后一次幸运数量判定失败，最后装备判定失败。
    rolls = iter([0, 1] * 4 + [1])
    rng = SimpleNamespace(random=lambda: next(rolls), choice=lambda pool: pool[0], randint=lambda lo, hi: lo)
    pools = dungeon.get_region_materials('50层诡域')
    expected = [dungeon.get_monster_material_candidates(pools, rarity)[0]
                for rarity in dungeon.get_monster_material_rates(80)]
    await dungeon.handle_monster_drops(SimpleNamespace(), SimpleNamespace(id=123, luck=0), 80, '50层诡域', rng)
    assert [call.args[2] for call in add_item.await_args_list] == expected


async def test_dungeon_pagination_retains_depth_and_all_materials(monkeypatch):
    entry = codex_world.dungeon_entry(50)
    _, _, pages = codex_service.detail_page(entry)
    assert pages > 1
    collected = []
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(catalog.catalog_cmd, 'finish', finish)
    for page in range(1, pages + 1):
        with pytest.raises(FinishedException):
            await catalog._(SimpleNamespace(), Message(f'诡域 50 {page}'))
        text = finish.await_args.args[0].data['markdown'].content
        collected.append(text)
        if page < pages:
            assert f'text="图鉴 诡域 50 {page + 1}"' in text
    for line in entry['lines']:
        assert line in '\n'.join(collected)


def test_inverse_item_sources_acknowledge_supplemental_pools():
    text = '\n'.join(codex_sources.source_lines('soul_crystal'))
    assert '战斗同品质补充池' in text and '商人随机补充' in text
    assert '独立掉落' in '\n'.join(codex_sources.source_lines(dungeon.FRAGMENT_ITEM_ID))
    assert '手动探索宝箱格' in '\n'.join(codex_sources.source_lines(dungeon.TREASURE_MATERIAL_ITEM_ID))
