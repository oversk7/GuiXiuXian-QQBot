from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException

from plugins.xiuxian_game.item import catalog
from plugins.xiuxian_game import platform_utils


@pytest.mark.parametrize('query', ['回春散', 'item:heal_potion'])
async def test_item_name_and_stable_link_keep_original_detail_and_relations(monkeypatch, query):
    @asynccontextmanager
    async def no_database():
        yield SimpleNamespace()

    monkeypatch.setattr(catalog, 'safe_session', no_database)
    monkeypatch.setattr(platform_utils, 'get_unified_player', AsyncMock(return_value=None))
    monkeypatch.setattr(catalog, '_get_item_image_url', lambda key: '')
    finish = AsyncMock(side_effect=FinishedException)
    send = AsyncMock()
    monkeypatch.setattr(catalog.catalog_cmd, 'finish', finish)
    monkeypatch.setattr(catalog.catalog_cmd, 'send', send)
    with pytest.raises(FinishedException):
        await catalog._(SimpleNamespace(), Message(query))
    assert send.await_count == 1
    text = send.await_args.args[0].data['markdown'].content
    assert '回春散' in text and '50' in text
    assert '来源' in text and 'item:heal_potion' in text
