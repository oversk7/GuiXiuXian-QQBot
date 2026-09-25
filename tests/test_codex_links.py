"""遍历真实百科，防止跨类别同名、动态注册及关联跳转断链。"""
import html
import re

from plugins.xiuxian_game.item import codex_service
from plugins.xiuxian_game.config import config


def test_all_public_stable_entry_links_resolve_uniquely():
    entries = codex_service.get_entries()
    assert len({entry['key'] for entry in entries}) == len(entries)
    texts = [line for entry in entries for line in [entry['description'], *entry['lines']]]
    texts.extend(line for item_id in config.items_config['by_id']
                 for line in codex_service.get_item_relations(item_id))
    targets = {html.unescape(target) for text in texts
               for target in re.findall(r'text="图鉴 ([^"]+)"', text)}
    assert len(targets) > 50
    for target in targets:
        if ':' not in target:
            continue
        hits = codex_service.search_entries(target, entries)
        assert len(hits) == 1 and hits[0]['key'] == target, target


def test_dynamically_registered_dishes_are_searchable_and_link_to_recipes(monkeypatch):
    from copy import deepcopy
    from plugins.xiuxian_game.cooking.cooking_service import RecipeManager
    from plugins.xiuxian_game.cooking.dish_item_generator import DishItemGenerator

    original = config.items_config
    monkeypatch.setattr(config, '_cached_items_config', deepcopy(original))
    before = {entry['key'] for entry in codex_service.get_entries()}
    DishItemGenerator.register_dish_items_to_config(config, RecipeManager())
    entries = codex_service.get_entries()
    for recipe in RecipeManager().get_all_recipes():
        for quality in DishItemGenerator.QUALITY_NAMES:
            item_id = f'dish_{recipe.recipe_id}_{quality}'
            hits = codex_service.search_entries(f'item:{item_id}', entries)
            assert len(hits) == 1
            relations = codex_service.get_item_relations(item_id)
            assert any(f'text="图鉴 cooking:{recipe.recipe_id}"' in line for line in relations)
    assert len(entries) >= len(before)


def test_public_mechanism_queries_expose_actual_rules():
    entries = codex_service.get_entries()
    hits = codex_service.search_entries('暴击', entries)
    text = '\n'.join(line for hit in hits for line in [hit['description'], *hit['lines']])
    assert '暴击倍率' in text or '暴击力' in text
    assert 'AI客服专用' not in text and '供AI客服' not in text
    assert not any(entry['key'].startswith('knowledge:admin') for entry in entries)
