"""游戏命令共用入口频控，聊天与重复回调不消耗额度。"""

import asyncio
from types import SimpleNamespace

import pytest
from nonebot.adapters.qq import Message
from nonebot.consts import (
    CMD_ARG_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    PREFIX_KEY,
    RAW_CMD_KEY,
)
from nonebot.exception import IgnoredException
from nonebot.rule import CommandRule, RegexRule, Rule

from plugins.xiuxian_game import command_guard, message_guard
from plugins.xiuxian_game.rate_limiter import SlidingWindowRateLimiter


class FakeEvent:
    __type__ = "GROUP_AT_MESSAGE_CREATE"
    to_me = True

    def __init__(self, user_id="openid", group_id="group-1"):
        self.user_id = user_id
        self.group_id = group_id

    def get_user_id(self):
        return self.user_id


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send(self, event, message):
        self.sent.append((event, message))
        await asyncio.sleep(0)


def _matcher(command="面板", *, game=True, rule=None, block=True):
    return SimpleNamespace(
        rule=rule if rule is not None else Rule(CommandRule([(command,)])),
        block=block,
        plugin_name=None,
        module_name="plugins.xiuxian_game.player" if game else "plugins.other",
    )


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(command_guard, "_command_limiter", SlidingWindowRateLimiter(lambda: now[0]))
    monkeypatch.setattr(command_guard, "_notice_limiter", SlidingWindowRateLimiter(lambda: now[0]))
    return now


async def test_commands_aliases_and_groups_share_budget(clock):
    bot = FakeBot()
    commands = ["面板", "背包", "探索", "帮助", "抽签", "求签", "每日一言", "今天吃什么"]
    for index, command in enumerate(commands):
        await command_guard.enforce_command_guard(
            _matcher(command), bot, FakeEvent(group_id=f"group-{index}"), {}
        )

    with pytest.raises(IgnoredException):
        await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent(), {})
    assert len(bot.sent) == 1
    assert "每 5 秒最多处理 **8** 条游戏指令" in bot.sent[0][1].data["markdown"].content

    await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent("other-openid"), {})
    clock[0] = 5.0
    await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent(), {})


async def test_notice_cooldown_is_independent_of_command_window(clock):
    bot = FakeBot()
    event = FakeEvent()
    for now, expected_notices in [(0.0, 1), (5.0, 1), (10.0, 2)]:
        clock[0] = now
        for _ in range(8):
            await command_guard.enforce_command_guard(_matcher(), bot, event, {})
        for _ in range(3):
            with pytest.raises(IgnoredException):
                await command_guard.enforce_command_guard(_matcher(), bot, event, {})
        assert len(bot.sent) == expected_notices


async def test_bare_chat_does_not_consume_budget():
    bot = FakeBot()
    event = FakeEvent()
    event.__type__ = "GROUP_MESSAGE_CREATE"
    event.to_me = False
    state = {
        PREFIX_KEY: {
            RAW_CMD_KEY: "面板",
            CMD_START_KEY: "",
            CMD_ARG_KEY: Message("好难"),
            CMD_WHITESPACE_KEY: None,
        }
    }
    for _ in range(10):
        with pytest.raises(IgnoredException):
            await command_guard.enforce_command_guard(_matcher(), bot, event, state)
    for _ in range(8):
        await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent(), {})
    assert bot.sent == []


async def test_regex_movement_uses_same_budget_as_commands():
    bot = FakeBot()
    event = FakeEvent()
    for _ in range(8):
        await command_guard.enforce_command_guard(_matcher(), bot, event, {})
    movement = _matcher(rule=Rule(RegexRule(r"^\s*(上|下|左|右)\s*$")))
    with pytest.raises(IgnoredException):
        await command_guard.enforce_command_guard(movement, bot, event, {})


async def test_other_plugins_and_chat_listeners_do_not_consume_budget():
    bot = FakeBot()
    event = FakeEvent()
    for matcher in [
        _matcher(game=False),
        _matcher(rule=Rule(), block=False),
        _matcher(rule=Rule(RegexRule(r".*")), block=False),
    ]:
        for _ in range(10):
            await command_guard.enforce_command_guard(matcher, bot, event, {})
    for _ in range(8):
        await command_guard.enforce_command_guard(_matcher(), bot, event, {})
    assert bot.sent == []


async def test_multiple_matchers_count_once_and_share_rejection():
    bot = FakeBot()
    event = FakeEvent()
    for _ in range(8):
        state = {}
        await command_guard.prepare_command_guard(state)
        await asyncio.gather(
            command_guard.enforce_command_guard(_matcher(), bot, event, state.copy()),
            command_guard.enforce_command_guard(_matcher("背包"), bot, event, state.copy()),
        )
    assert bot.sent == []

    state = {}
    await command_guard.prepare_command_guard(state)
    results = await asyncio.gather(
        command_guard.enforce_command_guard(_matcher(), bot, event, state.copy()),
        command_guard.enforce_command_guard(_matcher("背包"), bot, event, state.copy()),
        return_exceptions=True,
    )
    assert all(isinstance(result, IgnoredException) for result in results)
    assert len(bot.sent) == 1


async def test_rejected_command_does_not_reach_story_fallback():
    bot = FakeBot()
    event = FakeEvent()
    for _ in range(8):
        await command_guard.enforce_command_guard(_matcher(), bot, event, {})
    state = {}
    await command_guard.prepare_command_guard(state)
    with pytest.raises(IgnoredException):
        await command_guard.enforce_command_guard(_matcher(), bot, event, state.copy())
    story_listener = _matcher(rule=Rule(RegexRule(r".*")), block=False)
    with pytest.raises(IgnoredException):
        await command_guard.enforce_command_guard(story_listener, bot, event, state.copy())
    assert len(bot.sent) == 1


async def test_duplicate_callback_does_not_consume_budget(monkeypatch):
    monkeypatch.setattr(message_guard, "_event_id_cache", {})
    monkeypatch.setattr(message_guard, "_event_id_queue", message_guard.deque())
    bot = FakeBot()
    event = FakeEvent()
    event.event_id = "GROUP_AT_MESSAGE_CREATE:command-guard-duplicate"
    await message_guard._event_id_dedup(bot, event, {})
    await command_guard.enforce_command_guard(_matcher(), bot, event, {})
    with pytest.raises(IgnoredException):
        await message_guard._event_id_dedup(bot, event, {})

    for _ in range(7):
        await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent(), {})
    with pytest.raises(IgnoredException):
        await command_guard.enforce_command_guard(_matcher(), bot, FakeEvent(), {})
