import importlib.util
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
ENGINE_PATH = PROJECT_ROOT / "plugins" / "xiuxian_game" / "story" / "engine.py"


class DummyPlayer:
    def __init__(self, completed_trials=None):
        self.id = "player-1"
        self.uid = 10001
        self.nickname = "测试玩家"
        self.level = 12
        self.sex = "男"
        self.region = "大都会"
        self.exp = 123
        self.hp = 30
        self.max_hp = 40
        self.mp = 20
        self.max_mp = 25
        self.attack = 15
        self.defense = 10
        self.agility = 8
        self.stamina = 9
        self.luck = 7
        self.resentment = 0
        self.gold = 666
        self.gold2 = 88
        self.vip = 0
        self.guild_id = None
        self.guild_contribution = 0
        self.attribute_points = 0
        self.sign_streak = 0
        self._completed_trials = completed_trials or []

    def get_current_coordinates(self):
        return 3, 4

    def get_completed_trials(self):
        return list(self._completed_trials)


class DummyStorySession:
    pass


class DummyAsyncSession:
    pass


def load_story_engine_module():
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

    config_module = types.ModuleType("plugins.xiuxian_game.config")
    config_module.config = types.SimpleNamespace()
    sys.modules["plugins.xiuxian_game.config"] = config_module

    story_session_module = types.ModuleType("plugins.xiuxian_game.models.story_session")
    story_session_module.StorySession = DummyStorySession
    sys.modules["plugins.xiuxian_game.models.story_session"] = story_session_module

    player_module = types.ModuleType("plugins.xiuxian_game.models.player")
    player_module.Player = DummyPlayer
    sys.modules["plugins.xiuxian_game.models.player"] = player_module

    sqlalchemy_module = types.ModuleType("sqlalchemy")
    sqlalchemy_module.select = lambda *args, **kwargs: None
    sys.modules["sqlalchemy"] = sqlalchemy_module

    sqlalchemy_ext_module = types.ModuleType("sqlalchemy.ext")
    sys.modules["sqlalchemy.ext"] = sqlalchemy_ext_module

    sqlalchemy_asyncio_module = types.ModuleType("sqlalchemy.ext.asyncio")
    sqlalchemy_asyncio_module.AsyncSession = DummyAsyncSession
    sys.modules["sqlalchemy.ext.asyncio"] = sqlalchemy_asyncio_module

    spec = importlib.util.spec_from_file_location("plugins.xiuxian_game.story.engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_format_content_exposes_completed_trial_variable():
    module = load_story_engine_module()
    module.StoryEngine._build_index = lambda self: None
    engine = module.StoryEngine()
    player = DummyPlayer(completed_trials=["荔湾鬼镇"])

    content = "荔湾鬼镇通关状态：{trial_completed_荔湾鬼镇}"
    rendered = engine.format_content(content, player, {})

    assert rendered == "荔湾鬼镇通关状态：True"
