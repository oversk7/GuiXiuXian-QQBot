"""序章续接、注册事务和新手按钮协议；数据库仅使用临时 SQLite。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nonebot.exception import FinishedException
from nonebot.adapters.qq.models.common import Action, Permission
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.account_ownership import AccountOwnership
from plugins.xiuxian_game.models.player import Gender, Player
from plugins.xiuxian_game.player import info, prologue
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService
from plugins.xiuxian_game.utils_markdown import build_markdown, keyboard


def actions(message):
    return [
        button.action
        for segment in message
        if segment.type == "keyboard"
        for row in segment.data["keyboard"].content.rows
        for button in row.buttons
    ]


def content(message):
    return "\n".join(
        segment.data["markdown"].content
        for segment in message
        if segment.type == "markdown"
    )


class CaptureMatcher:
    async def finish(self, message):
        self.message = message
        raise FinishedException


@pytest.fixture
async def onboarding_store(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'onboarding.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: db.Base.metadata.create_all(conn, tables=[
                Player.__table__, AccountOwnership.__table__,
            ]))
        monkeypatch.setattr(db, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
        yield
    finally:
        await engine.dispose()


@pytest.fixture
async def prologue_player(onboarding_store, monkeypatch):
    async with db.safe_session() as session:
        session.add(Player(
            id="prologue-player", uid=100, nickname="醒来的角色", server_id=1,
            prologue_step=1, level=1, exp=0, gold=0, attribute_points=0,
        ))

    async def require_player(session, event, matcher):
        return await session.get(Player, "prologue-player")

    monkeypatch.setattr(prologue, "require_player", require_player)
    reward = AsyncMock()
    monkeypatch.setattr(prologue.ItemInstance, "add_item", reward)
    return reward


@pytest.mark.parametrize("server_id, expected_exp", [(1, 10), (2, 20)])
async def test_first_fight_leads_to_breakthrough_without_auto_leveling(prologue_player, server_id, expected_exp):
    async with db.safe_session() as session:
        player = await session.get(Player, "prologue-player")
        player.server_id = server_id
    matcher = CaptureMatcher()

    with pytest.raises(FinishedException):
        await prologue._finish_prologue(matcher, SimpleNamespace(), "首战\n")

    assert actions(matcher.message)[0].data == "突破"
    assert actions(matcher.message)[0].enter is True
    assert "新手任务" in [action.data for action in actions(matcher.message)]
    assert "完成首次突破" in content(matcher.message)
    async with db.safe_session() as session:
        player = await session.get(Player, "prologue-player")
        assert (player.prologue_step, player.level, player.exp, player.gold) == (2, 1, expected_exp, 500)
    prologue_player.assert_awaited_once()
    assert prologue_player.await_args.args[1:] == ("prologue-player", "bone_armor", 1)


@pytest.mark.parametrize("retry", ["反抗", "装死", "睁开眼"])
async def test_completed_prologue_retry_keeps_rewards_and_resume_entry(prologue_player, monkeypatch, retry):
    matcher = CaptureMatcher()
    with pytest.raises(FinishedException):
        await prologue._finish_prologue(matcher, SimpleNamespace(), "首战\n")
    monkeypatch.setattr(prologue, "fight_back", matcher)
    monkeypatch.setattr(prologue, "play_dead", matcher)
    monkeypatch.setattr(prologue, "open_eyes", matcher)
    handler = {
        "反抗": prologue.handle_fight_back,
        "装死": prologue.handle_play_dead,
        "睁开眼": prologue.handle_open_eyes,
    }[retry]

    with pytest.raises(FinishedException):
        await handler(SimpleNamespace())

    assert [action.data for action in actions(matcher.message)] == ["突破", "新手任务"]
    assert "经验 +" not in content(matcher.message)
    async with db.safe_session() as session:
        player = await session.get(Player, "prologue-player")
        assert (player.prologue_step, player.level, player.exp, player.gold) == (2, 1, 10, 500)
    prologue_player.assert_awaited_once()


@pytest.mark.parametrize("step, level, points, expected", [
    (0, 1, 0, "睁开眼"),
    (1, 1, 0, "反抗"),
    (2, 1, 0, "突破"),
    (2, 2, 5, "加点 力 5"),
    (2, 2, 0, "面板"),
])
def test_resume_uses_existing_player_progress(step, level, points, expected):
    player = SimpleNamespace(
        nickname="当前角色", uid=321, prologue_step=step,
        level=level, attribute_points=points,
    )
    message = prologue.build_onboarding_resume(player)

    assert actions(message)[0].data == expected
    assert actions(message)[-1].data == "新手任务"
    assert all(action.enter is True for action in actions(message))
    assert "当前角色" in content(message)
    assert "321" in content(message)
    assert player.prologue_step == step


async def test_registered_resume_resolves_current_identity(monkeypatch):
    current_player = SimpleNamespace(
        nickname="当前借用角色", uid=321, prologue_step=2,
        level=2, attribute_points=5,
    )
    resolver = AsyncMock(return_value=current_player)
    monkeypatch.setattr(info, "get_unified_player", resolver)
    session, event = object(), object()

    message = await info._resume_registered_player(session, event, "你已经拥有游戏账号了")

    resolver.assert_awaited_once_with(session, event, read_only=True)
    assert actions(message)[0].data == "加点 力 5"
    assert "当前借用角色" in content(message)
    assert "我的账号" in content(message)


@pytest.fixture
def registration_hooks(monkeypatch):
    monkeypatch.setattr(info, "_registration_lock", asyncio.Lock())
    monkeypatch.setattr(info, "ensure_platform_server_binding", AsyncMock(
        side_effect=lambda session, user_id, server_id: (True, "", server_id),
    ))
    cache_put = Mock()
    monkeypatch.setattr(info.player_identity_cache, "put", cache_put)
    return cache_put


@pytest.mark.parametrize("failure", ["false", "exception"])
async def test_registration_tutorial_failure_rolls_back(onboarding_store, registration_hooks, monkeypatch, failure):
    init = AsyncMock(return_value=False)
    if failure == "exception":
        init.side_effect = RuntimeError("教程初始化异常")
    monkeypatch.setattr(NoviceQuestService, "init_novice_quests", init)
    event = SimpleNamespace(get_user_id=lambda: "new-user")

    with pytest.raises(RuntimeError, match="初始化"):
        await info.create_player(event, "新角色", Gender.MALE, 1)

    async with db.safe_session() as session:
        assert await session.scalar(select(func.count()).select_from(Player)) == 0
        assert await session.scalar(select(func.count()).select_from(AccountOwnership)) == 0
    registration_hooks.assert_not_called()


async def test_registration_initializes_before_commit_then_caches(onboarding_store, registration_hooks, monkeypatch):
    async def initialize(session, player):
        registration_hooks.assert_not_called()
        async with db.safe_session() as observer:
            assert await observer.scalar(select(func.count()).select_from(Player)) == 0
        return True

    init = AsyncMock(side_effect=initialize)
    monkeypatch.setattr(NoviceQuestService, "init_novice_quests", init)
    event = SimpleNamespace(get_user_id=lambda: "new-user")

    message = await info.create_player(event, "新角色", Gender.MALE, 1)

    init.assert_awaited_once()
    async with db.safe_session() as session:
        player = (await session.execute(select(Player))).scalar_one()
        registration_hooks.assert_called_once_with("new-user", player.id)
    assert actions(message)[0].data == "睁开眼"
    assert all(action.enter is True for action in actions(message))


@pytest.mark.parametrize("button_enter", [False, True])
def test_keyboard_enter_is_explicit_and_preserves_default_serialization(button_enter):
    segment = keyboard([[("分配", "加点 力 ")]], button_enter=button_enter)
    action = segment.data["keyboard"].content.rows[0].buttons[0].action
    legacy = Action(
        type=2, permission=Permission(type=2), data="加点 力 ",
        unsupport_tips="请升级新版QQ后使用按钮",
    )
    expected = legacy.dict(exclude_unset=True)
    if button_enter:
        expected["enter"] = True
    assert action.dict(exclude_unset=True) == expected
    if not button_enter:
        assert action.dict() == legacy.dict()


def test_build_markdown_forwards_enter_without_changing_default():
    default = build_markdown("提示", buttons=[["加点"]])
    enabled = build_markdown("提示", buttons=[["加点"]], button_enter=True)

    assert actions(default)[0].enter is None
    assert actions(enabled)[0].enter is True
    assert content(default) == content(enabled) == "提示"
