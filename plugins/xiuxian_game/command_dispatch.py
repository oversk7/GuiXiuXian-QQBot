"""Filter dispatch candidates without changing NoneBot's matching semantics.

The provider API is public; the preprocessor hook and Trie completion hook rely
on NoneBot 2.5's handle_event ordering. Recheck these hooks when upgrading.
Each dispatch iteration scans its layer and rebuilds its command map (O(N)
structure scanning). Unknown rules, permissions, or overridden checks cause
that entire layer to use native full enumeration: their checks may rewrite the
shared command prefix. Known native listeners still allow candidate filtering.
"""

import asyncio
from collections import defaultdict
from contextlib import AsyncExitStack
from contextvars import ContextVar
from dataclasses import dataclass
from functools import wraps

import nonebot.message as message_dispatch
import nonebot.permission as native_permission
from nonebot.adapters.qq import permission as qq_permission

from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.consts import CMD_KEY, PREFIX_KEY
from nonebot.dependencies import Dependent
from nonebot.matcher import DEFAULT_PROVIDER_CLASS, Matcher, MatcherProvider, matchers
from nonebot.permission import Permission
from nonebot.params import DependParam, StateParam
from nonebot.rule import (
    CommandRule, EndswithRule, FullmatchRule, IsTypeRule, KeywordsRule,
    RegexRule, Rule, StartswithRule, ToMeRule, TrieRule,
)
from nonebot.typing import T_DependencyCache, T_State


class CommandDispatchRule(Rule):
    async def __call__(
        self,
        bot: Bot,
        event: Event,
        state: T_State,
        stack: AsyncExitStack | None = None,
        dependency_cache: T_DependencyCache | None = None,
    ) -> bool:
        prefix = state.get(PREFIX_KEY)
        if isinstance(prefix, dict) and CMD_KEY in prefix and len(self.checkers) == 1:
            command = prefix[CMD_KEY]
            checker = next(iter(self.checkers)).call
            if type(checker) is CommandRule and (
                command is None or isinstance(command, tuple)
            ):
                # Matching commands still use NoneBot's argument, whitespace
                # and dependency validation, including force_whitespace.
                if command not in checker.cmds:
                    return False
        return await super().__call__(bot, event, state, stack, dependency_cache)


def optimize_command_rules() -> int:
    optimized = 0
    for group in matchers.values():
        for matcher in group:
            module = matcher.module_name or ""
            if not (
                matcher.plugin_name == "xiuxian_game"
                or module == "plugins.xiuxian_game"
                or module.startswith("plugins.xiuxian_game.")
            ):
                continue
            rule = matcher.rule
            # Leave composite/custom rules intact because their checkers may
            # produce state or other effects even when a command does not match.
            if type(rule) is not Rule or len(rule.checkers) != 1:
                continue
            checker = next(iter(rule.checkers))
            if type(checker.call) is not CommandRule:
                continue
            matcher.rule = CommandDispatchRule(checker)
            optimized += 1
    return optimized


@dataclass
class _DispatchContext:
    state: T_State
    owner_task: asyncio.Task
    is_message: bool
    parsed: bool = False


_dispatch_context: ContextVar[_DispatchContext | None] = ContextVar(
    "command_dispatch_context", default=None
)
_native_check_perm = Matcher.check_perm.__func__
_native_check_rule = Matcher.check_rule.__func__
_native_command_params = next(iter(Rule(CommandRule([])).checkers)).params


def _native_params(params):
    if len(params) != len(_native_command_params):
        return False
    for actual, expected in zip(params, _native_command_params):
        info = actual.field_info
        if (
            actual.name != expected.name
            or actual.annotation != expected.annotation
            or type(info) is not DependParam
            or info.validate
            or info.use_cache is not True
            or type(info.dependent) is not Dependent
            or info.dependent.call is not expected.field_info.dependent.call
            or info.dependent.parameterless
            or len(info.dependent.params) != 1
        ):
            return False
        state = info.dependent.params[0]
        if (state.name != "state"
                or state.annotation != expected.field_info.dependent.params[0].annotation
                or type(state.field_info) is not StateParam
                or state.field_info.validate):
            return False
    return True


_prefix_safe_rules = frozenset({
    CommandRule, StartswithRule, EndswithRule, FullmatchRule, KeywordsRule,
    RegexRule, ToMeRule, IsTypeRule,
})
_prefix_safe_permissions = frozenset({
    native_permission.Message, native_permission.Notice, native_permission.Request,
    native_permission.MetaEvent, native_permission.SuperUser,
})
_qq_permission_calls = frozenset(
    checker.call
    for permission in (
        qq_permission.GROUP_MEMBER, qq_permission.GROUP_ADMIN,
        qq_permission.GROUP_OWNER, qq_permission.GUILD_ADMIN,
        qq_permission.GUILD_CHANNEL_ADMIN, qq_permission.GUILD_OWNER,
    )
    for checker in permission.checkers
)


def _standard_dependency(actual, expected):
    """Require the native parameter tree, including its nested dependencies."""
    if (type(actual) is not Dependent or actual.call is not expected.call
            or actual.parameterless or len(actual.params) != len(expected.params)):
        return False
    for field, native in zip(actual.params, expected.params):
        info, native_info = field.field_info, native.field_info
        if (field.name != native.name or field.annotation != native.annotation
                or type(info) is not type(native_info)
                or info.validate != native_info.validate):
            return False
        if type(info) is DependParam and (
            info.use_cache != native_info.use_cache
            or not _standard_dependency(info.dependent, native_info.dependent)
        ):
            return False
    return True


def _unsafe_layer_reason(matcher):
    if (getattr(matcher.check_perm, "__func__", None) is not _native_check_perm
            or getattr(matcher.check_rule, "__func__", None) is not _native_check_rule):
        return "overridden matcher checks"
    if type(matcher.permission) is not Permission:
        return "custom Permission"
    for checker in matcher.permission.checkers:
        if not (type(checker.call) in _prefix_safe_permissions
                or any(checker.call is call for call in _qq_permission_calls)):
            return "unknown permission checker"
        expected = Dependent.parse(
            call=checker.call, allow_types=Permission.HANDLER_PARAM_TYPES
        )
        if not _standard_dependency(checker, expected):
            return "custom permission dependencies"
    if type(matcher.rule) is not Rule:
        return "custom Rule"
    for checker in matcher.rule.checkers:
        if type(checker.call) not in _prefix_safe_rules:
            return "unknown rule checker"
        if type(checker.call) is CommandRule:
            if (type(checker) is not Dependent or checker.parameterless
                    or not _native_params(checker.params)):
                return "custom command dependencies"
        else:
            expected = Dependent.parse(
                call=checker.call, allow_types=Rule.HANDLER_PARAM_TYPES
            )
            if not _standard_dependency(checker, expected):
                return "custom rule dependencies"
    return None


def _index_commands(matcher):
    module = matcher.module_name or ""
    if not (
        matcher.plugin_name == "xiuxian_game"
        or module == "plugins.xiuxian_game"
        or module.startswith("plugins.xiuxian_game.")
    ):
        return None
    if (
        matcher.type != "message"
        or matcher.temp
        or matcher.expire_time is not None
        or getattr(matcher.check_perm, "__func__", None) is not _native_check_perm
        or getattr(matcher.check_rule, "__func__", None) is not _native_check_rule
        or type(matcher.permission) is not Permission
        or matcher.permission.checkers
        or type(matcher.rule) is not Rule
        or len(matcher.rule.checkers) != 1
    ):
        return None
    checker = next(iter(matcher.rule.checkers))
    if (type(checker) is not Dependent or type(checker.call) is not CommandRule
            or checker.parameterless):
        return None
    # A manually constructed Dependent can attach additional dependencies even
    # to a native CommandRule. Only its standard injected parameters are safe.
    if not _native_params(checker.params):
        return None
    cmds = checker.call.cmds
    if not isinstance(cmds, tuple) or not all(
        isinstance(cmd, tuple) and all(isinstance(part, str) for part in cmd)
        for cmd in cmds
    ):
        return None
    return cmds


def _is_owner(context):
    try:
        return asyncio.current_task() is context.owner_task
    except RuntimeError:
        # Synchronous handlers run in worker threads with inherited ContextVars.
        return False


class _CandidateList(list):
    def __iter__(self):
        context = _dispatch_context.get()
        if (
            context is None
            or not _is_owner(context)
            or not context.is_message
            or not context.parsed
        ):
            return super().__iter__()
        prefix = context.state.get(PREFIX_KEY)
        if not isinstance(prefix, dict) or CMD_KEY not in prefix:
            return super().__iter__()
        command = prefix[CMD_KEY]
        if command is not None and not (
            isinstance(command, tuple) and all(isinstance(part, str) for part in command)
        ):
            return super().__iter__()

        # Store positions rather than sets of matchers to preserve registration
        # order, including duplicate entries, in the candidate snapshot.
        index = defaultdict(list)
        fallback = []
        snapshot = list(super().__iter__())
        for position, matcher in enumerate(snapshot):
            if _unsafe_layer_reason(matcher) is not None:
                return iter(snapshot)
            commands = _index_commands(matcher)
            if commands is None:
                fallback.append(position)
            else:
                for cmd in set(commands):
                    index[cmd].append(position)
        positions = sorted(fallback + index.get(command, []))
        return iter([snapshot[position] for position in positions])


class CommandMatcherProvider(defaultdict, MatcherProvider):
    def __init__(self, registry):
        super().__init__(_CandidateList)
        for priority, group in registry.items():
            self[priority] = group

    def __setitem__(self, priority, group):
        # Always retain the complete registry, even if installation occurs in
        # an active event context.
        if type(group) is not _CandidateList:
            group = _CandidateList(list.__iter__(group))
        super().__setitem__(priority, group)

    def setdefault(self, priority, default=None):
        if priority not in self:
            self[priority] = [] if default is None else default
        return self[priority]

    def update(self, registry=(), **kwargs):
        entries = registry.items() if hasattr(registry, "items") else registry
        for priority, group in entries:
            self[priority] = group
        for priority, group in kwargs.items():
            self[priority] = group


async def _bind_dispatch_context(original, bot, event, state, stack=None,
                                 dependency_cache=None, show_log=True):
    allowed = await original(bot, event, state, stack, dependency_cache, show_log)
    if allowed and stack is not None:
        token = _dispatch_context.set(_DispatchContext(
            state, asyncio.current_task(), event.get_type() == "message"
        ))
        stack.callback(_dispatch_context.reset, token)
    return allowed


def install_command_dispatch() -> bool:
    """Install once; refuse to replace another plugin's provider."""
    if type(matchers.provider) is CommandMatcherProvider:
        return False
    if type(matchers.provider) is not DEFAULT_PROVIDER_CLASS:
        raise RuntimeError("CommandDispatch requires the default MatcherProvider")
    original = message_dispatch._apply_event_preprocessors
    original_trie = TrieRule.get_value

    @wraps(original)
    async def preprocess(bot, event, state, stack=None, dependency_cache=None,
                         show_log=True):
        return await _bind_dispatch_context(
            original, bot, event, state, stack, dependency_cache, show_log
        )

    @wraps(original_trie)
    def parse(cls, bot, event, state):
        result = original_trie(bot, event, state)
        context = _dispatch_context.get()
        if (context is not None and context.state is state
                and _is_owner(context)):
            context.parsed = True
        return result

    matchers.set_provider(CommandMatcherProvider)
    message_dispatch._apply_event_preprocessors = preprocess
    # Trie initializes a None prefix before parsing and can then raise. Mark
    # completion only on success so that failed parsing dispatches all entries.
    TrieRule.get_value = classmethod(parse)
    return True


@get_driver().on_startup
async def _optimize_command_dispatch() -> None:
    installed = install_command_dispatch()
    logger.info(f"[CommandDispatch] candidate provider installed={installed}")
