from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.item import catalog, codex_service


async def invoke(monkeypatch, query):
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(catalog.catalog_cmd, 'finish', finish)
    with pytest.raises(FinishedException):
        await catalog._(SimpleNamespace(), Message(query))
    return finish.await_args.args[0].data['markdown'].content


@pytest.mark.parametrize('query', ['诡域 0', '诡域 -2', '诡域 abc', '诡域 ²', '诡域 ' + '9' * 5000])
async def test_invalid_depth_is_a_friendly_reply(monkeypatch, query):
    assert '正整数深度' in await invoke(monkeypatch, query)


async def test_numeric_suffix_in_full_name_is_not_a_page(monkeypatch):
    entry = {'key': 'npc:test', 'name': '值班员 2', 'category': '人物', 'description': '完整姓名', 'aliases': [], 'lines': []}
    monkeypatch.setattr(codex_service, 'get_entries', lambda: [entry])
    text = await invoke(monkeypatch, '值班员 2')
    assert '完整姓名' in text and '值班员 2' in text


async def test_source_query_accepts_player_facing_name(monkeypatch):
    text = await invoke(monkeypatch, '来源 回春散')
    assert '回春散 来源与用途' in text and '黑市基础商品' in text


async def test_unknown_source_query_does_not_invent_an_item(monkeypatch):
    assert '未找到该物品' in await invoke(monkeypatch, '来源 不存在物品xyz')


async def test_item_name_numeric_suffix_works_in_source_query(monkeypatch):
    entry = {'key': 'item:test', 'name': '药剂 2', 'category': '丹药与消耗品', 'description': '', 'aliases': [], 'lines': []}
    monkeypatch.setattr(codex_service, 'get_entries', lambda: [entry])
    monkeypatch.setattr(codex_service, 'get_item_relations', lambda item_id: ['正确来源'] if item_id == 'test' else [])
    text = await invoke(monkeypatch, '来源 药剂 2')
    assert '药剂 2 来源与用途' in text and '正确来源' in text
