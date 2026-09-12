"""每日委托与新手教程隔离；所有数据库操作仅使用独立 SQLite 内存库。"""

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.exception import FinishedException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.daily_task import commands
from plugins.xiuxian_game import platform_utils
from plugins.xiuxian_game.daily_task.service import DailyTaskService
from plugins.xiuxian_game.infrastructure.repositories.daily_task_repository import DailyTaskRepository
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.daily_task import DailyTask, TaskStatus, TaskType
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService


@pytest.fixture
async def task_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    monkeypatch.setattr(commands, "AsyncSessionLocal", factory)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Player.__table__.create)
            await connection.run_sync(DailyTask.__table__.create)
        async with db.safe_session(factory) as session:
            session.add_all([
                Player(id="tutorial-s1", uid=99001, nickname="一区新人", server_id=1),
                Player(id="tutorial-s2", uid=99002, nickname="二区新人", server_id=2),
            ])
        yield factory
    finally:
        await engine.dispose()


def make_task(player_id, task_date, status, tutorial=False):
    return DailyTask(
        player_id=player_id,
        task_type=TaskType.TUTORIAL.value if tutorial else TaskType.GHOST_ELIMINATION.value,
        title="新手教程" if tutorial else "普通委托",
        description="测试任务",
        target_region="大都会",
        target_x=0,
        target_y=0,
        enemy_name="测试鬼怪",
        enemy_level=1,
        enemy_hp=10,
        enemy_attack=1,
        enemy_defense=1,
        enemy_agility=1,
        exp_reward=10,
        gold_reward=0,
        guild_points_reward=0,
        task_date=task_date,
        status=status.value,
        is_tutorial=tutorial,
        quest_chain_id="novice_basic" if tutorial else None,
        quest_step=9 if tutorial else None,
    )


async def test_cleanup_keeps_yesterday_tutorials_in_both_servers(task_db):
    today = date.today()
    yesterday = today - timedelta(days=1)
    async with db.safe_session(task_db) as session:
        tutorials = [
            make_task(player_id, yesterday, status, tutorial=True)
            for player_id in ("tutorial-s1", "tutorial-s2")
            for status in (TaskStatus.AVAILABLE, TaskStatus.ACCEPTED)
        ]
        ordinary = [
            make_task(player_id, yesterday, status)
            for player_id in ("tutorial-s1", "tutorial-s2")
            for status in (TaskStatus.AVAILABLE, TaskStatus.ACCEPTED)
        ]
        today_task = make_task("tutorial-s1", today, TaskStatus.ACCEPTED)
        completed = make_task("tutorial-s1", yesterday, TaskStatus.COMPLETED)
        session.add_all(tutorials + ordinary + [today_task, completed])
        await session.flush()
        repo = DailyTaskRepository(session)
        service = DailyTaskService(repo, None, None)

        assert {task.id for task in await repo.find_expired_tasks(today)} == {
            task.id for task in ordinary
        }
        assert await service.check_and_cleanup_expired_tasks() == 4
        expected = {
            task.id: task.status for task in tutorials + ordinary + [today_task, completed]
        }
        assert all(task.status == TaskStatus.EXPIRED.value for task in ordinary)
        assert [task.status for task in tutorials] == ["available", "accepted"] * 2
        assert today_task.status == TaskStatus.ACCEPTED.value
        assert completed.status == TaskStatus.COMPLETED.value

    async with db.safe_session(task_db) as session:
        tasks = (await session.execute(select(DailyTask))).scalars().all()
        assert {task.id: task.status for task in tasks} == expected


async def test_daily_lists_counts_and_summary_exclude_tutorials(task_db):
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    async with db.safe_session(task_db) as session:
        ordinary = make_task("tutorial-s1", today, TaskStatus.COMPLETED)
        older = make_task("tutorial-s1", week_start - timedelta(days=1), TaskStatus.COMPLETED)
        session.add_all([ordinary, older])
        await session.flush()
        session.add_all([
            make_task("tutorial-s1", today, TaskStatus.ACCEPTED, tutorial=True),
            make_task("tutorial-s1", today, TaskStatus.COMPLETED, tutorial=True),
            make_task("tutorial-s2", today, TaskStatus.COMPLETED, tutorial=True),
        ])
        await session.flush()
        repo = DailyTaskRepository(session)
        service = DailyTaskService(repo, None, None)

        assert await repo.find_by_player_and_date("tutorial-s1", today) is ordinary
        assert await service.get_player_daily_tasks("tutorial-s1", today) == [ordinary]
        assert await service.get_player_daily_task("tutorial-s2", today) is None
        assert await service.get_player_daily_tasks("tutorial-s2", today) == []
        assert await repo.count() == 2
        assert await repo.count_weekly_completed("tutorial-s1", week_start) == 1
        assert await repo.count_total_completed("tutorial-s1") == 2
        assert await repo.count_total_completed("tutorial-s2") == 0
        assert await service.get_task_summary("tutorial-s1") == {
            "today_task": ordinary,
            "weekly_completed": 1,
            "total_completed": 2,
        }


@pytest.mark.parametrize("status", [TaskStatus.AVAILABLE, TaskStatus.ACCEPTED])
async def test_daily_repository_cannot_resolve_tutorial_by_id(task_db, status):
    async with db.safe_session(task_db) as session:
        tutorial = make_task("tutorial-s1", date.today(), status, tutorial=True)
        ordinary = make_task("tutorial-s1", date.today(), status)
        session.add_all([tutorial, ordinary])
        await session.flush()
        repo = DailyTaskRepository(session)

        assert await repo.find_by_id(tutorial.id) is None
        assert await repo.get_by_id(tutorial.id) is None
        assert not await repo.exists(tutorial.id)
        assert not await repo.delete(tutorial.id)
        assert await repo.find_by_id(ordinary.id) is ordinary
        assert await repo.get_by_id(ordinary.id) is ordinary
        assert await repo.exists(ordinary.id)
        assert tutorial.status == status.value


@pytest.mark.parametrize("action", ["accept", "complete"])
async def test_daily_commands_cannot_accept_or_complete_tutorial(task_db, monkeypatch, action):
    status = TaskStatus.AVAILABLE if action == "accept" else TaskStatus.ACCEPTED
    async with db.safe_session(task_db) as session:
        tutorial = make_task("tutorial-s1", date.today(), status, tutorial=True)
        session.add(tutorial)
        await session.flush()
        tutorial_id = tutorial.id
    player = SimpleNamespace(id="tutorial-s1", level=30, guild_id=None, x=0, y=0)
    monkeypatch.setattr(commands, "require_player", AsyncMock(return_value=player))
    monkeypatch.setattr(platform_utils, "require_player", AsyncMock(return_value=player))
    accept = AsyncMock()
    complete = AsyncMock()
    monkeypatch.setattr(DailyTaskService, "accept_task", accept)
    monkeypatch.setattr(DailyTaskService, "complete_task", complete)
    monkeypatch.setattr(DailyTaskService, "force_generate_new_task", AsyncMock(return_value=None))
    matcher = commands.accept_task_cmd if action == "accept" else commands.complete_task_cmd
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(matcher, "finish", finish)

    with pytest.raises(FinishedException):
        if action == "accept":
            await commands.handle_accept_task(SimpleNamespace(), Message(str(tutorial_id)))
        else:
            await commands.handle_complete_task(SimpleNamespace())

    accept.assert_not_awaited()
    complete.assert_not_awaited()
    expected_message = "不存在" if action == "accept" else "没有已接取的任务"
    assert expected_message in str(finish.call_args.args[0])
    async with db.safe_session(task_db) as session:
        assert (await session.get(DailyTask, tutorial_id)).status == status.value


@pytest.mark.parametrize("quest_completed", [False, True])
async def test_under_level_30_preview_advances_tutorial_and_shows_message(
    task_db, monkeypatch, quest_completed
):
    async with db.safe_session(task_db) as session:
        session.add(make_task("tutorial-s1", date.today(), TaskStatus.ACCEPTED, tutorial=True))

    async def require_player(session, event, matcher):
        return await session.get(Player, "tutorial-s1")

    async def advance(session, player, event_type, event_data):
        assert player.level < 30
        assert event_type == "command"
        assert event_data == {"command": "任务"}
        tutorial = (await session.execute(select(DailyTask))).scalar_one()
        assert tutorial.quest_step == 9
        if quest_completed:
            tutorial.complete_task()
        return quest_completed, "第九步教程反馈"

    monkeypatch.setattr(commands, "require_player", require_player)
    advance_mock = AsyncMock(side_effect=advance)
    monkeypatch.setattr(NoviceQuestService, "check_and_advance_quest", advance_mock)
    generate = AsyncMock()
    monkeypatch.setattr(DailyTaskService, "generate_daily_task", generate)
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(commands.daily_task_cmd, "finish", finish)
    monkeypatch.setattr(commands, "build_markdown", lambda text: text)

    with pytest.raises(FinishedException):
        await commands.handle_daily_task(SimpleNamespace())

    advance_mock.assert_awaited_once()
    generate.assert_not_awaited()
    message = finish.call_args.args[0]
    assert "每日委托预览" in message
    assert "Lv.30" in message
    assert "第九步教程反馈" in message
    async with db.safe_session(task_db) as session:
        tasks = (await session.execute(select(DailyTask))).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].is_tutorial
        assert tasks[0].status == ("completed" if quest_completed else "accepted")


@pytest.mark.parametrize("action", ["accept", "refresh"])
async def test_under_level_30_cannot_accept_or_refresh(task_db, monkeypatch, action):
    player = SimpleNamespace(level=29)
    monkeypatch.setattr(commands, "require_player", AsyncMock(return_value=player))
    monkeypatch.setattr(platform_utils, "require_player", AsyncMock(return_value=player))
    generate = AsyncMock()
    accept = AsyncMock()
    monkeypatch.setattr(DailyTaskService, "force_generate_new_task", generate)
    monkeypatch.setattr(DailyTaskService, "accept_task", accept)
    matcher = commands.accept_task_cmd if action == "accept" else commands.refresh_task_cmd
    finish = AsyncMock(side_effect=FinishedException)
    monkeypatch.setattr(matcher, "finish", finish)

    with pytest.raises(FinishedException):
        if action == "accept":
            await commands.handle_accept_task(SimpleNamespace(), Message("1"))
        else:
            await commands.handle_refresh_task(SimpleNamespace())

    assert "Lv.30" in str(finish.call_args.args[0])
    generate.assert_not_awaited()
    accept.assert_not_awaited()
