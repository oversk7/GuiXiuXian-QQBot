"""全量消息群裸消息的指令精准匹配守卫。

`COMMAND_START` 含空前缀时,NoneBot 按"消息开头命中指令名"匹配,全量消息群
(GROUP_MESSAGE_CREATE)里日常聊天(如"背包好重")极易误触指令。

本守卫要求:未@机器人的全量群裸消息,指令名后必须是空白或消息结束才放行。
@机器人、私聊/频道、显式使用 "/" 前缀的消息均不受影响。
"""

from __future__ import annotations

from nonebot.adapters import Event
from nonebot.consts import (
    CMD_ARG_KEY,
    CMD_START_KEY,
    CMD_WHITESPACE_KEY,
    PREFIX_KEY,
    RAW_CMD_KEY,
)
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.rule import CommandRule
from nonebot.typing import T_State


def _event_type(event: Event) -> str:
    raw = getattr(event, "__type__", "")
    return str(getattr(raw, "value", raw))


def _is_bare_full_group_message(event: Event) -> bool:
    return (
        _event_type(event) == "GROUP_MESSAGE_CREATE"
        and not bool(getattr(event, "to_me", False))
    )


def _is_command_matcher(matcher: Matcher) -> bool:
    # 指令解析结果是全局写入 state 的,必须只拦截真正的指令 matcher,
    # 避免误伤 on_message 类守卫/剧情处理器
    return any(isinstance(checker.call, CommandRule) for checker in matcher.rule.checkers)


def _violates_strict_match(prefix: dict) -> bool:
    if prefix.get(RAW_CMD_KEY) is None:
        return False
    if prefix.get(CMD_START_KEY):
        return False  # 显式 "/" 前缀视为明确指令意图
    cmd_arg = prefix.get(CMD_ARG_KEY)
    return bool(cmd_arg) and prefix.get(CMD_WHITESPACE_KEY) is None


async def enforce_strict_command_match(matcher: Matcher, event: Event, state: T_State) -> None:
    if not _is_bare_full_group_message(event):
        return
    if not _is_command_matcher(matcher):
        return
    prefix = state.get(PREFIX_KEY)
    if not isinstance(prefix, dict):
        return
    if _violates_strict_match(prefix):
        raise IgnoredException("全量群裸消息指令名后未跟空白，按聊天忽略")
