import asyncio
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import event as sql_event, select

from plugins.xiuxian_game import platform_utils
from plugins.xiuxian_game.auction import auction_commands
from plugins.xiuxian_game.economy import market
from plugins.xiuxian_game.infrastructure.cache.player_identity_cache import PlayerIdentityCache
from plugins.xiuxian_game.infrastructure.locking import lock_row
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.account_ownership import AccountOwnership
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.platform_server_binding import PlatformServerBinding
from plugins.xiuxian_game.social import gift_commands
from tests.mysql_helpers import mysql_session_factory


LISTENERS = [
    (auction_commands, "auction_equipment_selection_handler", "_auction_equipment_selection_state"),
    (market, "equipment_selection_handler", "equipment_selection_state"),
    (gift_commands, "equipment_transfer_selection_handler", "equipment_transfer_selection_state"),
]


def make_event(text, user_id="platform"):
    return SimpleNamespace(
        get_message=lambda: Message(text), get_user_id=lambda: user_id,
        get_session_id=lambda: f"group_test_{user_id}", group_openid="new-group",
        author=SimpleNamespace(member_openid="new-member", username="新昵称"),
    )


def selection_state():
    return {"equipment_ids": [7], "price": 10, "receiver_uid": 2,
            "item_name": "测试装备", "start_price": 10, "duration_hours": 1,
            "buyout_price": None, "timestamp": time.time()}


@pytest.mark.parametrize("module,matcher_name,state_name", LISTENERS)
@pytest.mark.parametrize("case", ["empty", "expired", "unrelated"])
async def test_unrelated_selection_messages_do_not_open_session(monkeypatch, module, matcher_name, state_name, case):
    state = selection_state()
    if case == "expired":
        state["timestamp"] = 0
    monkeypatch.setattr(module, state_name, {} if case == "empty" else {"player": state})
    factory = Mock(side_effect=AssertionError("无关消息不应打开数据库会话"))
    monkeypatch.setattr(module, "UnitOfWork" if module is auction_commands else "safe_session", factory)
    await getattr(module, matcher_name).handlers[0].call(make_event("修炼" if case == "unrelated" else "1"))
    factory.assert_not_called()


@pytest.mark.parametrize("module,matcher_name,state_name", LISTENERS)
@pytest.mark.parametrize("text", ["取消", "2", "1"])
async def test_selection_still_cancels_validates_and_executes(monkeypatch, module, matcher_name, state_name, text):
    player = SimpleNamespace(id="player")
    equipment = SimpleNamespace(id=7, player_id=player.id)
    state = {player.id: selection_state()}
    monkeypatch.setattr(module, state_name, state)
    session = SimpleNamespace(autoflush=True, commit=AsyncMock(), rollback=AsyncMock(),
                              get=AsyncMock(return_value=equipment))

    async def get(model, key):
        return player if model is Player else equipment

    session.get.side_effect = get
    uow = SimpleNamespace(session=session, commit=session.commit, rollback=session.rollback)

    @asynccontextmanager
    async def context(*args):
        yield uow if module is auction_commands else session

    monkeypatch.setattr(module, "UnitOfWork" if module is auction_commands else "safe_session", context)
    identity = AsyncMock(return_value=player)
    monkeypatch.setattr(module, "get_unified_player", identity)
    monkeypatch.setattr(module, "message_add_head", lambda message, event: message)
    matcher = getattr(module, matcher_name)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(matcher, "finish", finish)
    action = AsyncMock(return_value=(True, "上架成功"))
    if module is auction_commands:
        monkeypatch.setattr(module.auction_service, "list_auction", action)
    else:
        action.side_effect = FinishedException
        monkeypatch.setattr(module, "_create_instance_order" if module is market else "_execute_equipment_transfer", action)

    with pytest.raises(FinishedException):
        await matcher.handlers[0].call(make_event(text))
    assert identity.await_args.kwargs == {"read_only": True}
    if text == "1":
        action.assert_awaited_once()
        assert not state
        if module is auction_commands:
            session.commit.assert_awaited_once()
    else:
        action.assert_not_awaited()
        assert (player.id in state) == (text == "2")
        assert ("取消" if text == "取消" else "无效") in finish.await_args.args[0]


async def test_mysql_selection_observers_do_not_wait_for_player_writer(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(auction_commands, "AsyncSessionLocal", factory)
    cache = PlayerIdentityCache()
    cache.put("platform", "player")
    monkeypatch.setattr(platform_utils, "player_identity_cache", cache)
    async with db.safe_session() as session:
        session.add(Player(id="player", uid=1, nickname="玩家", gold=100))

    statements = []
    engine = factory.kw["bind"].sync_engine

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    async with db.safe_session() as writer:
        player = await lock_row(writer, Player, "player")
        player.gold -= 10
        await writer.flush()
        sql_event.listen(engine, "before_cursor_execute", record)
        try:
            for module, matcher_name, state_name in LISTENERS:
                monkeypatch.setattr(module, state_name, {"someone-else": selection_state()})
                await asyncio.wait_for(getattr(module, matcher_name).handlers[0].call(make_event("1")), timeout=2)
        finally:
            sql_event.remove(engine, "before_cursor_execute", record)
    assert statements
    assert all(stmt.lstrip().upper().startswith("SELECT") and "FOR UPDATE" not in stmt.upper()
               for stmt in statements)
    async with db.safe_session() as session:
        player = await session.get(Player, "player")
        assert player.gold == 90 and player.version_id == 2
        assert player.last_active_at is None and player.last_group_openid is None
        assert player.last_group_member_id is None and player.last_group_username is None


async def test_mysql_read_only_identity_preserves_account_resolution_and_normal_writes(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    cache = PlayerIdentityCache()
    monkeypatch.setattr(platform_utils, "player_identity_cache", cache)
    switches = {}
    monkeypatch.setattr(platform_utils, "_admin_temp_switch", switches)
    async with db.safe_session(factory) as session:
        session.add_all([Player(id="active", uid=1, nickname="主号"),
                         Player(id="inactive", uid=2, nickname="小号"),
                         Player(id="legacy", uid=3, nickname="旧号")])
        await session.flush()
        session.add_all([AccountOwnership(owner_platform_id="platform", player_id="active", is_active=True),
                         AccountOwnership(owner_platform_id="platform", player_id="inactive", is_active=False)])

    for path in ("ownership", "cache", "admin", "legacy"):
        cache.invalidate("platform")
        switches.clear()
        if path == "cache":
            cache.put("platform", "active")
        if path == "admin":
            switches["platform"] = "inactive"
        user_id = "legacy" if path == "legacy" else "platform"
        expected = {"admin": "inactive", "legacy": "legacy"}.get(path, "active")
        async with db.safe_session(factory) as session:
            player = await platform_utils.get_unified_player(session, make_event("1", user_id), read_only=True)
            assert player.id == expected
            assert not session.dirty and not session.new
            assert player.version_id == 1 and player.last_active_at is None
        if path != "cache":
            assert not cache.has(user_id)

    switches.clear()
    async with db.safe_session(factory) as session:
        assert not (await session.execute(select(PlatformServerBinding))).scalars().all()
        player = await platform_utils.get_unified_player(session, make_event("修炼"))
        assert player.id == "active" and player.last_active_at is not None
        assert player.last_group_openid == "new-group"
    async with db.safe_session(factory) as session:
        binding = (await session.execute(select(PlatformServerBinding))).scalar_one()
        assert binding.owner_platform_id == "platform" and binding.server_id == 1
        assert (await session.get(Player, "active")).version_id == 2
        binding.server_id = 2
    cache.invalidate("platform")
    async with db.safe_session(factory) as session:
        assert await platform_utils.get_unified_player(session, make_event("1"), read_only=True) is None
