"""文件加载纯运行器，隔离假包加载真实引擎，不导入机器人插件。"""
import asyncio
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

STORY_DIR = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game" / "story"


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runtime = load_file("isolated_story_runtime", STORY_DIR / "runtime.py")


class Player:
    INIT_ATTRS = {"luck"}

    def __init__(self, trials=()):
        self.trials = list(trials)
        self.nickname = "修士"
        self.level = 12
        self.gold = 100
        self.luck = 5
        self.guild_id = None

    def get_completed_trials(self):
        return self.trials.copy()

    def add_completed_trial(self, trial):
        self.trials.append(trial)

    def get_current_coordinates(self):
        return 7, 9


@pytest.fixture
def runner():
    return runtime.StoryRuntime()


@pytest.mark.parametrize("trials,trial,expected", [
    ([], "试炼", False), (["试炼"], "试炼", True),
    (["试炼_完美"], "试炼_完美", True), (["试炼"], "试炼_完美", False),
    (["试炼_完美"], "试炼", False),
])
def test_completed_trials_contains(runner, trials, trial, expected):
    assert runner.evaluate_condition({"player_completed_trials": {"contains": trial}}, Player(trials), {}) is expected


@pytest.mark.parametrize("value,check,expected", [
    (12, {">=": 10, "<": 15}, True), (12, {">=": 10, "<": 12}, False),
    (12, {">=": 10, "unknown": 1}, False), (12, {}, False),
    (12, {"unknown": 1}, False), (12, None, False),
    (12, {">": "1"}, False), (12, {"!=": "12"}, False),
    (None, {"!=": 1}, False), (None, {"==": None}, False),
    (["key"], {"contains": "key"}, True), ("abc", {"contains": "b"}, True),
    ({"key": 1}, {"contains": "key"}, True), (12, {"contains": 1}, False),
    ("a", {"in": ["a", "b"]}, True), ("a", {"not_in": ["b"]}, True),
    ("a", {"in": 1}, False), ("a", {"not_in": 1}, False),
    (12, {"==": 12.0}, True), (True, {"==": 1}, False),
    ({}, {">": {}}, False), (True, {">": False}, False),
    ([2], {">": [1]}, False),
])
def test_comparisons(runner, value, check, expected):
    assert runner._check_value(value, check) is expected


@pytest.mark.parametrize("condition", [None, [], "bad", {"and": {}}, {"or": None},
                                            {"missing": {"!=": 1}}, {"story_missing": {"==": None}},
                                            {"player_absent": {"==": 0}}])
def test_invalid_and_missing_conditions(runner, condition):
    assert runner.evaluate_condition(condition, Player(), {}) is False


def test_mixed_logic_requires_every_sibling(runner):
    condition = {"and": [{"player_level": {">=": 10}}],
                 "or": [{"flag": {"==": True}}, {"score": {">": 50}}],
                 "story_key": {"==": True}}
    assert runner.evaluate_condition(condition, Player(), {"flag": True, "key": True})
    assert not runner.evaluate_condition(condition, Player(), {"flag": True, "key": False})
    assert not runner.evaluate_condition(condition, Player(), {"flag": False, "key": True})
    assert runner.evaluate_condition({}, Player(), {})


def test_route_first_match_default_and_none(runner):
    branches = [{"if": None, "goto": "invalid"},
                {"if": {"flag": {"==": True}}, "goto": "first"},
                {"if": {"flag": {"==": True}}, "goto": "second"},
                {"goto": "default"}]
    assert runner.resolve_next(branches, Player(), {"flag": True}) == "first"
    assert runner.resolve_next(branches, Player(), {"flag": False}) == "default"
    assert runner.resolve_next(branches[:-1], Player(), {}) is None
    assert runner.resolve_next(None, Player(), {}) is None
    assert runner.resolve_next("direct", Player(), {}) == "direct"
    assert runner.resolve_next([{}, {"goto": "later"}], Player(), {}) is None


def test_variable_effects_and_changes_are_pure():
    before = {"score": 5, "keep": True}
    effects = {"variables": {"score": "-2", "new": "+3", "label": "完成"}}
    assert runtime.effect_changes({"score": "+4"}, before) == {"score": 9}
    assert runtime.apply_variable_effects(effects, before) == {"score": 3, "keep": True, "new": 3, "label": "完成"}
    assert before == {"score": 5, "keep": True}
    assert effects["variables"]["score"] == "-2"
    assert runtime.apply_variable_effects({}, before) == before
    assert runtime.apply_variable_effects({}, before) is not before


@pytest.mark.parametrize("perfect,expected", [(False, "试炼"), (True, "试炼_完美")])
def test_record_success_preserves_perfect_rule(perfect, expected):
    player = Player()
    variables = {"current_story_id": "试炼", "perfect_ending": perfect}
    runtime.record_trial_success({"trial_success": True}, player, variables)
    runtime.record_trial_success({"trial_success": True}, player, variables)
    assert player.trials == [expected]
    runtime.record_trial_success({"trial_success": False}, player, {"current_story_id": "其他"})
    runtime.record_trial_success({"trial_success": True}, player, {})
    assert player.trials == [expected]


def test_format_records_coordinates_all_fields_and_safe_defaults(runner):
    player = Player(["试炼_完美"])
    player.custom_field = "自定义"
    text = "{player_name}/{player_level}/{player_x},{player_y}/{player_guild_id}/{player_custom_field}/{flag}/{trial_completed_试炼}/{trial_completed_试炼_完美}/{player_completed_trials}/{unknown}"
    assert runner.format_content(text, player, {"flag": 3}) == "修士/12/7,9/无/自定义/3/False/True/['试炼_完美']/{unknown}"
    assert runner.format_content("{player_name}:{player_hp}:{player_x}:{trial_completed_试炼}", SimpleNamespace(), {}) == ":0:0:False"


def test_visible_options(runner):
    options = [{"id": 1}, {"id": 2, "conditions": {"player_completed_trials": {"contains": "试炼"}}},
               {"id": 3, "conditions": None}, "bad"]
    assert runner.visible_options({"options": options}, Player(), {}) == [options[0]]
    assert runner.visible_options({"options": options}, Player(["试炼"]), {}) == options[:2]
    assert runner.visible_options([], Player(), {}) == []
    assert runner.visible_options({"options": None}, Player(), {}) == []


@pytest.fixture
def engine_module(monkeypatch):
    # 假包仅提供依赖；执行真实 engine.py，继承真实 runtime.py。
    for name in ("story_test", "story_test.story", "story_test.models", "story_test.domain",
                 "story_test.domain.attributes", "sqlalchemy", "sqlalchemy.ext"):
        package = ModuleType(name)
        package.__path__ = []
        monkeypatch.setitem(sys.modules, name, package)
    for name, fields in {
        "story_test.models.player": {"Player": Player},
        "story_test.models.story_session": {"StorySession": SimpleNamespace},
        "sqlalchemy.ext.asyncio": {"AsyncSession": object},
        "story_test.domain.attributes.permanent_change": {
            "LEDGER_STORY_REWARD": "story_reward", "apply_permanent_change": AsyncMock()},
    }.items():
        module = ModuleType(name)
        module.__dict__.update(fields)
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, "story_test.story.runtime", runtime)
    return load_file("story_test.story.engine", STORY_DIR / "engine.py")


def make_engine(engine_module, story):
    engine = engine_module.StoryEngine.__new__(engine_module.StoryEngine)
    engine.get_story = lambda story_id: story
    return engine


def make_session():
    variables = {"score": 1}
    session = SimpleNamespace(story_id="试炼", current_node="start", get_variables=lambda: variables)
    session.set_variables = lambda new: (variables.clear(), variables.update(new))
    return session


def test_engine_inherits_runtime_and_filters_nodes(engine_module, monkeypatch):
    for method in ("evaluate_condition", "_check_value", "resolve_next", "format_content", "visible_options"):
        assert getattr(engine_module.StoryEngine, method) is getattr(runtime.StoryRuntime, method)
    option = {"id": 1}
    node = {"type": "choice", "content": "{player_name}", "options": [option]}
    engine = make_engine(engine_module, {"nodes": {"start": node}})
    calls = []
    monkeypatch.setattr(engine, "visible_options", lambda *args: calls.append(args) or [])
    assert engine.get_current_node(make_session(), Player()) == {"type": "choice", "content": "修士", "options": []}
    assert len(calls) == 1
    assert node["options"] == [option]


@pytest.mark.parametrize("story", [{"nodes": {"start": []}}, {"nodes": []}, {"nodes": {"start": "bad"}}, []])
def test_engine_rejects_malformed_nodes(engine_module, story):
    engine = make_engine(engine_module, story)
    assert engine.get_current_node(make_session(), Player()) is None
    assert asyncio.run(engine.process_choice(make_session(), Player(), 1))[0] is False


def test_engine_reads_bom_encoded_story(engine_module, tmp_path):
    path = tmp_path / "bom.json"
    path.write_text('{"id": "bom", "nodes": {"start": {"type": "end"}}}', encoding="utf-8-sig")
    engine = engine_module.StoryEngine.__new__(engine_module.StoryEngine)
    engine.story_dir = tmp_path
    engine._story_index = {}
    engine._story_meta = {}
    engine._build_index()
    assert engine.get_story("bom")["nodes"]["start"]["type"] == "end"


def test_engine_effects_keep_ledger_and_variable_helpers(engine_module, monkeypatch):
    engine = make_engine(engine_module, {})
    player = Player()
    variables = {"score": 1}
    session = object()
    effect_spy = []
    variable_spy = []
    original_changes = runtime.effect_changes
    original_variables = runtime.apply_variable_effects
    monkeypatch.setattr(engine_module, "effect_changes", lambda *args: effect_spy.append(args) or original_changes(*args))
    monkeypatch.setattr(engine_module, "apply_variable_effects", lambda *args: variable_spy.append(args) or original_variables(*args))
    _, result = asyncio.run(engine.apply_effects({"player": {"luck": "+2", "gold": "-10"}, "variables": {"score": "+4"}}, player, variables, session))
    ledger = sys.modules["story_test.domain.attributes.permanent_change"].apply_permanent_change
    ledger.assert_awaited_once_with(session, player, {"luck": 2}, ledger_item_id="story_reward")
    assert player.gold == 90 and player.luck == 5
    assert result == {"score": 5} and variables == {"score": 1}
    assert len(effect_spy) == len(variable_spy) == 1
    asyncio.run(engine.apply_effects({"player": {"luck": "+2"}}, player, {}, None))
    assert player.luck == 7


def test_engine_locked_choice_does_not_apply_effects(engine_module):
    option = {"id": 1, "conditions": {"player_completed_trials": {"contains": "试炼"}},
              "effects": {"player": {"gold": "+100"}}, "next": "end"}
    engine = make_engine(engine_module, {"nodes": {"start": {"type": "choice", "options": [option]}}})
    session = make_session()
    player = Player()
    assert engine.get_current_node(session, player)["options"] == []
    assert asyncio.run(engine.process_choice(session, player, 1)) == (False, "不满足选择条件", None)
    assert player.gold == 100 and session.current_node == "start"


def test_engine_choice_routes_after_effect_and_special_delegates(engine_module, monkeypatch):
    story = {"nodes": {"start": {"type": "choice", "options": [
        {"id": 1, "effects": {"variables": {"score": "+2"}}, "next": [
            {"if": {"score": {"==": 3}}, "goto": "end"}]}]},
        "end": {"type": "end", "content": "{score}"}}}
    engine = make_engine(engine_module, story)
    session = make_session()
    player = Player()
    assert asyncio.run(engine.process_choice(session, player, 1)) == (True, "选择成功", {"type": "end", "content": "3"})
    assert session.current_node == "end"
    calls = []
    original = runtime.record_trial_success
    monkeypatch.setattr(engine_module, "record_trial_success", lambda *args: calls.append(args) or original(*args))
    variables = {"current_story_id": "试炼", "perfect_ending": True}
    _, _, message = asyncio.run(engine.apply_special_effects({"trial_success": True}, player, variables, None))
    assert calls and player.trials == ["试炼_完美"] and message == ""
