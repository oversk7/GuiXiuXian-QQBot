"""作者工具回归：非法输入可报告，离线执行遵循线上共享规则。"""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

STORY_DIR = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game" / "story"
SPEC = importlib.util.spec_from_file_location("offline_story_debugger_test", STORY_DIR / "story_debugger.py")
debugger_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(debugger_module)


def story(nodes=None):
    return {"id": "测试试炼", "title": "测试", "description": "回归", "start_node": "start", "nodes": nodes or {
        "start": {"type": "story", "content": "开始", "next": "end"}, "end": {"type": "end"}}}


@pytest.fixture
def save_story(tmp_path):
    def save(data):
        path = tmp_path / "test.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path
    return save


def check(path):
    checker = debugger_module.StoryDebugger(str(path))
    result = checker.run_full_check()
    report = checker.generate_report()
    assert "Story Debugger 报告" in report
    return result, checker


@pytest.mark.parametrize("data", [[], None, 1, "bad", {}, {"nodes": []}, {"nodes": {"start": []}},
                                    {"id": [], "start_node": [], "nodes": {"start": {"type": []}}}])
def test_invalid_structures_produce_reports(save_story, data):
    result, checker = check(save_story(data))
    assert not result and checker.errors


@pytest.mark.parametrize("node", [[], "bad", None, {"type": []}, {"type": "story", "next": 3},
                                     {"type": "choice", "options": [None]},
                                     {"type": "choice", "options": [{"id": [], "text": [], "next": []}]}])
def test_invalid_node_and_option_shapes_do_not_crash(save_story, node):
    data = story()
    data["nodes"]["start"] = node
    assert not check(save_story(data))[0]


@pytest.mark.parametrize("path", sorted((STORY_DIR.parent / "data" / "stories").glob("*.json")), ids=lambda path: path.name)
def test_shipped_stories_pass_full_static_check(path):
    result, checker = check(path)
    assert result, checker.generate_report()


def test_load_and_invalid_json_report_without_writing(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text("{", encoding="utf-8")
    assert not check(path)[0]
    assert not check(tmp_path / "missing.json")[0]
    assert sorted(file.name for file in tmp_path.iterdir()) == ["broken.json"]


def test_optional_metadata_and_repeated_checks(save_story):
    data = story()
    del data["title"], data["description"]
    path = save_story(data)
    result, checker = check(path)
    assert result
    data["nodes"]["start"]["next"] = "missing"
    save_story(data)
    assert not checker.run_full_check()
    data["nodes"]["start"]["next"] = "end"
    save_story(data)
    assert checker.run_full_check()
    assert not checker.errors and not checker.warnings


@pytest.mark.parametrize("next_field", [[{"if": {"player_level": 1}, "goto": "end"}],
                                          [{"if": {"or": [{"flag": {"unknown": True}}]}, "goto": "end"}],
                                          [{"if": {"flag": {"in": 1}}, "goto": "end"}]])
def test_option_route_conditions_are_validated(save_story, next_field):
    data = story({"start": {"type": "choice", "options": [{"id": 1, "text": "继续", "next": next_field}]},
                  "end": {"type": "end"}})
    result, checker = check(save_story(data))
    assert not result
    assert any("选项 1" in error and "分支 1" in error for error in checker.errors)


@pytest.mark.parametrize("changes", [{"player": {"gold": "+abc"}}, {"variables": []},
                                       {"player": {"gold": "100"}}, {"trial_success": "true"},
                                       {"player": {"not_an_attribute": 10}}, {"player": {"hp": 1.5}},
                                       {"player": {"nickname": "+1"}}, {"player": {"extra_attrs": "broken"}}])
def test_invalid_effects_are_rejected(save_story, changes):
    data = story()
    data["nodes"]["start"]["effects"] = changes
    assert not check(save_story(data))[0]


def test_misplaced_effects_and_missing_image_warn(save_story):
    data = story()
    data["nodes"]["start"]["image"] = "missing.png"
    data["nodes"]["end"]["effects"] = {"player": {"gold": "+1"}, "variables": {"perfect_ending": True}}
    result, checker = check(save_story(data))
    assert result
    assert any("不会执行" in warning for warning in checker.warnings)
    assert any("配图文件不存在" in warning for warning in checker.warnings)


def test_invalid_image_path_does_not_crash(save_story):
    data = story()
    data["nodes"]["start"]["image"] = "bad\u0000name.png"
    result, checker = check(save_story(data))
    assert result and any("路径无效" in warning for warning in checker.warnings)


def test_story_options_are_not_counted_as_executable_edges(save_story):
    data = story()
    data["nodes"]["start"].pop("next")
    data["nodes"]["start"]["options"] = [{"id": 1, "text": "继续", "next": "end"}]
    result, checker = check(save_story(data))
    assert not result
    assert any("story 节点不能使用 options" in error for error in checker.errors)
    assert any("无法到达任何结束节点" in error for error in checker.errors)


def test_closed_loop_detected_even_with_other_reachable_ending(save_story):
    nodes = {"start": {"type": "choice", "options": [
        {"id": 1, "text": "结局", "next": "end"}, {"id": 2, "text": "循环", "next": "loop"}]},
        "loop": {"type": "story", "next": "loop"}, "end": {"type": "end"}}
    result, checker = check(save_story(story(nodes)))
    assert not result
    assert any("无出口循环" in error and "loop" in error for error in checker.errors)
    nodes["loop"] = {"type": "choice", "options": [
        {"id": 1, "text": "再次", "next": "loop"}, {"id": 2, "text": "结束", "next": "end"}]}
    assert check(save_story(story(nodes)))[0]


def test_default_branch_prunes_unexecutable_paths(save_story):
    data = story()
    data["nodes"]["start"]["next"] = [{"goto": "end"}, {"goto": "missing"}]
    result, checker = check(save_story(data))
    assert result
    assert any("永远不会执行" in warning for warning in checker.warnings)


def test_interactive_effects_filtered_choices_and_perfect_completion(save_story, capsys):
    data = story({
        "start": {"type": "story", "content": "{player_gold} {flag}",
                  "effects": {"player": {"gold": "+10"}, "variables": {"flag": True}},
                  "next": [{"if": {"story_flag": {"==": True}}, "goto": "choice"}, {"goto": "end"}]},
        "choice": {"type": "choice", "content": "选择", "options": [
            {"id": 1, "text": "锁定选项", "conditions": {"player_level": {">=": 10}}, "next": "end"},
            {"id": 2, "text": "完美结局", "effects": {"variables": {"perfect_ending": True}},
             "next": [{"if": {"story_perfect_ending": {"==": True}}, "goto": "end"}]}]},
        "end": {"type": "end", "effects": {"trial_success": True, "player": {"gold": "+99"}}},
    })
    tool = debugger_module.InteractiveDebugger(str(save_story(data)), {"gold": 0, "level": 1})
    assert tool.load()
    capsys.readouterr()
    tool._next_node()
    assert tool.current_node == "choice" and tool.player_state["gold"] == 10 and tool.variables["flag"] is True
    capsys.readouterr()
    tool._show_node()
    shown = capsys.readouterr().out
    assert "锁定选项" not in shown and "完美结局" in shown
    tool._choose_option(1)
    assert tool.current_node == "choice" and tool.player_state["gold"] == 10
    tool._choose_option(2)
    assert tool.finished and tool.current_node == "end"
    assert tool.player_state["completed_trials"] == ["测试试炼_完美"]
    assert tool.player_state["gold"] == 10  # 结束节点中的普通效果与线上一样不执行。
    tool._choose_option(2)
    tool._next_node()
    assert tool.player_state["gold"] == 10 and len(tool.history) == 2
    tool.restart()
    assert not tool.finished and tool.current_node == "start"
    assert tool.player_state["gold"] == 0 and tool.player_state["completed_trials"] == []
    assert tool.variables == {"current_story_id": "测试试炼"} and tool.history == []


def test_permanent_limits_clamp_resources_before_routing(save_story):
    data = story()
    data["nodes"]["start"].update(
        effects={"player": {"max_hp": "-10", "max_mp": "-5"}},
        next=[{"if": {"player_hp": {"==": 10}, "player_mp": {"==": 15}}, "goto": "end"},
              {"goto": "wrong"}],
    )
    data["nodes"]["wrong"] = {"type": "end"}
    tool = debugger_module.InteractiveDebugger(str(save_story(data)), {"hp": 20, "max_hp": 20, "mp": 20, "max_mp": 20})
    assert tool.load()
    tool._next_node()
    assert tool.current_node == "end"
    assert tool.player_state["hp"] == tool.player_state["max_hp"] == 10
    assert tool.player_state["mp"] == tool.player_state["max_mp"] == 15


def test_unusual_numeric_commands_do_not_crash(save_story, monkeypatch):
    tool = debugger_module.InteractiveDebugger(str(save_story(story())))
    assert tool.load()
    commands = iter(["²", "9" * 5000, "０", "q"])
    monkeypatch.setattr("builtins.input", lambda _: next(commands))
    tool.run()
    assert tool.current_node == "start"


def test_render_does_not_apply_effects_and_edits_support_lists(save_story, capsys):
    data = story()
    data["nodes"]["start"].update(content="金币 {player_gold}，标记 {flag}", effects={"player": {"gold": "+5"}})
    tool = debugger_module.InteractiveDebugger(str(save_story(data)), {"gold": 0})
    assert tool.load()
    tool._edit_variable('flag="开始"')
    capsys.readouterr()
    tool._show_node()
    tool._show_node()
    shown = capsys.readouterr().out
    assert "金币 0，标记 开始" in shown
    assert tool.player_state["gold"] == 0
    tool._edit_player('completed_trials=["测试试炼"]')
    assert tool.player_state["completed_trials"] == ["测试试炼"]
    tool._edit_player("completed_trials=123")
    assert tool.player_state["completed_trials"] == ["测试试炼"]
    tool._edit_player("gold=true")
    tool._edit_player("gold=1.5")
    assert tool.player_state["gold"] == 0
    tool._edit_player("guild_id=7")
    assert tool.player_state["guild_id"] == 7
    assert tool.player_state["extra_attrs"] == {}
    tool._edit_player('extra_attrs={"test":true}')
    assert tool.player_state["extra_attrs"] == {"test": True}
    assert debugger_module.PLAYER_DEFAULTS["extra_attrs"] == {}


@pytest.mark.parametrize("perfect", [False, True])
def test_real_marriage_first_and_repeat_rewards(perfect):
    path = STORY_DIR.parent / "data" / "stories" / "marriage.json"
    tool = debugger_module.InteractiveDebugger(str(path), {"gold": 0, "exp": 0, "agility": 0, "luck": 0})
    assert tool.load()
    entry = "end_perfect" if perfect else "end_success"
    tool.current_node = entry
    for _ in range(3):
        tool._next_node()
    assert tool.finished
    assert tool.player_state["gold"] == (120 if perfect else 80)
    assert tool.player_state["exp"] == (150 if perfect else 100)
    assert tool.player_state["agility"] == tool.player_state["luck"] == (2 if perfect else 1)
    assert tool.player_state["completed_trials"] == ["冥契红绳_完美" if perfect else "冥契红绳"]
    before = copy.deepcopy(tool.player_state)
    tool.finished = False
    tool.current_node = entry
    for _ in range(2):
        tool._next_node()
    assert tool.finished and tool.current_node == ("end_perfect_repeat" if perfect else "end_success_repeat")
    assert tool.player_state == before


def test_offline_player_reads_database_style_trial_json():
    state = {"completed_trials": json.dumps(["完整试炼名称"], ensure_ascii=False)}
    player = debugger_module.OfflinePlayer(state)
    assert player.get_completed_trials() == ["完整试炼名称"]
    player.add_completed_trial("另一试炼")
    player.add_completed_trial("另一试炼")
    assert player.get_completed_trials() == ["完整试炼名称", "另一试炼"]


def test_bom_encoded_story_and_cancelled_attribute_edit(save_story, monkeypatch):
    path = save_story(story())
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    tool = debugger_module.InteractiveDebugger(str(path))
    assert tool.load()
    monkeypatch.setattr("builtins.input", lambda _: (_ for _ in ()).throw(EOFError()))
    tool._edit_player()
    assert tool.player_state == tool.initial_player_state


def test_report_hard_link_cannot_overwrite_story(tmp_path):
    source = tmp_path / "story.json"
    original = json.dumps(story(), ensure_ascii=False)
    source.write_text(original, encoding="utf-8")
    link = tmp_path / "report.txt"
    try:
        os.link(source, link)
    except OSError as error:
        pytest.skip(f"当前文件系统不支持硬链接: {error}")
    with pytest.raises(SystemExit) as failure:
        debugger_module.main([str(source), "--report", str(link)])
    assert failure.value.code == 2
    assert source.read_text(encoding="utf-8") == original


def test_cli_batch_report_and_source_protection(tmp_path):
    path = tmp_path / "valid.json"
    original = json.dumps(story(), ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    (tmp_path / "invalid.json").write_text("[]", encoding="utf-8")
    tool_path = STORY_DIR / "story_debugger.py"
    result = subprocess.run([sys.executable, str(tool_path), str(tmp_path), "--check-all"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1
    assert "1 个通过，1 个失败" in result.stdout
    assert sorted(file.name for file in tmp_path.iterdir()) == ["invalid.json", "valid.json"]
    (tmp_path / "invalid.json").unlink()
    report = tmp_path / "reports" / "audit.txt"
    assert debugger_module.main([str(path), "--report", str(report)]) == 0
    assert "[PASS]" in report.read_text(encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        debugger_module.main([str(path), "--report", str(path)])
    assert error.value.code == 2 and path.read_text(encoding="utf-8") == original
