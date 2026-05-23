import importlib.util
import sys
import types
from enum import Enum
from pathlib import Path


class _DummyEventType(str, Enum):
    GROUP_MESSAGE_CREATE = "GROUP_MESSAGE_CREATE"


class _DummyGroupAtMessageCreateEvent:
    pass


_event_classes = {}


def _register_event_class(event_class):
    _event_classes[event_class.__type__.value] = event_class
    return event_class


def _load_module():
    event_mod = types.ModuleType("nonebot.adapters.qq.event")
    event_mod.EventType = _DummyEventType
    event_mod.GroupAtMessageCreateEvent = _DummyGroupAtMessageCreateEvent
    event_mod.register_event_class = _register_event_class

    stubs = {
        "nonebot": types.ModuleType("nonebot"),
        "nonebot.adapters": types.ModuleType("nonebot.adapters"),
        "nonebot.adapters.qq": types.ModuleType("nonebot.adapters.qq"),
        "nonebot.adapters.qq.event": event_mod,
    }
    created_stubs = []
    for name, module in stubs.items():
        if name not in sys.modules:
            sys.modules[name] = module
            created_stubs.append((name, module))

    _event_classes.clear()
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


def test_group_message_create_registered_as_group_at_event_compatibility():
    _load_module()

    event_class = _event_classes["GROUP_MESSAGE_CREATE"]
    assert issubclass(event_class, _DummyGroupAtMessageCreateEvent)
