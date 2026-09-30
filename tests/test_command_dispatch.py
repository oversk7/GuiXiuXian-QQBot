"""Command filtering keeps native matching and leaves custom rules intact."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.consts import CMD_ARG_KEY, CMD_KEY, CMD_WHITESPACE_KEY, PREFIX_KEY
from nonebot.rule import CommandRule, Rule

from plugins.xiuxian_game import command_dispatch
from plugins.xiuxian_game.command_dispatch import CommandDispatchRule


def _state(command, argument="", whitespace=None):
    return {PREFIX_KEY: {
        CMD_KEY: command,
        CMD_ARG_KEY: Message(argument),
        CMD_WHITESPACE_KEY: whitespace,
    }}


@pytest.mark.parametrize("command,argument,whitespace,force", [
    (("sign",), "", None, None),
    (("checkin",), "", None, None),
    (("other",), "", None, None),
    (None, "", None, None),
    (("sign",), "5", None, True),
    (("sign",), "5", " ", True),
    (("sign",), "5", " ", False),
    (("sign",), "5", " ", " "),
    (("sign",), "5", "\t", " "),
    (("sign", "sub"), "", None, None),
])
async def test_matches_native_command_rules(command, argument, whitespace, force):
    checker = CommandRule([("sign",), ("checkin",), ("sign", "sub")], force)
    state = _state(command, argument, whitespace)
    original = Rule(checker)
    optimized = CommandDispatchRule(*original.checkers)
    assert await optimized(None, None, state, dependency_cache={}) == await original(
        None, None, state, dependency_cache={}
    )


async def test_unrelated_commands_skip_dependency_task_creation(monkeypatch):
    original = Rule(CommandRule([("sign",)]))
    optimized = CommandDispatchRule(*original.checkers)
    check = AsyncMock(return_value=True)
    monkeypatch.setattr(Rule, "__call__", check)
    assert not await optimized(None, None, _state(("other",)))
    assert not await optimized(None, None, _state(None))
    check.assert_not_awaited()
    assert await optimized(None, None, _state(("sign",)))
    check.assert_awaited_once()


@pytest.mark.parametrize("state", [{}, {PREFIX_KEY: {}}, {PREFIX_KEY: None},
                                  {PREFIX_KEY: {CMD_KEY: "sign"}}])
async def test_unknown_prefix_format_uses_native_path(monkeypatch, state):
    original = Rule(CommandRule([("sign",)]))
    optimized = CommandDispatchRule(*original.checkers)
    check = AsyncMock(return_value=False)
    monkeypatch.setattr(Rule, "__call__", check)
    assert not await optimized(None, None, state)
    check.assert_awaited_once()


async def test_rule_modified_after_startup_uses_native_path(monkeypatch):
    original = Rule(CommandRule([("sign",)]))
    optimized = CommandDispatchRule(*original.checkers)
    async def custom():
        return True
    optimized.checkers.update(Rule(custom).checkers)
    check = AsyncMock(return_value=False)
    monkeypatch.setattr(Rule, "__call__", check)
    assert not await optimized(None, None, _state(("other",)))
    check.assert_awaited_once()


def test_installer_scope_custom_rules_and_idempotence(monkeypatch):
    class CustomCommand(CommandRule):
        pass
    class CustomRule(Rule):
        pass
    async def custom():
        return True
    def matcher(rule, module="plugins.xiuxian_game.player"):
        return SimpleNamespace(rule=rule, module_name=module, plugin_name=None)
    native = matcher(Rule(CommandRule([("sign",)])))
    same_command = matcher(Rule(CommandRule([("sign",)])))
    other = matcher(Rule(CommandRule([("sign",)])), "plugins.other")
    composite = matcher(Rule(CommandRule([("sign",)]), custom))
    custom_command = matcher(Rule(CustomCommand([("sign",)])))
    custom_rule = matcher(CustomRule(CommandRule([("sign",)])))
    listener = matcher(Rule())
    untouched = [other, composite, custom_command, custom_rule, listener]
    old_rules = [item.rule for item in untouched]
    monkeypatch.setattr(command_dispatch, "matchers", {
        5: [native, same_command, *untouched],
    })
    assert command_dispatch.optimize_command_rules() == 2
    assert isinstance(native.rule, CommandDispatchRule)
    assert isinstance(same_command.rule, CommandDispatchRule)
    assert [item.rule for item in untouched] == old_rules
    assert command_dispatch.optimize_command_rules() == 0
