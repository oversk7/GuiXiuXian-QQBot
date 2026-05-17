import importlib.util
import sys
import types
from pathlib import Path


class _DummyBot:
    async def send(self, event, message, **kwargs):
        return message


class _DummyMessageSegment:
    @staticmethod
    def text(value):
        return value


def _load_module():
    nonebot_mod = types.ModuleType("nonebot")
    adapters_mod = types.ModuleType("nonebot.adapters")
    qq_mod = types.ModuleType("nonebot.adapters.qq")
    qq_mod.Bot = _DummyBot
    qq_mod.MessageSegment = _DummyMessageSegment
    stubs = {
        "nonebot": nonebot_mod,
        "nonebot.adapters": adapters_mod,
        "nonebot.adapters.qq": qq_mod,
    }
    created_stubs = []
    for name, module in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = module
            created_stubs.append((name, module))

    module_path = (
        Path(__file__).resolve().parents[1]
        / "plugins"
        / "xiuxian_game"
        / "qq_full_message_send.py"
    )
    spec = importlib.util.spec_from_file_location("qq_full_message_send_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name, module_stub in created_stubs:
        if sys.modules.get(name) is module_stub:
            del sys.modules[name]
    return module


def test_with_sender_mention_uses_author_username():
    module = _load_module()
    event = types.SimpleNamespace(author=types.SimpleNamespace(username="  阿青  "))

    assert module._with_sender_mention(event, "修炼完成") == "@阿青 修炼完成"


def test_with_sender_mention_does_not_fall_back_to_openid():
    module = _load_module()
    event = types.SimpleNamespace(author=types.SimpleNamespace(member_openid="openid_123"))

    assert module._with_sender_mention(event, "修炼完成") == "修炼完成"
