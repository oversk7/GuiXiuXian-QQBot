from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.item import catalog, codex_service


def content_of(message):
    return message.data["markdown"].content.replace("\r", "\n")


@pytest.mark.parametrize("category,page", [("材料", 1), ("丹药", 2)])
def test_catalog_list_format_contains_clickable_entry(category, page):
    content = catalog._format_codex_list(
        [{"key": "item:flesh_crystal", "name": "血肉结晶", "category": category, "description": "诡域材料"}],
        category, page, 3, category,
    )
    assert f"第 {page}/3 页" in content
    assert '<qqbot-cmd-input text="图鉴 item:flesh_crystal" show="血肉结晶"' in content


async def test_catalog_delegates_specific_dungeon_depth(monkeypatch):
    result = {"name": "50重诡域", "description": "怪物等级范围", "lines": ["产出：血肉结晶"]}
    monkeypatch.setattr(codex_service, "dungeon_entry", lambda depth: result if depth == 50 else None)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(catalog.catalog_cmd, "finish", finish)

    with pytest.raises(FinishedException):
        await catalog._(SimpleNamespace(), Message("诡域 50"))

    message = content_of(finish.await_args.args[0])
    assert "50重诡域" in message
    assert "产出：血肉结晶" in message


async def test_equipment_filter_preserves_level_and_query_in_next_page(monkeypatch):
    from plugins.xiuxian_game.item import codex_filters

    entries = [
        {"key": f"item:e{i}", "name": f"装备{i}", "category": "装备", "description": "", "aliases": [], "lines": []}
        for i in range(17)
    ]
    monkeypatch.setattr(codex_service, "get_entries", lambda: entries)
    monkeypatch.setattr(codex_filters, "filter_equipment", lambda rows, rarity, level: rows)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(catalog.catalog_cmd, "finish", finish)

    with pytest.raises(FinishedException):
        await catalog._(SimpleNamespace(), Message("装备 蓝色 100级 2"))

    message = content_of(finish.await_args.args[0])
    assert "等级要求不高于100；转生条件见装备详情" in message
    assert 'text="图鉴 装备 蓝色 100级 3"' in message


async def test_catalog_routes_category_to_paginated_list(monkeypatch):
    entries = [
        {"key": "item:flesh_crystal", "name": "血肉结晶", "category": "材料", "description": "材料描述", "aliases": [], "lines": []},
    ]
    monkeypatch.setattr(codex_service, "get_entries", lambda: entries)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(catalog.catalog_cmd, "finish", finish)

    with pytest.raises(FinishedException):
        await catalog._(SimpleNamespace(), Message("材料 1"))

    message = content_of(finish.await_args.args[0])
    assert "材料（第 1/1 页）" in message
    assert "血肉结晶" in message
