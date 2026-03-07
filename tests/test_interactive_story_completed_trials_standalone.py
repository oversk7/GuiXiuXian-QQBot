import asyncio
import importlib.util
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
MODULE_PATH = PROJECT_ROOT / "plugins" / "xiuxian_game" / "story" / "interactive_story.py"


class FinishCalled(Exception):
    def __init__(self, message):
        super().__init__(str(message))
        self.message = message


class DummyMatcher:
    def handle(self):
        def decorator(func):
            return func
        return decorator

    async def finish(self, message):
        raise FinishCalled(message)


class DummyPlayer:
    def __init__(self, completed_trials=None):
        self.id = "player-1"
        self._completed_trials = completed_trials or []

    def get_completed_trials(self):
        return list(self._completed_trials)


class DummyEvent:
    pass


class DummySafeSession:
    def __init__(self, player):
        self.player = player

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def add(self, obj):
        return None

    async def commit(self):
        return None


class DummyStorySession:
    @staticmethod
    async def get_active_session(session, player_id):
        return None


class DummyStoryEngine:
    def __init__(self):
        self._story_index = {}

    def get_story_list(self):
        return []

    def get_story(self, story_id):
        return None


def load_interactive_story_module(player):
    plugins_pkg = types.ModuleType("plugins")
    plugins_pkg.__path__ = []
    sys.modules["plugins"] = plugins_pkg

    xiuxian_pkg = types.ModuleType("plugins.xiuxian_game")
    xiuxian_pkg.__path__ = []
    sys.modules["plugins.xiuxian_game"] = xiuxian_pkg

    story_pkg = types.ModuleType("plugins.xiuxian_game.story")
    story_pkg.__path__ = []
    sys.modules["plugins.xiuxian_game.story"] = story_pkg

    models_pkg = types.ModuleType("plugins.xiuxian_game.models")
    models_pkg.__path__ = []
    sys.modules["plugins.xiuxian_game.models"] = models_pkg

    nonebot_module = types.ModuleType("nonebot")
    nonebot_module.on_command = lambda *args, **kwargs: DummyMatcher()
    nonebot_module.on_regex = lambda *args, **kwargs: DummyMatcher()
    sys.modules["nonebot"] = nonebot_module

    adapters_pkg = types.ModuleType("nonebot.adapters")
    adapters_pkg.__path__ = []
    sys.modules["nonebot.adapters"] = adapters_pkg

    qq_module = types.ModuleType("nonebot.adapters.qq")
    qq_module.MessageEvent = DummyEvent
    qq_module.Message = str
    qq_module.MessageSegment = types.SimpleNamespace(text=lambda x: x, file_image=lambda x: x)
    sys.modules["nonebot.adapters.qq"] = qq_module

    params_module = types.ModuleType("nonebot.params")
    params_module.CommandArg = lambda: None
    sys.modules["nonebot.params"] = params_module

    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.select = lambda *args, **kwargs: None
    sys.modules["sqlalchemy"] = sqlalchemy_module

    db_module = types.ModuleType("plugins.xiuxian_game.models.db")
    db_module.safe_session = lambda: DummySafeSession(player)
    sys.modules["plugins.xiuxian_game.models.db"] = db_module

    player_module = types.ModuleType("plugins.xiuxian_game.models.player")
    player_module.Player = DummyPlayer
    sys.modules["plugins.xiuxian_game.models.player"] = player_module

    story_session_module = types.ModuleType("plugins.xiuxian_game.models.story_session")
    story_session_module.StorySession = DummyStorySession
    sys.modules["plugins.xiuxian_game.models.story_session"] = story_session_module

    utils_module = types.ModuleType("plugins.xiuxian_game.utils")
    utils_module.message_add_head = lambda message, event: message
    sys.modules["plugins.xiuxian_game.utils"] = utils_module

    platform_utils_module = types.ModuleType("plugins.xiuxian_game.platform_utils")

    async def get_unified_player(session, event):
        return session.player

    platform_utils_module.get_unified_player = get_unified_player
    sys.modules["plugins.xiuxian_game.platform_utils"] = platform_utils_module

    engine_module = types.ModuleType("plugins.xiuxian_game.story.engine")
    engine_module.StoryEngine = DummyStoryEngine
    sys.modules["plugins.xiuxian_game.story.engine"] = engine_module

    spec = importlib.util.spec_from_file_location("plugins.xiuxian_game.story.interactive_story", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_handle_completed_trials_lists_completed_trials():
    player = DummyPlayer(completed_trials=["荔湾鬼镇", "荔湾鬼镇_完美"])
    module = load_interactive_story_module(player)

    try:
        asyncio.run(module.handle_completed_trials(DummyEvent()))
    except FinishCalled as exc:
        message = str(exc.message)
    else:
        raise AssertionError("expected command to finish with completed trials message")

    assert "已通关试炼" in message
    assert "荔湾鬼镇" in message
    assert "荔湾鬼镇_完美" in message


def test_handle_completed_trials_shows_empty_message_when_no_records():
    player = DummyPlayer(completed_trials=[])
    module = load_interactive_story_module(player)

    try:
        asyncio.run(module.handle_completed_trials(DummyEvent()))
    except FinishCalled as exc:
        message = str(exc.message)
    else:
        raise AssertionError("expected command to finish with empty completed trials message")

    assert message == "📚 你还没有已通关的试炼记录"
