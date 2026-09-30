"""Skip unrelated command dependency checks using NoneBot's parsed command."""

from contextlib import AsyncExitStack

from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot.consts import CMD_KEY, PREFIX_KEY
from nonebot.matcher import matchers
from nonebot.rule import CommandRule, Rule
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


@get_driver().on_startup
async def _optimize_command_dispatch() -> None:
    count = optimize_command_rules()
    logger.info(f"[CommandDispatch] optimized={count} native command rules")
