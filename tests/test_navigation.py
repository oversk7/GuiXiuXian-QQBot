import asyncio
import sys
import types
from importlib import util
from pathlib import Path
from datetime import datetime, timedelta
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.append(str(REPO_ROOT))


def _register_stub_modules():
    nonebot = types.ModuleType("nonebot")

    class _DummyCommand:
        def handle(self):
            def _decorator(func):
                return func

            return _decorator

        async def finish(self, *args, **kwargs):
            return None

    def _dummy_handler(*args, **kwargs):
        return _DummyCommand()

    class _DummyDriver:
        def on_startup(self, func):
            return func

    nonebot.on_command = _dummy_handler
    nonebot.get_driver = lambda: _DummyDriver()
    sys.modules.setdefault("nonebot", nonebot)

    adapters_pkg = types.ModuleType("nonebot.adapters")
    adapters_pkg.__path__ = []
    sys.modules.setdefault("nonebot.adapters", adapters_pkg)

    adapters_qq = types.ModuleType("nonebot.adapters.qq")
    adapters_qq.MessageEvent = type("MessageEvent", (), {})
    adapters_qq.Message = type("Message", (), {})
    sys.modules.setdefault("nonebot.adapters.qq", adapters_qq)

    params = types.ModuleType("nonebot.params")
    params.CommandArg = type("CommandArg", (), {})
    sys.modules.setdefault("nonebot.params", params)

    plugins_pkg = types.ModuleType("plugins")
    plugins_pkg.__path__ = [str(REPO_ROOT / "plugins")]
    sys.modules.setdefault("plugins", plugins_pkg)

    xiuxian_pkg = types.ModuleType("plugins.xiuxian_game")
    xiuxian_pkg.__path__ = [str(REPO_ROOT / "plugins" / "xiuxian_game")]
    sys.modules.setdefault("plugins.xiuxian_game", xiuxian_pkg)

    models_pkg = types.ModuleType("plugins.xiuxian_game.models")
    models_pkg.__path__ = [str(REPO_ROOT / "plugins" / "xiuxian_game" / "models")]
    sys.modules.setdefault("plugins.xiuxian_game.models", models_pkg)

    db_module = types.ModuleType("plugins.xiuxian_game.models.db")

    async def _safe_session():
        raise RuntimeError("stubbed safe_session should not be used in tests")

    db_module.safe_session = _safe_session
    sys.modules.setdefault("plugins.xiuxian_game.models.db", db_module)

    player_module = types.ModuleType("plugins.xiuxian_game.models.player")
    player_module.Player = type("Player", (), {})
    sys.modules.setdefault("plugins.xiuxian_game.models.player", player_module)

    utils_module = types.ModuleType("plugins.xiuxian_game.utils")
    utils_module.message_add_head = lambda msg, event=None: msg
    sys.modules.setdefault("plugins.xiuxian_game.utils", utils_module)

    nav_task_module = types.ModuleType("plugins.xiuxian_game.models.navigation_task")
    nav_task_module.NavigationTask = type("NavigationTask", (), {})
    sys.modules.setdefault("plugins.xiuxian_game.models.navigation_task", nav_task_module)


_register_stub_modules()

nav_path = REPO_ROOT / "plugins" / "xiuxian_game" / "world" / "navigation.py"
spec = util.spec_from_file_location("plugins.xiuxian_game.world.navigation", nav_path)
nav = util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(nav)


def test_low_agility_navigation_accumulates_progress(monkeypatch):
    start_time = datetime(2024, 1, 1, 0, 0, 0)
    current_time = {"value": start_time}

    class DummyDateTime(datetime):
        @classmethod
        def now(cls):
            return current_time["value"]

    monkeypatch.setattr(nav, "datetime", DummyDateTime)

    player = SimpleNamespace(
        agility=1,
        region=nav.REAL_WORLD,
        real_world_x=0,
        real_world_y=0,
        x=0,
        y=0,
    )

    def _is_in_dungeon():
        return False

    player.is_in_dungeon = _is_in_dungeon

    task = SimpleNamespace(target_x=1, target_y=0, last_update=start_time)

    # 前几次查询间隔不足以跨越一个整数格，应该持续累积时间而不移动
    for step in range(1, 10):
        current_time["value"] = start_time + timedelta(seconds=step * 5)
        reached = asyncio.run(nav._update_nav_position(player, task))
        assert not reached
        assert player.real_world_x == 0
        assert task.last_update == start_time

    current_time["value"] = start_time + timedelta(seconds=100)
    reached = asyncio.run(nav._update_nav_position(player, task))

    assert reached
    assert player.real_world_x == 1
    assert player.real_world_y == 0
    assert task.last_update == start_time + timedelta(seconds=100)
