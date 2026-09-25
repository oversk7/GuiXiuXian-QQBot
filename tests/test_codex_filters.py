from types import SimpleNamespace

import pytest

from plugins.xiuxian_game.item import codex_filters


@pytest.mark.parametrize('query, expected', [
    ('装备 蓝色 100级 2', ('blue', 100, 2)),
    ('装备 100级', (None, 100, 1)),
    ('装备 紫色', ('purple', None, 1)),
    ('装备 2', None),
    ('装备', None),
    ('装备 蓝色 紫色', None),
    ('装备 蓝色 2 3', None),
])
def test_parse_explicit_filter_and_keep_bare_page_semantics(query, expected):
    assert codex_filters.parse_equipment_query(query) == expected


def test_filters_current_definitions_without_including_recipes(monkeypatch):
    items = {
        'a': SimpleNamespace(type='EQUIPMENT', rarity='blue', required_level=30),
        'b': SimpleNamespace(type='EQUIPMENT', rarity='blue', required_level=101),
        'c': SimpleNamespace(type='MATERIAL', rarity='blue', required_level=1),
        'd': SimpleNamespace(type='EQUIPMENT', rarity='purple', required_level=1),
    }
    monkeypatch.setattr(codex_filters, 'config', SimpleNamespace(items_config={'by_id': items}))
    entries = [{'key': f'item:{key}', 'name': key} for key in items]
    entries.append({'key': 'craft:a', 'name': 'a配方'})
    assert [e['key'] for e in codex_filters.filter_equipment(entries, 'blue', 100)] == ['item:a']
    items['a'].required_level = 150
    assert codex_filters.filter_equipment(entries, 'blue', 100) == []
