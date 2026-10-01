"""Command filtering keeps native matching and leaves custom rules intact."""

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.adapters.qq import Message
from nonebot.consts import CMD_ARG_KEY, CMD_KEY, CMD_WHITESPACE_KEY, PREFIX_KEY
import nonebot.message as message_dispatch
from nonebot.matcher import DEFAULT_PROVIDER_CLASS, Matcher, MatcherSource, matchers
from nonebot.permission import Permission, SUPERUSER
from nonebot.rule import CommandRule, Rule, TrieRule, command, regex, startswith
from nonebot.typing import T_State

from plugins.xiuxian_game import command_dispatch
from plugins.xiuxian_game.command_dispatch import CommandDispatchRule


_project_layers = {
    priority: tuple(list.__iter__(group)) for priority, group in matchers.items()
}


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


@pytest.fixture
def dispatch(monkeypatch):
    monkeypatch.setattr(matchers, "provider", DEFAULT_PROVIDER_CLASS({}))
    monkeypatch.setattr(message_dispatch, "_apply_event_preprocessors",
                        message_dispatch._apply_event_preprocessors)
    monkeypatch.setattr(TrieRule, "get_value", TrieRule.__dict__["get_value"])
    for name in ("_event_preprocessors", "_event_postprocessors",
                 "_run_preprocessors", "_run_postprocessors"):
        monkeypatch.setattr(message_dispatch, name, set())
    monkeypatch.setattr(TrieRule, "prefix", TrieRule.prefix.__class__())
    calls = []
    original = message_dispatch.check_and_run_matcher

    async def counted(matcher, bot, event, *args):
        calls.append((event.text, matcher))
        await original(matcher, bot, event, *args)

    monkeypatch.setattr(message_dispatch, "check_and_run_matcher", counted)
    assert command_dispatch.install_command_dispatch()
    assert not command_dispatch.install_command_dispatch()
    return calls


def _matcher(rule, handler=None, priority=5, **kwargs):
    source = MatcherSource(module_name="plugins.xiuxian_game.player")
    return Matcher.new(type_="message", rule=rule, priority=priority,
                       source=source, handlers=[handler] if handler else [], **kwargs)


def _event(text, type_="message"):
    return SimpleNamespace(
        text=text, get_type=lambda: type_, get_message=lambda: Message(text),
        get_log_string=lambda: text, get_event_name=lambda: type_,
        get_session_id=lambda: text, get_plaintext=lambda: text,
        get_user_id=lambda: "user",
    )


async def _dispatch(text, type_="message"):
    await message_dispatch.handle_event(
        SimpleNamespace(type="test", self_id="bot",
                        config=SimpleNamespace(superusers=set()),
                        adapter=SimpleNamespace(get_name=lambda: "test")),
        _event(text, type_)
    )


@pytest.mark.parametrize("text,expected", [
    ("/sign", True), ("/checkin", True), ("/sign.sub", True),
    ("/sign5", False), ("/sign 5", True), ("chat", False),
])
async def test_real_dispatch_reduces_outer_tasks_and_keeps_native_rules(
    dispatch, text, expected
):
    ran = []
    async def handler():
        ran.append(True)
    target = _matcher(command("sign", "checkin", ("sign", "sub"),
                              force_whitespace=True), handler)
    for i in range(40):
        _matcher(command(f"unrelated{i}"))
    fallback = _matcher(Rule())
    await _dispatch(text)
    assert [m for _, m in dispatch] == ([target, fallback] if text != "chat" else [fallback])
    assert bool(ran) == expected
    assert len(list(matchers[5])) == 42
    assert command_dispatch._dispatch_context.get() is None
    assert type(target.rule) is Rule


async def test_same_priority_concurrency_block_and_handler_registry(dispatch):
    entered = asyncio.Event()
    registry = []
    ran = []
    async def first():
        registry.extend(matchers[5])
        await entered.wait()
        ran.append("first")
    async def second():
        entered.set()
        ran.append("second")
    a = _matcher(command("go"), first, block=True)
    b = _matcher(command("go"), second)
    unrelated = _matcher(command("other"))
    lower = _matcher(command("go"), priority=7)
    await asyncio.wait_for(_dispatch("/go"), 3)
    assert set(ran) == {"first", "second"}
    assert registry == [a, b, unrelated]
    assert [m for _, m in dispatch] == [a, b]
    assert lower not in [m for _, m in dispatch]


async def test_sync_handler_reads_full_registry(dispatch):
    registry = []
    def handler():
        registry.extend(matchers[5])
    target = _matcher(command("go"), handler)
    other = _matcher(command("other"))
    await _dispatch("/go")
    assert registry == [target, other]
    assert dispatch == [("/go", target)]


async def test_buy_priority_false_then_true_and_permission_side_effect(dispatch):
    ran = []
    effects = []
    async def false_rule():
        effects.append("rule")
        return False
    async def permission():
        effects.append("permission")
        return True
    async def handler():
        ran.append("buy")
    first = _matcher(command("购买") & false_rule, priority=5, block=True)
    protected = _matcher(command("unrelated"), permission=Permission(permission))
    unrelated = _matcher(command("other"))
    second = _matcher(command("购买"), handler, priority=7, block=True)
    await _dispatch("/购买")
    assert [m for _, m in dispatch] == [first, protected, unrelated, second]
    assert effects == ["permission", "rule"] or effects == ["rule", "permission"]
    assert ran == ["buy"]


async def test_dynamic_registration_and_rule_mutations(dispatch):
    effects = []
    async def side_effect():
        effects.append(True)
        return True
    a = _matcher(command("other"))
    b = _matcher(command("other2"))
    await _dispatch("/go")
    assert dispatch == []
    a.rule.checkers.update(Rule(side_effect).checkers)
    b.rule = command("go")
    temporary = _matcher(command("other"), temp=True)
    expired = _matcher(command("other"), expire_time=datetime.now() - timedelta(seconds=1))
    await _dispatch("/go")
    assert [m for _, m in dispatch] == [a, b, temporary, expired]
    assert effects == [True]
    assert expired not in list(matchers[5])
    # Same length checker replacement, in-place command mutation, and removal.
    a.rule.checkers = command("go").checkers
    command("new")  # Native Trie registration is separate from rule mutation.
    next(iter(b.rule.checkers)).call.cmds = (("new",),)
    temporary.destroy()
    fresh = _matcher(command("go"))
    dispatch.clear()
    await _dispatch("/go")
    assert [m for _, m in dispatch] == [a, fresh]
    matchers[5][:] = [b, a]
    dispatch.clear()
    await _dispatch("/new")
    assert [m for _, m in dispatch] == [b]


async def test_fallback_scope_and_extra_dependencies(dispatch):
    from nonebot.dependencies import Dependent
    from nonebot.params import Depends
    effects = []
    async def extra():
        effects.append(True)
    composite = _matcher(command("other") & extra)
    other_plugin = _matcher(command("other"))
    other_plugin._source = MatcherSource(module_name="plugins.other")
    custom = _matcher(command("other"))
    async def custom_check(cls, *args):
        effects.append(True)
        return False
    custom.check_rule = classmethod(custom_check)
    dep = Dependent.parse(call=CommandRule([("other",)]),
                          parameterless=[Depends(extra)],
                          allow_types=Rule.HANDLER_PARAM_TYPES)
    extra_dep = _matcher(Rule(dep))
    listener = _matcher(Rule())
    unrelated = _matcher(command("never"))
    await _dispatch("chat")
    assert [m for _, m in dispatch] == [composite, other_plugin, custom, extra_dep, listener, unrelated]
    assert len(effects) == 3


async def test_context_isolation_nested_cleanup_and_nonmessage(dispatch, monkeypatch):
    a = _matcher(command("a"))
    b = _matcher(command("b"))
    await asyncio.gather(_dispatch("/a"), _dispatch("/b"))
    assert set(dispatch) == {("/a", a), ("/b", b)}
    assert command_dispatch._dispatch_context.get() is None
    dispatch.clear()
    await _dispatch("notice", "notice")
    assert [m for _, m in dispatch] == [a, b]
    # Failed Trie parsing leaves a None prefix; it must still enumerate all.
    event = _event("broken")
    def broken():
        raise ValueError("broken message")
    event.get_message = broken
    dispatch.clear()
    await message_dispatch.handle_event(SimpleNamespace(type="test", self_id="bot"), event)
    assert [m for _, m in dispatch] == [a, b]
    assert command_dispatch._dispatch_context.get() is None

    async def allowed(*args):
        return True
    async with AsyncExitStack() as outer:
        await command_dispatch._bind_dispatch_context(allowed, None, _event("a"), {}, outer)
        parent = command_dispatch._dispatch_context.get()
        async with AsyncExitStack() as inner:
            await command_dispatch._bind_dispatch_context(allowed, None, _event("b"), {}, inner)
            assert command_dispatch._dispatch_context.get() is not parent
        assert command_dispatch._dispatch_context.get() is parent
    assert command_dispatch._dispatch_context.get() is None
    async def denied(*args):
        return False
    async with AsyncExitStack() as stack:
        assert not await command_dispatch._bind_dispatch_context(denied, None, _event("a"), {}, stack)
        assert command_dispatch._dispatch_context.get() is None
    await command_dispatch._bind_dispatch_context(allowed, None, _event("a"), {})
    assert command_dispatch._dispatch_context.get() is None


@pytest.mark.parametrize("prefix", [None, {}, {CMD_KEY: "bad"},
                                   {CMD_KEY: ([],)}])
async def test_invalid_prefix_enumerates_full_registry(dispatch, prefix):
    a = _matcher(command("a"))
    context = command_dispatch._DispatchContext(
        {PREFIX_KEY: prefix}, asyncio.current_task(), True, parsed=True
    )
    token = command_dispatch._dispatch_context.set(context)
    try:
        assert list(matchers[5]) == [a]
    finally:
        command_dispatch._dispatch_context.reset(token)


async def test_ignored_preprocessor_does_not_bind_context(dispatch):
    from nonebot.exception import IgnoredException
    @message_dispatch.event_preprocessor
    async def ignore():
        raise IgnoredException("ignored")
    _matcher(command("a"))
    await _dispatch("/a")
    assert dispatch == []
    assert command_dispatch._dispatch_context.get() is None


async def test_same_layer_changes_from_previous_priority(dispatch):
    target = _matcher(command("other"), priority=7)
    async def mutate():
        target.rule = command("go")
        _matcher(command("go"), priority=7)
    first = _matcher(command("go"), mutate, priority=5)
    await _dispatch("/go")
    assert [m.priority for _, m in dispatch] == [5, 7, 7]
    assert [m for _, m in dispatch][:2] == [first, target]


async def test_temporary_hit_destroy_and_registry_update(dispatch):
    temporary = _matcher(command("go"), temp=True)
    await _dispatch("/go")
    assert dispatch == [("/go", temporary)]
    assert temporary not in matchers[5]
    normal = _matcher(command("go"), priority=7)
    matchers.update({5: [normal, normal]})
    assert list(matchers[5]) == [normal, normal]
    matchers[7].remove(normal)
    dispatch.clear()
    await _dispatch("/go")
    assert [m for _, m in dispatch] == [normal, normal]


@pytest.mark.parametrize("override", [False, True])
async def test_shared_prefix_rewrite_matches_native_dispatch(dispatch, monkeypatch, override):
    changed = asyncio.Event()
    ran = []
    async def rewrite(state: T_State):
        state[PREFIX_KEY][CMD_KEY] = ("new",)
        changed.set()
        return False
    writer = _matcher(Rule(rewrite))
    if override:
        writer.rule = Rule()
        async def check_rule(cls, bot, event, state, *args):
            return await rewrite(state)
        writer.check_rule = classmethod(check_rule)
    async def handler():
        ran.append("new")
    target = _matcher(command("new"), handler)
    unrelated = _matcher(command("other"))
    counted = message_dispatch.check_and_run_matcher
    async def ordered(matcher, *args):
        if matcher is target:
            await changed.wait()
        await counted(matcher, *args)
    monkeypatch.setattr(message_dispatch, "check_and_run_matcher", ordered)
    protected = matchers.provider
    # Use the same native handle_event and matchers for both providers. The
    # gate makes the shared-state write happen before the target checks it.
    monkeypatch.setattr(matchers, "provider", DEFAULT_PROVIDER_CLASS(protected))
    await _dispatch("chat")
    native_calls, native_ran = list(dispatch), list(ran)
    assert native_ran == ["new"]
    monkeypatch.setattr(matchers, "provider", protected)
    dispatch.clear()
    ran.clear()
    changed.clear()
    await _dispatch("chat")
    assert len(dispatch) == len(native_calls) == 3
    assert set(dispatch) == set(native_calls) == {
        ("chat", m) for m in (writer, target, unrelated)
    }
    assert ran == native_ran


async def test_native_listeners_and_permissions_keep_layer_indexed(dispatch):
    from nonebot.adapters.qq.permission import GROUP_MEMBER
    target = _matcher(command("go"))
    _matcher(command("other"))
    regex_listener = _matcher(regex("^/go$"))
    composite = _matcher(startswith("/go") & regex("go"))
    listener = _matcher(Rule())
    protected = _matcher(command("admin"), permission=SUPERUSER | GROUP_MEMBER)
    await _dispatch("/go")
    assert [m for _, m in dispatch] == [target, regex_listener, composite, listener, protected]
    assert all(command_dispatch._unsafe_layer_reason(m) is None for m in matchers[5])


@pytest.mark.parametrize("kind", ["permission", "check_perm", "rule_subclass", "dependency"])
async def test_unknown_checks_disable_only_their_layer(dispatch, kind):
    from nonebot.dependencies import Dependent
    from nonebot.params import Depends
    async def custom():
        return False
    unsafe = _matcher(Rule())
    if kind == "permission":
        unsafe.permission = Permission(custom)
    elif kind == "check_perm":
        async def check_perm(cls, *args):
            return False
        unsafe.check_perm = classmethod(check_perm)
    elif kind == "rule_subclass":
        class CustomRule(Rule):
            pass
        unsafe.rule = CustomRule()
    else:
        dep = Dependent.parse(call=next(iter(regex("go").checkers)).call,
                              parameterless=[Depends(custom)],
                              allow_types=Rule.HANDLER_PARAM_TYPES)
        unsafe.rule = Rule(dep)
    unrelated = _matcher(command("other"))
    later = _matcher(command("go"), priority=7)
    _matcher(command("later_other"), priority=7)
    await _dispatch("/go")
    assert [m for _, m in dispatch] == [unsafe, unrelated, later]
    assert command_dispatch._unsafe_layer_reason(unsafe) is not None


async def test_command_prefix_is_reread_at_each_priority(dispatch):
    async def rewrite(state: T_State):
        state[PREFIX_KEY][CMD_KEY] = ("new",)
        return False
    writer = _matcher(Rule(rewrite), priority=5)
    target = _matcher(command("new"), priority=7)
    _matcher(command("other"), priority=7)
    await _dispatch("chat")
    assert [m for _, m in dispatch] == [writer, target]


@pytest.mark.parametrize("parsed_command", [None, ("购买",)])
async def test_actual_project_layers_keep_candidate_filtering(parsed_command):
    token = command_dispatch._dispatch_context.set(command_dispatch._DispatchContext(
        _state(parsed_command), asyncio.current_task(), True, parsed=True
    ))
    try:
        for priority, group in _project_layers.items():
            unsafe = [(m.module_name, command_dispatch._unsafe_layer_reason(m))
                      for m in group if command_dispatch._unsafe_layer_reason(m)]
            assert not unsafe, (priority, unsafe)
            candidates = command_dispatch._CandidateList(group)
            expected = []
            for matcher in group:
                commands = command_dispatch._index_commands(matcher)
                if commands is None or parsed_command in commands:
                    expected.append(matcher)
            assert list(candidates) == expected, priority
        for priority in (5, 7, 13):
            group = _project_layers[priority]
            assert sum(command_dispatch._index_commands(m) is not None for m in group) > len(group) * 0.9
    finally:
        command_dispatch._dispatch_context.reset(token)


def test_provider_refuses_existing_custom_provider(monkeypatch):
    class OtherProvider(DEFAULT_PROVIDER_CLASS):
        pass
    provider = OtherProvider({})
    monkeypatch.setattr(matchers, "provider", provider)
    with pytest.raises(RuntimeError, match="default MatcherProvider"):
        command_dispatch.install_command_dispatch()
    assert matchers.provider is provider
