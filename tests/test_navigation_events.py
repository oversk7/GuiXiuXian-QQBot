import ast
import importlib.util
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from nonebot.exception import FinishedException


ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
PACKAGE = "navigation_event_test"


@pytest.fixture
def modules(monkeypatch):
    for suffix, directory in (("", ROOT), (".world", ROOT / "world"), (".models", ROOT / "models")):
        package = ModuleType(PACKAGE + suffix)
        package.__path__ = [str(directory)]
        monkeypatch.setitem(sys.modules, package.__name__, package)
    player_module = ModuleType(f"{PACKAGE}.models.player")
    player_module.Player = SimpleNamespace
    inventory_module = ModuleType(f"{PACKAGE}.models.inventory")
    inventory_module.ItemInstance = SimpleNamespace(add_item=AsyncMock())
    for module in (player_module, inventory_module):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    loaded = {}
    for name in ("utils_markdown", "world.navigation_events", "notification_service"):
        spec = importlib.util.spec_from_file_location(
            f"{PACKAGE}.{name}", ROOT / (name.replace(".", "/") + ".py")
        )
        module = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, spec.name, module)
        spec.loader.exec_module(module)
        loaded[name] = module
    return SimpleNamespace(
        events=loaded["world.navigation_events"],
        markdown=loaded["utils_markdown"],
        notify=loaded["notification_service"],
    )


@pytest.fixture
def navigation(modules):
    import dataclasses

    tree = ast.parse((ROOT / "world/navigation.py").read_text(encoding="utf-8"))
    names = {
        "NavigationUpdate", "_tiles_per_second", "_euclidean_distance", "_move_towards",
        "format_navigation_interruption", "_update_nav_position",
    }
    namespace = {
        "__name__": f"{PACKAGE}.world.navigation",
        "__package__": f"{PACKAGE}.world",
        "dataclass": dataclasses.dataclass, "field": dataclasses.field,
        "datetime": datetime, "timedelta": timedelta, "Tuple": tuple,
        "Player": SimpleNamespace, "NavigationTask": SimpleNamespace,
        "NavigationEvent": modules.events.NavigationEvent,
        "generate_supernatural_encounters": modules.events.generate_supernatural_encounters,
        "apply_navigation_events": modules.events.apply_navigation_events,
        "format_navigation_events": modules.events.format_navigation_events,
        "color_text": modules.markdown.color_text,
        "build_markdown": modules.markdown.build_markdown,
    }
    nodes = [node for node in tree.body if getattr(node, "name", None) in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "navigation_core", "exec"), namespace)
    return namespace


def traveler(in_dungeon=False):
    return SimpleNamespace(
        id="traveler", nickname="旅人", level=10, hp=100, max_hp=100,
        mp=30, stamina=5, gold=500, exp=0, agility=10, dungeon_kill_streak=12,
        real_world_x=0, real_world_y=0,
        x=2 if in_dungeon else 0, y=3 if in_dungeon else 0,
        dungeon_x=2, dungeon_y=3,
        is_in_dungeon=lambda: in_dungeon,
        get_effective_attributes=AsyncMock(return_value={"agility": 10}),
    )


def task_at(now, elapsed=1000, target=200):
    return SimpleNamespace(
        player_id="traveler", target_x=target, target_y=0,
        initial_distance=float(target), last_update=now - timedelta(seconds=elapsed),
        supernatural_events_seen=0,
    )


def ghost(modules, fatal):
    rng = Mock()
    rng.random.side_effect = [0.99, 0.89 if fatal else 0.90]
    rng.randint.return_value = 100
    rng.choices.side_effect = lambda templates, **kwargs: [
        next(template for template in templates if template.get("is_supernatural"))
    ]
    return modules.events._pick_event(traveler(), rng)


@pytest.mark.parametrize("fatal", [True, False])
def test_insurance_ghost_death_boundary_and_red_lines(modules, fatal):
    event = ghost(modules, fatal)
    assert event.fatal is fatal
    assert event.is_supernatural
    assert "保险鬼" in event.description
    assert ("我要买一百年保险！哈哈哈哈哈哈哈哈哈！" in event.description) is fatal
    assert ("当场死亡" in event.description) is fatal
    assert ("继续赶路" in event.description) is not fatal
    plain = modules.events.NavigationEvent("🍀", "捡到金币", gold=100)
    rendered = modules.events.format_navigation_events([plain, event])
    assert "  🍀 捡到金币\n" in rendered
    assert rendered.count(r"\textcolor{#FF5C6C}") == len(event.description.splitlines())
    message = modules.markdown.build_markdown(rendered)
    assert message.type == "markdown"
    assert "\n" not in message.data["markdown"].content


async def test_fatal_event_stops_settlement_without_one_hp_floor(modules):
    player = traveler()
    player.hp = 1
    await modules.events.apply_navigation_events(
        AsyncMock(), player,
        [ghost(modules, True), modules.events.NavigationEvent("🍀", "金币", gold=100)],
    )
    assert player.hp == 0
    assert player.dungeon_kill_streak == 0
    assert player.gold == 500


@pytest.mark.parametrize("in_dungeon", [False, True])
@pytest.mark.parametrize("checkpoint", [30, 200])
async def test_death_stops_at_encounter_even_when_elapsed_time_reaches_destination(
    modules, navigation, in_dungeon, checkpoint,
):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    fatal = ghost(modules, True)
    navigation["generate_supernatural_encounters"] = lambda *args: [(checkpoint, fatal)]
    player = traveler(in_dungeon)
    task = task_at(now)
    session = AsyncMock()
    update = await navigation["_update_nav_position"](player, task, session)
    assert not update and update.interrupted
    assert update.events == [fatal]
    assert player.hp == 0 and player.dungeon_kill_streak == 0
    assert (player.real_world_x, player.real_world_y) == (checkpoint, 0)
    assert (player.x, player.y) == ((2, 3) if in_dungeon else (checkpoint, 0))
    assert (player.dungeon_x, player.dungeon_y) == (2, 3)
    session.delete.assert_awaited_once_with(task)


@pytest.mark.parametrize("initial_distance", [200.0, None])
async def test_survived_encounter_is_not_replayed_on_refresh(modules, navigation, initial_distance):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    survived = ghost(modules, False)
    navigation["generate_supernatural_encounters"] = lambda *args: [(30, survived)]
    player = traveler()
    task = task_at(now, elapsed=35)
    task.initial_distance = initial_distance
    session = AsyncMock()
    first = await navigation["_update_nav_position"](player, task, session)
    assert first.events == [survived] and not first.interrupted
    assert player.real_world_x == 35 and player.hp == 100
    assert task.supernatural_events_seen == 1
    navigation["datetime"] = SimpleNamespace(now=lambda: now + timedelta(seconds=10))
    second = await navigation["_update_nav_position"](player, task, session)
    assert not second.events and not second.interrupted
    assert player.real_world_x == 45
    assert task.initial_distance == 200.0
    session.delete.assert_not_awaited()


async def test_dead_player_cannot_move_and_normal_arrival_still_works(navigation):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    navigation["generate_supernatural_encounters"] = lambda *args: []
    player = traveler()
    task = task_at(now)
    session = AsyncMock()
    update = await navigation["_update_nav_position"](player, task, session)
    assert update and not update.interrupted and player.real_world_x == 200
    session.delete.assert_not_awaited()
    player.hp = 0
    player.real_world_x = 25
    update = await navigation["_update_nav_position"](player, task, session)
    assert update.interrupted and not update
    assert player.real_world_x == 25
    session.delete.assert_awaited_once_with(task)


def test_encounter_schedule_is_stable_and_arrival_pool_excludes_ghosts(modules, monkeypatch):
    monkeypatch.setattr(modules.events, "_resolve_random_material", lambda rng: ("herb", "灵草"))
    player = traveler()
    encounters = []
    for index in range(100):
        player.id = f"route-{index}"
        encounters = modules.events.generate_supernatural_encounters(player, 400, 400, 0)
        if encounters:
            break
    assert encounters
    assert encounters == modules.events.generate_supernatural_encounters(player, 400, 400, 0)
    assert all(0 <= distance <= 400 for distance, event in encounters)
    ordinary = modules.events.generate_navigation_events(player, 400, 400, 0)
    assert all(not event.is_supernatural and not event.fatal for event in ordinary)
    assert len(ordinary) + len(encounters) <= 6
    player.level = 100
    modules.events._stamina_restore_counter[player.id] = (datetime.now().date().isoformat(), 3)
    assert encounters == modules.events.generate_supernatural_encounters(player, 400, 400, 0)


@pytest.mark.parametrize("markdown", [False, True])
async def test_notifications_send_actual_markdown_only_when_requested(modules, monkeypatch, markdown):
    monkeypatch.setattr(modules.notify, "_get_notification_target", AsyncMock(return_value=("group", "旅人", "member")))
    sender = AsyncMock(return_value=True)
    monkeypatch.setattr(modules.notify, "_send_group_text", sender)
    text = modules.events.format_navigation_events([ghost(modules, True)])
    assert await modules.notify.notify_player("traveler", text, AsyncMock(), markdown=markdown)
    message = sender.call_args.args[1]
    assert message.type == ("markdown" if markdown else "text")
    if markdown:
        assert r"\textcolor{#FF5C6C}" in message.data["markdown"].content
    else:
        assert message.data["text"] == f"@旅人 {text}"


def load_handler(namespace, name=None, matcher=None, path="world/navigation.py"):
    tree = ast.parse((ROOT / path).read_text(encoding="utf-8"))
    node = next(
        node for node in tree.body if isinstance(node, ast.AsyncFunctionDef)
        and ((name and node.name == name) or (matcher and any(
            matcher in ast.unparse(decorator) for decorator in node.decorator_list
        )))
    )
    node.decorator_list = []
    node.args.defaults = []
    for arg in node.args.args:
        arg.annotation = None
    exec(compile(ast.Module(body=[node], type_ignores=[]), "navigation_handler", "exec"), namespace)
    return namespace[node.name]


async def test_navigation_command_finishes_with_red_death_instead_of_arrival(modules, navigation):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    navigation["generate_supernatural_encounters"] = lambda *args: [(30, ghost(modules, True))]
    player, task, session = traveler(), task_at(now), AsyncMock()
    session.get.return_value = task

    @asynccontextmanager
    async def scope():
        yield session

    matcher = SimpleNamespace(finish=AsyncMock(side_effect=FinishedException), send=AsyncMock())
    navigation.update(safe_session=scope, get_unified_player=AsyncMock(return_value=player), nav_cmd=matcher)
    handler = load_handler(navigation, matcher="nav_cmd.handle")
    with pytest.raises(FinishedException):
        await handler(SimpleNamespace(), SimpleNamespace(extract_plain_text=lambda: ""))
    text = matcher.finish.call_args.args[0].data["markdown"].content
    assert "导航中止" in text and "(30,0)" in text and "当场死亡" in text
    assert "导航完成" not in text
    session.commit.assert_awaited_once()


async def test_arrival_poll_notifies_death_without_arrival_rewards(modules, navigation, monkeypatch):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    navigation["generate_supernatural_encounters"] = lambda *args: [(30, ghost(modules, True))]
    player, task, session = traveler(), task_at(now), AsyncMock()
    session.get.return_value = player
    session.add = Mock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: [task]))

    @asynccontextmanager
    async def scope():
        yield session

    notify = AsyncMock(return_value=True)
    ordinary = Mock()
    monkeypatch.setattr(modules.notify, "notify_player", notify)
    monkeypatch.setattr(modules.events, "generate_navigation_events", ordinary)
    navigation.update(safe_session=scope, _select=lambda model: model, _logger=Mock())
    await load_handler(navigation, name="_check_nav_arrivals")()
    ordinary.assert_not_called()
    notify.assert_awaited_once()
    assert notify.call_args.kwargs["markdown"] is True
    assert "当场死亡" in notify.call_args.args[1]
    assert "导航完成" not in notify.call_args.args[1]
    navigation["_logger"].warning.assert_not_called()
    navigation["_logger"].error.assert_not_called()


@pytest.fixture
def consumer_context(modules, navigation, monkeypatch):
    now = datetime(2026, 7, 25, 12)
    navigation["datetime"] = SimpleNamespace(now=lambda: now)
    navigation["_tiles_per_second"] = lambda agility: 1.0
    navigation["generate_supernatural_encounters"] = lambda *args: [(30, ghost(modules, True))]
    module = ModuleType(f"{PACKAGE}.world.navigation")
    module.__dict__.update(navigation)
    task_module = ModuleType(f"{PACKAGE}.models.navigation_task")
    task_module.NavigationTask = SimpleNamespace
    for item in (module, task_module):
        monkeypatch.setitem(sys.modules, item.__name__, item)
    player, task, session = traveler(), task_at(now), AsyncMock()
    player.max_mp = 80
    player.dungeon_level = 1
    player.can_enter_dungeon_level = lambda level: True
    player.enter_dungeon = Mock()
    player.exit_dungeon = Mock()
    session.get.return_value = task
    session.add = Mock()

    @asynccontextmanager
    async def scope():
        yield session

    matcher = SimpleNamespace(finish=AsyncMock(side_effect=FinishedException), send=AsyncMock())
    notify = AsyncMock(return_value=True)
    monkeypatch.setattr(modules.notify, "notify_player", notify)
    navigation.update(
        safe_session=scope, require_player=AsyncMock(return_value=player),
        revive_cmd=matcher, attack_cmd=matcher,
        config=SimpleNamespace(map_config={}, _generate_dungeon_level_config=Mock(return_value={})),
        message_add_head=lambda text, event: text,
    )
    return SimpleNamespace(player=player, task=task, session=session, matcher=matcher, notify=notify)


async def test_enter_dungeon_stops_before_stamina_cost_on_navigation_death(navigation, consumer_context):
    ctx = consumer_context
    handler = load_handler(navigation, name="_handle_teleport_logic", path="world/teleport.py")
    with pytest.raises(FinishedException):
        await handler(SimpleNamespace(), "1层诡域", ctx.matcher)
    assert ctx.player.hp == 0 and ctx.player.stamina == 5
    ctx.player.enter_dungeon.assert_not_called()
    assert "当场死亡" in ctx.matcher.finish.call_args.args[0].data["markdown"].content
    ctx.session.commit.assert_awaited_once()


@pytest.mark.parametrize("already_dead", [False, True])
async def test_return_does_not_revive_new_navigation_death_but_keeps_existing_revive(
    navigation, consumer_context, already_dead,
):
    ctx = consumer_context
    ctx.player.is_in_dungeon = lambda: True
    ctx.player.hp = 0 if already_dead else 10
    ctx.player.mp = 3
    ctx.player.get_effective_attributes.return_value = {"agility": 10, "max_hp": 100, "max_mp": 80}
    handler = load_handler(navigation, name="handle_revive", path="world/teleport.py")
    with pytest.raises(FinishedException):
        await handler(SimpleNamespace())
    if already_dead:
        assert ctx.player.hp == 100 and ctx.player.mp == 80
        ctx.player.exit_dungeon.assert_called_once()
        assert "完全恢复" in ctx.matcher.finish.call_args.args[0]
    else:
        assert ctx.player.hp == 0 and ctx.player.mp == 3
        ctx.player.exit_dungeon.assert_not_called()
        assert "当场死亡" in ctx.matcher.finish.call_args.args[0].data["markdown"].content
    ctx.session.delete.assert_awaited_once_with(ctx.task)
    ctx.session.commit.assert_awaited_once()


async def test_teleport_item_cannot_overwrite_death_coordinates(navigation, consumer_context):
    ctx = consumer_context
    navigation["__package__"] = f"{PACKAGE}.item"
    handler = load_handler(navigation, name="_santa_teleport", path="item/item_effects.py")
    success, message = await handler(ctx.player, None, 1, {"target": ["900", "900"]}, ctx.session)
    assert not success and "身亡" in message
    assert ctx.player.hp == 0
    assert (ctx.player.real_world_x, ctx.player.real_world_y) == (30, 0)
    assert (ctx.player.x, ctx.player.y) == (30, 0)
    ctx.player.exit_dungeon.assert_not_called()
    ctx.notify.assert_awaited_once()
    assert ctx.notify.call_args.kwargs["markdown"] is True


@pytest.mark.parametrize("dead_id", ["attacker", "target"])
async def test_attack_stops_if_either_player_dies_during_navigation(
    modules, navigation, consumer_context, monkeypatch, dead_id,
):
    ctx = consumer_context
    attacker, target = ctx.player, traveler()
    attacker.id, target.id = "attacker", "target"
    attacker.get_current_region = target.get_current_region = lambda: "大都会"
    navigation["generate_supernatural_encounters"] = lambda player, *args: (
        [(30, ghost(modules, True))] if player.id == dead_id else []
    )
    monkeypatch.setattr(modules.events, "generate_navigation_events", Mock(return_value=[]))
    handler = load_handler(navigation, name="handle_player_attack", path="world/attack_command.py")
    with pytest.raises(FinishedException):
        await handler(ctx.session, attacker, target, SimpleNamespace())
    assert "本次攻击中止" in ctx.matcher.finish.call_args.args[0]
    assert (attacker if dead_id == "attacker" else target).hp == 0
    assert ctx.notify.call_args.args[0] == dead_id
    assert ctx.notify.call_args.kwargs["markdown"] is True
