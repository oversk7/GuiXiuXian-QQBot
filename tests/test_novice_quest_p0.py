"""P0 新手任务链回归测试。"""
import asyncio
from types import SimpleNamespace


def asyncio_run(coro):
    return asyncio.run(coro)


class _EmptyResult:
    def scalar_one_or_none(self):
        return None


class _CaptureSession:
    def __init__(self):
        self.added = []

    async def execute(self, _statement):
        return _EmptyResult()

    def add(self, value):
        self.added.append(value)


class _QuestResult:
    def __init__(self, quest):
        self.quest = quest

    def scalar_one_or_none(self):
        return self.quest


class _QuestSession:
    def __init__(self, quest):
        self.quest = quest
        self.added = []

    async def execute(self, _statement):
        return _QuestResult(self.quest)

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        return None


def test_novice_task_persists_enum_values_as_strings():
    from plugins.xiuxian_game.models.daily_task import TaskStatus, TaskType
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

    session = _CaptureSession()
    player = SimpleNamespace(id="player-1", level=1)

    assert asyncio_run(NoviceQuestService._init_chain(session, player, "novice_basic")) is True
    task = session.added[0]
    assert task.task_type == TaskType.TUTORIAL.value
    assert task.status == TaskStatus.ACCEPTED.value


def test_novice_attribute_point_reward_updates_player_attribute_points():
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

    session = _CaptureSession()
    player = SimpleNamespace(id="player-1", exp=0, attribute_points=5)

    reward = asyncio_run(
        NoviceQuestService._give_rewards(
            session, player, {"attribute_points": 10}
        )
    )

    assert player.attribute_points == 15
    assert "属性点+10" in reward
    assert session.added == [player]


def test_navigation_command_keeps_legacy_alias():
    from nonebot.rule import CommandRule
    from plugins.xiuxian_game.world.navigation import nav_cmd

    commands = {
        command
        for checker in nav_cmd.rule.checkers
        if isinstance(checker.call, CommandRule)
        for command in checker.call.cmds
    }
    assert ("前往",) in commands



def test_navigation_alias_completes_go_to_task():
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

    step = {
        "completion_type": "command",
        "completion_target": "前往",
    }
    assert NoviceQuestService._check_completion(
        step, "command", {"command": "导航"}, SimpleNamespace()
    ) is True
    assert NoviceQuestService._check_completion(
        step, "command", {"command": "前往"}, SimpleNamespace()
    ) is True


def test_counted_task_requires_configured_number_of_actions():
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

    step = {
        "completion_type": "command_count",
        "completion_target": "修炼",
        "completion_count": 3,
    }
    player = SimpleNamespace()
    assert NoviceQuestService._check_completion(
        step, "command", {"command": "修炼", "progress": 1}, player
    ) is False
    assert NoviceQuestService._check_completion(
        step, "command", {"command": "修炼", "progress": 3}, player
    ) is True



def test_counted_task_advances_only_on_third_matching_action(monkeypatch):
    from plugins.xiuxian_game.models.daily_task import DailyTask, TaskStatus
    from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService

    quest = DailyTask(
        player_id="player-1",
        task_type="tutorial",
        title="汲取深渊之力",
        description="修炼三次",
        target_x=0,
        target_y=0,
        enemy_name="",
        enemy_level=0,
        enemy_hp=0,
        enemy_attack=0,
        enemy_defense=0,
        enemy_agility=0,
        status=TaskStatus.ACCEPTED.value,
        quest_chain_id="novice_basic",
        quest_step=4,
        quest_progress=0,
        is_tutorial=True,
    )
    session = _QuestSession(quest)
    player = SimpleNamespace(id="player-1", level=1, exp=0, gold=0, attribute_points=0)

    async def fake_give_rewards(_session, _player, _rewards):
        return ""

    monkeypatch.setattr(
        NoviceQuestService, "_give_rewards", staticmethod(fake_give_rewards)
    )

    assert asyncio_run(
        NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "修炼"}
        )
    )[0] is False
    assert quest.quest_progress == 1
    assert quest.status == TaskStatus.ACCEPTED.value

    assert asyncio_run(
        NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "修炼"}
        )
    )[0] is False
    assert quest.quest_progress == 2

    completed, _ = asyncio_run(
        NoviceQuestService.check_and_advance_quest(
            session, player, "command", {"command": "修炼"}
        )
    )
    assert completed is True
    assert quest.status == TaskStatus.COMPLETED.value
    assert len(session.added) == 1
