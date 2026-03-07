import asyncio
import importlib.util
import sys
import types
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
MODULE_PATH = PROJECT_ROOT / "plugins" / "xiuxian_game" / "player" / "help.py"


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


class DummyEvent:
    def get_plaintext(self):
        return ""


def load_help_module():
    plugins_pkg = types.ModuleType("plugins")
    plugins_pkg.__path__ = []
    sys.modules["plugins"] = plugins_pkg

    xiuxian_pkg = types.ModuleType("plugins.xiuxian_game")
    xiuxian_pkg.__path__ = []
    sys.modules["plugins.xiuxian_game"] = xiuxian_pkg

    player_pkg = types.ModuleType("plugins.xiuxian_game.player")
    player_pkg.__path__ = []
    sys.modules["plugins.xiuxian_game.player"] = player_pkg

    models_pkg = types.ModuleType("plugins.xiuxian_game.models")
    models_pkg.__path__ = []
    models_pkg.Player = object
    sys.modules["plugins.xiuxian_game.models"] = models_pkg

    inventory_module = types.ModuleType("plugins.xiuxian_game.models.inventory")
    inventory_module.ItemInstance = object
    inventory_module.ItemType = object
    sys.modules["plugins.xiuxian_game.models.inventory"] = inventory_module

    db_module = types.ModuleType("plugins.xiuxian_game.models.db")
    db_module.safe_session = lambda: None
    sys.modules["plugins.xiuxian_game.models.db"] = db_module

    config_module = types.ModuleType("plugins.xiuxian_game.config")
    config_module.config = types.SimpleNamespace()
    sys.modules["plugins.xiuxian_game.config"] = config_module

    utils_module = types.ModuleType("plugins.xiuxian_game.utils")
    utils_module.bypass_urls = lambda text: text
    sys.modules["plugins.xiuxian_game.utils"] = utils_module

    nonebot_module = types.ModuleType("nonebot")
    nonebot_module.on_command = lambda *args, **kwargs: DummyMatcher()
    nonebot_module.on_message = lambda *args, **kwargs: DummyMatcher()
    sys.modules["nonebot"] = nonebot_module

    permission_module = types.ModuleType("nonebot.permission")
    permission_module.SUPERUSER = object()
    sys.modules["nonebot.permission"] = permission_module

    params_module = types.ModuleType("nonebot.params")
    params_module.CommandArg = lambda: None
    sys.modules["nonebot.params"] = params_module

    rule_module = types.ModuleType("nonebot.rule")
    rule_module.to_me = lambda: None
    sys.modules["nonebot.rule"] = rule_module

    adapters_pkg = types.ModuleType("nonebot.adapters")
    adapters_pkg.__path__ = []
    sys.modules["nonebot.adapters"] = adapters_pkg

    qq_module = types.ModuleType("nonebot.adapters.qq")
    qq_module.MessageEvent = DummyEvent
    qq_module.Message = str
    qq_module.MessageSegment = types.SimpleNamespace(file_image=lambda x: x)
    sys.modules["nonebot.adapters.qq"] = qq_module

    qq_message_module = types.ModuleType("nonebot.adapters.qq.message")
    qq_message_module.MessageKeyboard = object
    qq_message_module.MessageArk = object
    sys.modules["nonebot.adapters.qq.message"] = qq_message_module

    qq_models_module = types.ModuleType("nonebot.adapters.qq.models")
    qq_models_module.MessageArkKv = object
    qq_models_module.MessageArk = object
    qq_models_module.MessageArkObj = object
    qq_models_module.MessageArkObjKv = object
    qq_models_module.MessageMarkdown = object
    qq_models_module.MessageMarkdownParams = object
    sys.modules["nonebot.adapters.qq.models"] = qq_models_module

    qq_models_common_module = types.ModuleType("nonebot.adapters.qq.models.common")
    qq_models_common_module.MessageMarkdown = object
    qq_models_common_module.MessageMarkdownParams = object
    sys.modules["nonebot.adapters.qq.models.common"] = qq_models_common_module

    spec = importlib.util.spec_from_file_location("plugins.xiuxian_game.player.help", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_fun_module_lists_completed_trials_command():
    module = load_help_module()

    try:
        asyncio.run(module.handle_fun_module(DummyEvent()))
    except FinishCalled as exc:
        message = str(exc.message)
    else:
        raise AssertionError("expected fun module command to finish with help text")

    assert "【已通关试炼】" in message


def test_entertainment_and_full_help_include_completed_trials_command():
    module = load_help_module()
    module._generate_full_help_image = lambda: None

    try:
        asyncio.run(module.handle_entertainment(DummyEvent()))
    except FinishCalled as exc:
        entertainment_message = str(exc.message)
    else:
        raise AssertionError("expected entertainment command to finish with help text")

    try:
        asyncio.run(module.handle_full_help(DummyEvent()))
    except FinishCalled as exc:
        full_help_message = str(exc.message)
    else:
        raise AssertionError("expected full help command to finish with help text")

    assert "【已通关试炼】" in entertainment_message
    assert "【已通关试炼】" in full_help_message
