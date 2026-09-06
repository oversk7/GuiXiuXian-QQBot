from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.adapters.qq.exception import NetworkError
from nonebot.exception import FinishedException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game import group_welcome
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.group_welcome_setting import GroupWelcomeSetting


@pytest.fixture
async def welcome_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(GroupWelcomeSetting.__table__.create)
    monkeypatch.setattr(db, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    try:
        yield
    finally:
        await engine.dispose()


@pytest.fixture
def finish(monkeypatch):
    mock = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(group_welcome.group_welcome_cmd, "finish", mock)
    return mock


async def run_setting(group_id, action, role="admin"):
    event = SimpleNamespace(group_openid=group_id, author=SimpleNamespace(member_role=role))
    with pytest.raises(FinishedException):
        await group_welcome.handle_group_welcome_setting(event, Message(action))


def assert_toggle_button(message, action):
    assert message[-1].type == "keyboard"
    keyboard = message[-1].data["keyboard"]
    assert len(keyboard.content.rows) == 1
    assert len(keyboard.content.rows[0].buttons) == 1
    button = keyboard.content.rows[0].buttons[0]
    assert button.render_data.label == f"{action}进群欢迎"
    assert button.action.type == 2
    assert button.action.permission.type == 1
    assert button.action.enter is True
    assert button.action.data == f"进群欢迎 {action}"


async def test_default_enabled_without_creating_setting(welcome_db, finish, monkeypatch):
    await run_setting("group-a", "", role="member")
    assert "已开启" in str(finish.call_args.args[0])
    assert "进群欢迎 开启" not in str(finish.call_args.args[0])
    assert "进群欢迎 关闭" not in str(finish.call_args.args[0])
    assert not any(segment.type == "keyboard" for segment in finish.call_args.args[0])
    async with db.safe_session() as session:
        assert await session.get(GroupWelcomeSetting, "group-a") is None

    send = AsyncMock()
    monkeypatch.setattr(group_welcome.group_welcome, "send", send)
    await group_welcome.handle_group_welcome(
        SimpleNamespace(self_id="bot"),
        SimpleNamespace(group_openid="group-a", member_openid="member"),
    )
    send.assert_awaited_once()
    assert_toggle_button(send.call_args.args[0], "关闭")


@pytest.mark.parametrize("role", ["admin", "owner"])
async def test_toggle_persists_and_isolates_groups(welcome_db, finish, monkeypatch, role):
    await run_setting("group-a", "关闭", role=role)
    assert "已关闭" in str(finish.call_args.args[0])
    assert_toggle_button(finish.call_args.args[0], "开启")
    async with db.safe_session() as session:
        assert (await session.get(GroupWelcomeSetting, "group-a")).enabled is False

    await run_setting("group-a", "")
    assert "已关闭" in str(finish.call_args.args[0])
    await run_setting("group-b", "")
    assert "已开启" in str(finish.call_args.args[0])

    send = AsyncMock()
    monkeypatch.setattr(group_welcome.group_welcome, "send", send)
    bot = SimpleNamespace(self_id="bot")
    event = SimpleNamespace(group_openid="group-a", member_openid="member")
    await group_welcome.handle_group_welcome(bot, event)
    send.assert_not_awaited()
    await group_welcome.handle_group_welcome(
        bot, SimpleNamespace(group_openid="group-b", member_openid="member")
    )
    send.assert_awaited_once()
    send.reset_mock()

    await run_setting("group-a", "开启", role=role)
    assert_toggle_button(finish.call_args.args[0], "关闭")
    async with db.safe_session() as session:
        assert (await session.get(GroupWelcomeSetting, "group-a")).enabled is True
    await group_welcome.handle_group_welcome(bot, event)
    send.assert_awaited_once()


async def test_repeated_disable_is_idempotent(welcome_db, finish):
    await run_setting("group-a", "关闭")
    await run_setting("group-a", "关闭")
    async with db.safe_session() as session:
        assert (await session.get(GroupWelcomeSetting, "group-a")).enabled is False


@pytest.mark.parametrize("group_id, action, expected", [
    (None, "关闭", "QQ群内"),
    ("group-a", "随便", "查看状态"),
])
async def test_rejects_invalid_context_or_argument(monkeypatch, finish, group_id, action, expected):
    session = AsyncMock()
    monkeypatch.setattr(group_welcome, "safe_session", session)
    await run_setting(group_id, action)
    assert expected in str(finish.call_args.args[0])
    session.assert_not_called()


@pytest.mark.parametrize("role", ["member", None, "unknown"])
@pytest.mark.parametrize("action", ["开启", "关闭"])
async def test_only_current_group_managers_can_change(monkeypatch, finish, role, action):
    session = AsyncMock()
    monkeypatch.setattr(group_welcome, "safe_session", session)
    await run_setting("group-a", action, role=role)
    assert "只有本群群主或管理员" in str(finish.call_args.args[0])
    session.assert_not_called()


async def test_missing_author_cannot_change(monkeypatch, finish):
    session = AsyncMock()
    monkeypatch.setattr(group_welcome, "safe_session", session)
    with pytest.raises(FinishedException):
        await group_welcome.handle_group_welcome_setting(
            SimpleNamespace(group_openid="group-a"), Message("关闭")
        )
    assert "只有本群群主或管理员" in str(finish.call_args.args[0])
    session.assert_not_called()


async def test_markdown_failure_falls_back_to_text(welcome_db, monkeypatch):
    send = AsyncMock(side_effect=[NetworkError("failed"), None])
    monkeypatch.setattr(group_welcome.group_welcome, "send", send)
    await group_welcome.handle_group_welcome(
        SimpleNamespace(self_id="bot"),
        SimpleNamespace(group_openid="group-a", member_openid="member"),
    )
    assert send.await_count == 2
    assert isinstance(send.call_args.args[0], str)
    assert "欢迎" in send.call_args.args[0]


async def test_control_flow_exception_is_not_swallowed(welcome_db, monkeypatch):
    send = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(group_welcome.group_welcome, "send", send)
    with pytest.raises(FinishedException):
        await group_welcome.handle_group_welcome(
            SimpleNamespace(self_id="bot"),
            SimpleNamespace(group_openid="group-a", member_openid="member"),
        )
    send.assert_awaited_once()


def test_setting_and_help_commands_registered():
    from nonebot.rule import CommandRule
    from nonebot.matcher import matchers

    commands = {
        command
        for priority_matchers in matchers.values()
        for matcher in priority_matchers
        for checker in matcher.rule.checkers
        if isinstance(checker.call, CommandRule)
        for command in checker.call.cmds
    }
    assert ("进群欢迎",) in commands
    assert ("进群欢迎帮助",) in commands
