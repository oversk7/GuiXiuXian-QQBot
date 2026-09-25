from types import SimpleNamespace

from plugins.xiuxian_game.item import codex_sources
from plugins.xiuxian_game.economy import merchant_service
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService
from plugins.xiuxian_game.item import equipment_upgrade_service


def test_market_buyback_is_not_an_acquisition_source(monkeypatch):
    market = merchant_service.MarketConfig('test', '测试市集', (1, 2), ['heal_potion'], ['spirit_herb'])
    monkeypatch.setattr(merchant_service, 'MARKETS', [market])
    assert '测试市集' in '\n'.join(codex_sources.source_lines('heal_potion'))
    assert '测试市集' not in '\n'.join(codex_sources.source_lines('spirit_herb'))


def test_black_market_candidates_are_not_promised_as_current_stock():
    text = '\n'.join(codex_sources.source_lines('upgrade_stone_low'))
    assert '不保证今日上架' in text
    assert str(merchant_service.HEADQUARTERS_ITEMS['upgrade_stone_low']) in text


def test_chapter_and_step_rewards_use_runtime_configuration(monkeypatch):
    monkeypatch.setattr(NoviceQuestService, '_quest_config', {'chains': [{
        'name': '测试章', 'steps': [{'title': '测试步', 'rewards': {'items': [{'item_id': 'heal_potion', 'quantity': 7}]}}],
        'completion_reward': {'items': [{'item_id': 'heal_potion', 'quantity': 9}]},
    }]})
    text = '\n'.join(codex_sources.source_lines('heal_potion'))
    assert '测试章·测试步' in text and '×7' in text
    assert '章节「测试章」完成奖励 ×9' in text


def test_material_depth_boundaries_follow_runtime_generator():
    text = '\n'.join(codex_sources.source_lines('world_fragment'))
    assert '201-999' in text
    assert '1000 重及以上' not in text
    assert '1000 重及以上' in '\n'.join(codex_sources.source_lines('grave_soil'))


def test_upgrade_uses_ignore_unused_tables_and_follow_current_cost(monkeypatch):
    item = SimpleNamespace(name='测试剑', type=SimpleNamespace(value='EQUIPMENT'), recipe={'materials': {}}, rarity='white')
    monkeypatch.setattr(codex_sources, 'config', SimpleNamespace(items_config={'by_id': {'test': item}}))
    monkeypatch.setattr(equipment_upgrade_service, '_upgrade_config', {'materials': {
        'normal': {1: {'material': 13}}, 'unreleased': {9: {'material': 99}},
    }})
    text = '\n'.join(codex_sources.upgrade_use_lines('material'))
    assert '1阶×13' in text
    assert '99' not in text


def test_fishing_distinguishes_coastal_dungeon_and_salvage():
    assert '舟山沿海特色钓点专属鱼' in '\n'.join(codex_sources.source_lines('zhoushan_tide_fish'))
    assert '诡域垂钓鱼池' in '\n'.join(codex_sources.source_lines('pale_scale_fish'))
    assert '诡域钓鱼打捞池' in '\n'.join(codex_sources.source_lines('bloodstained_room_card'))


def test_extra_equipment_drop_source_uses_configured_level_band():
    items = codex_sources.config.items_config['by_id']
    for item_id, item in items.items():
        if not item.dungeon_drop:
            continue
        text = '\n'.join(codex_sources.source_lines(item_id))
        assert f"Lv.{item.dungeon_drop['min_level']}" in text
        if item.dungeon_drop.get('max_level') is not None:
            assert f"～{item.dungeon_drop['max_level']}" in text


def test_unknown_item_has_no_invented_sources():
    assert codex_sources.source_lines('nonexistent_item') == []
