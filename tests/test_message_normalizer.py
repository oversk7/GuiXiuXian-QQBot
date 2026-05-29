import asyncio
import importlib.util
import sys
import types
from pathlib import Path


class _DummyMessageSegment:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data

    @staticmethod
    def text(value):
        return _DummyMessageSegment("text", {"text": value})


class _DummyBot:
    self_id = "102794949"
    self_info = types.SimpleNamespace(id="102794949")


class _DummyEvent:
    def __init__(self, event_type, message, to_me=False):
        self.__type__ = event_type
        self.group_openid = "group_openid"
        self._message = message
        self.to_me = to_me

    def get_message(self):
        return self._message


def _load_module():
    nonebot_mod = types.ModuleType("nonebot")
    adapters_mod = types.ModuleType("nonebot.adapters")
    qq_mod = types.ModuleType("nonebot.adapters.qq")
    message_mod = types.ModuleType("nonebot.message")

    qq_mod.Bot = _DummyBot
    qq_mod.MessageEvent = _DummyEvent
    qq_mod.MessageSegment = _DummyMessageSegment
    message_mod.event_preprocessor = lambda func: func

    stubs = {
        "nonebot": nonebot_mod,
        "nonebot.adapters": adapters_mod,
        "nonebot.adapters.qq": qq_mod,
        "nonebot.message": message_mod,
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
        / "message_normalizer.py"
    )
    spec = importlib.util.spec_from_file_location("message_normalizer_under_test", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    for name, module_stub in created_stubs:
        if sys.modules.get(name) is module_stub:
            del sys.modules[name]
    return module


def _mention_user(user_id="member_openid"):
    return _DummyMessageSegment("mention_user", {"user_id": user_id})


def _group_mention_user(user_id="member_openid", is_you=False):
    return _DummyMessageSegment(
        "group_mention_user",
        {
            "bot": False,
            "id": user_id,
            "is_you": is_you,
            "member_openid": user_id,
            "scope": "single",
            "username": "player",
        },
    )


def _image():
    return _DummyMessageSegment("image", {"url": "https://example.com/image.png"})


def test_full_group_leading_mention_user_is_stripped():
    module = _load_module()
    message = [_mention_user("A1188C82191CA5A015D0D68AA843AC29"), _DummyMessageSegment.text(" 喂食 怨念  ")]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is True
    assert [(seg.type, seg.data) for seg in event.get_message()] == [
        ("text", {"text": "喂食 怨念  "})
    ]


def test_empty_full_group_leading_mention_user_to_bot_stays_to_me():
    module = _load_module()
    message = [_mention_user("A1188C82191CA5A015D0D68AA843AC29"), _DummyMessageSegment.text(" ")]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is True
    assert [(seg.type, seg.data) for seg in event.get_message()] == [
        ("text", {"text": ""})
    ]


def test_non_full_group_leading_mention_user_is_not_stripped_without_bot_id_match():
    module = _load_module()
    message = [_mention_user("other_member"), _DummyMessageSegment.text(" 喂食 怨念  ")]
    event = _DummyEvent("GROUP_AT_MESSAGE_CREATE", message)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is False
    assert event.get_message() == message


def test_full_group_image_after_leading_mention_user_is_not_treated_as_bot_mention():
    module = _load_module()
    message = [_mention_user("member_openid"), _image()]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is False
    assert event.get_message() == message


def test_full_group_image_with_empty_text_after_leading_mention_user_is_not_treated_as_bot_mention():
    module = _load_module()
    message = [_mention_user("member_openid"), _DummyMessageSegment.text(" "), _image()]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is False
    assert event.get_message() == message


def test_full_group_leading_mention_user_to_other_member_is_not_stripped():
    module = _load_module()
    message = [
        _mention_user("other_member"),
        _DummyMessageSegment.text(" 帮助"),
        _group_mention_user("other_member", is_you=False),
    ]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message, to_me=True)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is False
    assert event.get_message() == message


def test_empty_full_group_mention_user_to_other_member_clears_to_me():
    module = _load_module()
    message = [
        _mention_user("other_member"),
        _DummyMessageSegment.text(" "),
        _group_mention_user("other_member", is_you=False),
    ]
    event = _DummyEvent("GROUP_MESSAGE_CREATE", message, to_me=True)

    asyncio.run(module.normalize_qq_group_command_message(_DummyBot(), event))

    assert event.to_me is False
    assert event.get_message() == message
