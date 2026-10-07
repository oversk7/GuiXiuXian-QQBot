"""地图回复等待网络时，事务必须已提交并释放唯一数据库连接。"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game.models.db import safe_session
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory
from plugins.xiuxian_game.world import map_locations, map_visualizer


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", ["map", "map_import_error", "map_value_error", "unregistered", "nearby_region"])
async def test_map_reply_releases_transaction_before_network(monkeypatch, tmp_path, scenario):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{(tmp_path / 'map.db').as_posix()}",
        pool_size=1, max_overflow=0, pool_timeout=0.2,
    )
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE TABLE context_marker (value INTEGER)"))
    monkeypatch.setattr(map_locations, "safe_session", lambda: safe_session(factory))
    player = SimpleNamespace(id="player", nickname="测试", region="下界", get_current_coordinates=lambda: (1, 2))

    async def identify(session, event):
        await session.execute(text("INSERT INTO context_marker VALUES (1)"))
        return None if scenario == "unregistered" else player

    monkeypatch.setattr(map_locations, "get_unified_player", identify)
    monkeypatch.setattr(map_locations, "message_add_head", lambda message, event: message)
    generated = AsyncMock(return_value=b"image")
    if scenario == "map_import_error":
        generated.side_effect = ImportError("missing image dependency")
    elif scenario == "map_value_error":
        generated.side_effect = ValueError("invalid coordinates")
    monkeypatch.setattr(map_visualizer.MapVisualizer, "generate_map", generated)
    nearby = scenario == "nearby_region"
    matcher = map_locations.nearby_locations_cmd if nearby else map_locations.visual_map_cmd

    async def send_with_network_failure(message):
        # 发送仍未结束时，其他会话能获取唯一连接，并看到已提交的上下文写入。
        async with safe_session(factory) as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM context_marker")) == 1
            await session.execute(text("INSERT INTO context_marker VALUES (2)"))
        raise TimeoutError("simulated slow QQ upload")

    finish = AsyncMock(side_effect=send_with_network_failure)
    monkeypatch.setattr(matcher, "finish", finish)
    handler = map_locations.handle_nearby_locations if nearby else map_locations.handle_visual_map
    try:
        with pytest.raises(TimeoutError, match="slow QQ"):
            await handler(SimpleNamespace())
        finish.assert_awaited_once()
        async with safe_session(factory) as session:
            assert await session.scalar(text("SELECT COUNT(*) FROM context_marker")) == 2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("nearby", [False, True])
async def test_slow_map_reply_does_not_block_same_player_update(mysql_session_factory, monkeypatch, nearby):
    factory = mysql_session_factory
    async with safe_session(factory) as session:
        session.add(Player(id="map-player", uid=1, nickname="地图玩家", gold=100, region="下界"))
    monkeypatch.setattr(map_locations, "safe_session", lambda: safe_session(factory))
    monkeypatch.setattr(map_locations, "message_add_head", lambda message, event: message)
    touched = datetime.now().replace(microsecond=0)

    async def identify(session, event):
        player = await session.get(Player, "map-player")
        player.last_active_at = touched
        # 复现原命令在后续查询 autoflush 时取得玩家行锁。
        await session.flush()
        return player

    monkeypatch.setattr(map_locations, "get_unified_player", identify)
    monkeypatch.setattr(map_visualizer.MapVisualizer, "generate_map", AsyncMock(return_value=b"image"))

    async def update_player():
        async with safe_session(factory) as session:
            player = await session.get(Player, "map-player")
            assert player.last_active_at == touched
            player.gold -= 20

    async def slow_send(message):
        # 回复仍在等待时，另一个任务必须能在 2 秒内提交对同一行的修改。
        await asyncio.wait_for(asyncio.create_task(update_player()), timeout=2)
        raise TimeoutError("QQ upload still waiting")

    matcher = map_locations.nearby_locations_cmd if nearby else map_locations.visual_map_cmd
    finish = AsyncMock(side_effect=slow_send)
    monkeypatch.setattr(matcher, "finish", finish)
    handler = map_locations.handle_nearby_locations if nearby else map_locations.handle_visual_map
    with pytest.raises(TimeoutError, match="QQ upload"):
        await handler(SimpleNamespace())
    finish.assert_awaited_once()
    async with safe_session(factory) as session:
        player = await session.get(Player, "map-player")
        assert player.gold == 80 and player.version_id == 2
        assert player.last_active_at == touched


@pytest.mark.asyncio
async def test_map_commit_failure_does_not_send_success(monkeypatch):
    @asynccontextmanager
    async def failed_session():
        yield SimpleNamespace()
        raise RuntimeError("commit failed")

    monkeypatch.setattr(map_locations, "safe_session", failed_session)
    monkeypatch.setattr(map_locations, "get_unified_player", AsyncMock(return_value=None))
    finish = AsyncMock()
    monkeypatch.setattr(map_locations.visual_map_cmd, "finish", finish)
    with pytest.raises(RuntimeError, match="commit failed"):
        await map_locations.handle_visual_map(SimpleNamespace())
    finish.assert_not_awaited()
