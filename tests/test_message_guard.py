"""统一频控与事件去重的回归测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import nonebot.message as message_dispatch
from nonebot.adapters.qq import Bot, GroupAtMessageCreateEvent
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher

from plugins.xiuxian_game import command_guard, message_guard
from plugins.xiuxian_game.rate_limiter import SlidingWindowRateLimiter


def _qq_event(index=0, text="面板"):
    return GroupAtMessageCreateEvent.model_validate({
        "id": f"message-12345678-{index}",
        "event_id": f"GROUP_AT_MESSAGE_CREATE:callback-{index}",
        "content": text,
        "timestamp": "2026-01-01T00:00:00Z",
        "author": {"id": "openid", "member_openid": "openid", "bot": False, "member_role": "member"},
        "group_openid": "group-1",
        "group_id": "group-1",
    })


def _qq_bot():
    adapter = MagicMock()
    adapter.get_name.return_value = "QQ"
    return Bot(adapter=adapter, self_id="bot-test", bot_info=MagicMock())


@pytest.fixture(autouse=True)
def reset_guard(monkeypatch):
    monkeypatch.setattr(message_guard, "_event_id_cache", {})
    monkeypatch.setattr(message_guard, "_event_id_queue", message_guard.deque())


async def test_duplicate_callback_is_ignored(monkeypatch):
    monkeypatch.setattr(message_guard.time, "monotonic", lambda: 100.0)
    event = SimpleNamespace(id="GROUP_AT_MESSAGE_CREATE:callback-1")

    await message_guard._event_id_dedup(None, event, {})
    with pytest.raises(IgnoredException, match="duplicate outer id"):
        await message_guard._event_id_dedup(None, event, {})


async def test_callback_can_be_processed_after_dedup_ttl(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(message_guard.time, "monotonic", lambda: clock[0])
    event = SimpleNamespace(id="GROUP_AT_MESSAGE_CREATE:callback-1")

    await message_guard._event_id_dedup(None, event, {})
    clock[0] += message_guard._EVENT_ID_TTL_SECONDS
    await message_guard._event_id_dedup(None, event, {})


async def test_events_without_outer_id_are_allowed():
    event = SimpleNamespace(id="short")
    await message_guard._event_id_dedup(None, event, {})
    await message_guard._event_id_dedup(None, event, {})


async def test_repeated_text_with_distinct_callback_ids_is_allowed():
    for index in range(8):
        event = SimpleNamespace(
            event_id=f"GROUP_AT_MESSAGE_CREATE:callback-{index}",
            get_plaintext=lambda: "探索",
            get_user_id=lambda: "openid",
        )
        await message_guard._event_id_dedup(None, event, {})


def test_adapter_event_id_takes_precedence_over_message_id():
    event = SimpleNamespace(event_id="callback-12345678", id="message-12345678")
    assert message_guard._extract_outer_event_id(event) == "callback-12345678"


async def test_one_callback_reaches_multiple_matchers_once(monkeypatch):
    handled = []

    async def log_message():
        handled.append("log")

    async def handle_command():
        handled.append("command")

    logger_matcher = Matcher.new(type_="message", handlers=[log_message], priority=1)
    command_matcher = Matcher.new(type_="message", handlers=[handle_command], priority=5)
    monkeypatch.setattr(message_dispatch, "matchers", {1: [logger_matcher], 5: [command_matcher]})
    monkeypatch.setattr(message_dispatch, "_event_preprocessors", {
        proc for proc in message_dispatch._event_preprocessors
        if proc.call is message_guard._event_id_dedup
    })
    monkeypatch.setattr(message_dispatch, "_run_preprocessors", {
        proc for proc in message_dispatch._run_preprocessors
        if proc.call is message_guard._event_id_dedup
    })
    monkeypatch.setattr(message_dispatch, "_run_postprocessors", set())
    event = _qq_event()
    bot = _qq_bot()
    try:
        await message_dispatch.handle_event(bot, event)
        assert handled == ["log", "command"]
        await message_dispatch.handle_event(bot, event)
        assert handled == ["log", "command"]
    finally:
        logger_matcher.destroy()
        command_matcher.destroy()


async def test_registered_guard_limits_real_movement_dispatch(monkeypatch):
    from plugins.xiuxian_game.world.dungeon_battle import move_cmd

    handled = []

    async def handle_move():
        handled.append("move")

    stub = Matcher.new(type_="message", handlers=[handle_move])
    monkeypatch.setattr(move_cmd, "handlers", stub.handlers)
    monkeypatch.setattr(message_dispatch, "matchers", {5: [move_cmd]})
    guard_modules = {message_guard.__name__, command_guard.__name__}
    monkeypatch.setattr(message_dispatch, "_event_preprocessors", {
        proc for proc in message_dispatch._event_preprocessors
        if proc.call.__module__ in guard_modules
    })
    monkeypatch.setattr(message_dispatch, "_run_preprocessors", {
        proc for proc in message_dispatch._run_preprocessors
        if proc.call.__module__ in guard_modules
    })
    monkeypatch.setattr(message_dispatch, "_run_postprocessors", set())
    monkeypatch.setattr(command_guard, "_command_limiter", SlidingWindowRateLimiter(lambda: 0.0))
    monkeypatch.setattr(command_guard, "_notice_limiter", SlidingWindowRateLimiter(lambda: 0.0))
    send = AsyncMock()
    monkeypatch.setattr(Bot, "send", send)
    bot = _qq_bot()
    try:
        for index in range(8):
            await message_dispatch.handle_event(bot, _qq_event(index, "上"))
        assert handled == ["move"] * 8
        await message_dispatch.handle_event(bot, _qq_event(0, "上"))
        await message_dispatch.handle_event(bot, _qq_event(8, "上"))
        await message_dispatch.handle_event(bot, _qq_event(9, "上"))
        assert handled == ["move"] * 8
        assert send.await_count == 1
    finally:
        stub.destroy()
