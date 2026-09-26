"""有效游戏指令的精准匹配与统一入口限频。"""

from __future__ import annotations

import asyncio

from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.matcher import Matcher
from nonebot.message import event_preprocessor, run_preprocessor
from nonebot.rule import RegexRule
from nonebot.typing import T_State

from .command_strict_match import _is_command_matcher, enforce_strict_command_match
from .config import config
from .infrastructure.shared_rate_limiter import SharedSlidingWindowRateLimiter
from .utils_markdown import build_markdown


_command_limiter = SharedSlidingWindowRateLimiter("command")
_notice_limiter = SharedSlidingWindowRateLimiter("command-notice")
_GUARD_STATE_KEY = "_xiuxian_command_guard"


def _is_game_matcher(matcher: Matcher) -> bool:
    if matcher.plugin_name == "xiuxian_game":
        return True
    module_name = matcher.module_name or ""
    return module_name == "plugins.xiuxian_game" or module_name.startswith(
        "plugins.xiuxian_game."
    )


def _is_game_command(matcher: Matcher) -> bool:
    # 上下左右使用阻断式正则匹配；普通聊天监听器不消耗指令额度。
    return _is_command_matcher(matcher) or (
        matcher.block
        and any(isinstance(checker.call, RegexRule) for checker in matcher.rule.checkers)
    )


@event_preprocessor
async def prepare_command_guard(state: T_State) -> None:
    # NoneBot 为每个 matcher 浅拷贝 state，嵌套字典保留事件内共享的准入结果。
    state[_GUARD_STATE_KEY] = {}


@run_preprocessor
async def enforce_command_guard(
    matcher: Matcher,
    bot: Bot,
    event: Event,
    state: T_State,
) -> None:
    if (
        state.get(_GUARD_STATE_KEY, {}).get("allowed") is False
        and _is_game_matcher(matcher)
    ):
        raise IgnoredException("command ingress rate limited")
    if not _is_game_command(matcher):
        return
    await enforce_strict_command_match(matcher, event, state)
    if not _is_game_matcher(matcher):
        return

    platform_id = str(event.get_user_id() or "").strip()
    if not platform_id:
        return

    admission = state.setdefault(_GUARD_STATE_KEY, {})
    # Redis 调用会让出执行权；同一事件的多个 matcher 仍只能消费一次额度。
    async with admission.setdefault("lock", asyncio.Lock()):
        if "allowed" not in admission:
            settings = config.game_config["command_ingress"]
            admission["allowed"] = await _command_limiter.allow(
                platform_id,
                settings["calls_per_window"],
                settings["window_seconds"],
            )
            if not admission["allowed"] and await _notice_limiter.allow(
                platform_id, 1, settings["notice_cooldown_seconds"]
            ):
                await bot.send(
                    event,
                    build_markdown(
                        "# ⏳ 慢一点\n"
                        f"> 每 {settings['window_seconds']} 秒最多处理 "
                        f"**{settings['calls_per_window']}** 条游戏指令。\n"
                        "稍等片刻再操作；继续刷新的请求将静默忽略。"
                    ),
                )

    if not admission["allowed"]:
        raise IgnoredException("command ingress rate limited")
