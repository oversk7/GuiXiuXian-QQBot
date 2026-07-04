"""全量群裸消息指令精准匹配守卫的单元测试。

用真实的 TrieRule 解析构造 state,验证 command_strict_match 的判定
与 NoneBot 指令解析的 key/取值约定一致。
"""

from types import SimpleNamespace

from nonebot.adapters.qq.message import Message
from nonebot.consts import PREFIX_KEY, RAW_CMD_KEY
from nonebot.rule import TRIE_VALUE, CommandRule, Rule, TrieRule

from plugins.xiuxian_game.command_strict_match import (
    _is_bare_full_group_message,
    _is_command_matcher,
    _violates_strict_match,
)

_CMD = "测试守卫指令"


def _parse(text: str) -> dict:
    """用 NoneBot 真实的 TrieRule 解析文本,返回 state[PREFIX_KEY]。"""
    TrieRule.add_prefix(_CMD, TRIE_VALUE("", (_CMD,)))
    TrieRule.add_prefix(f"/{_CMD}", TRIE_VALUE("/", (_CMD,)))

    class FakeMessageEvent:
        def get_type(self) -> str:
            return "message"

        def get_message(self) -> Message:
            return Message(text)

    state: dict = {}
    TrieRule.get_value(None, FakeMessageEvent(), state)
    return state[PREFIX_KEY]


# ---------------- _violates_strict_match ----------------

def test_exact_command_allowed():
    prefix = _parse(_CMD)
    assert prefix[RAW_CMD_KEY] == _CMD
    assert not _violates_strict_match(prefix)


def test_command_with_space_arg_allowed():
    prefix = _parse(f"{_CMD} 参数")
    assert not _violates_strict_match(prefix)


def test_command_glued_to_chat_blocked():
    prefix = _parse(f"{_CMD}好重啊")
    assert _violates_strict_match(prefix)


def test_slash_prefix_glued_arg_allowed():
    prefix = _parse(f"/{_CMD}参数")
    assert not _violates_strict_match(prefix)


def test_non_command_text_ignored():
    prefix = _parse("随便聊聊天")
    assert prefix[RAW_CMD_KEY] is None
    assert not _violates_strict_match(prefix)


# ---------------- _is_bare_full_group_message ----------------

def _event(event_type: str, to_me: bool = False, mentioned: bool = False):
    event = SimpleNamespace(__type__=event_type, to_me=to_me)
    if mentioned:
        event._mentioned_bot = True
    return event


def test_bare_full_group_message_detected():
    assert _is_bare_full_group_message(_event("GROUP_MESSAGE_CREATE"))


def test_mentioned_full_group_message_not_bare():
    assert not _is_bare_full_group_message(
        _event("GROUP_MESSAGE_CREATE", to_me=True, mentioned=True)
    )


def test_at_group_message_not_affected():
    assert not _is_bare_full_group_message(_event("GROUP_AT_MESSAGE_CREATE"))


# ---------------- _is_command_matcher ----------------

def test_command_matcher_detected():
    matcher = SimpleNamespace(rule=Rule(CommandRule([(_CMD,)])))
    assert _is_command_matcher(matcher)


def test_plain_message_matcher_not_command():
    async def always_true() -> bool:
        return True

    matcher = SimpleNamespace(rule=Rule(always_true))
    assert not _is_command_matcher(matcher)
