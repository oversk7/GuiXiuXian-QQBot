"""试炼脚本检查与离线调试。只依赖 Python 标准库，不启动机器人或连接数据库。

python plugins/xiuxian_game/story/story_debugger.py <剧本.json>
python plugins/xiuxian_game/story/story_debugger.py <剧本.json> --interactive
python plugins/xiuxian_game/story/story_debugger.py --check-all
"""

import argparse
import ast
import copy
import importlib.util
import json
import re
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

# 直接运行脚本、按文件导入测试以及包内导入都使用同一个运行模块。
if __package__:
    from . import runtime
else:
    _spec = importlib.util.spec_from_file_location(
        "_story_debugger_runtime", Path(__file__).with_name("runtime.py")
    )
    runtime = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = runtime
    _spec.loader.exec_module(runtime)

STORIES_DIR = Path(__file__).parent.parent / "data" / "stories"
NODE_TYPES = frozenset({"story", "choice", "end"})
EFFECT_SECTIONS = frozenset({"player", "variables", "trial_success", "first_trial_reward", "rewards"})
RELATIVE_CHANGE = re.compile(r"^[+-]\d+$")
PLAYER_ATTRIBUTE_TYPES = {}
PERMANENT_ATTRIBUTES = {"max_hp", "max_mp", "attack", "defense", "agility", "luck"}


def player_defaults() -> dict[str, Any]:
    """从模型声明读取离线初值，避免导入游戏插件和数据库。"""
    defaults = {
        "nickname": "调试玩家", "uid": 1, "level": 1, "sex": "男", "region": "大都会",
        "gold": 1000, "hp": 20, "max_hp": 20, "mp": 20, "max_mp": 20,
        "attack": 1, "defense": 0, "agility": 5, "stamina": 10, "luck": 1,
        "resentment": 0, "exp": 0, "vip": 0, "completed_trials": [],
    }
    PLAYER_ATTRIBUTE_TYPES.update({name: type(value) for name, value in defaults.items()})
    model_file = Path(__file__).parent.parent / "models" / "player.py"
    if model_file.is_file():
        model = ast.parse(model_file.read_text(encoding="utf-8"))
        player_class = next(node for node in model.body if isinstance(node, ast.ClassDef) and node.name == "Player")
        for field in player_class.body:
            if isinstance(field, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "INIT_ATTRS" for target in field.targets):
                PERMANENT_ATTRIBUTES.clear()
                PERMANENT_ATTRIBUTES.update(ast.literal_eval(field.value))
            if not isinstance(field, ast.AnnAssign) or not isinstance(field.target, ast.Name):
                continue
            if not isinstance(field.value, ast.Call) or not isinstance(field.value.func, ast.Name):
                continue
            if field.value.func.id != "mapped_column":
                continue
            name = field.target.id
            annotation = ast.unparse(field.annotation)
            value = None
            if "Mapped[int" in annotation:
                value = 0
                PLAYER_ATTRIBUTE_TYPES[name] = int
            elif "Mapped[float" in annotation:
                value = 0.0
                PLAYER_ATTRIBUTE_TYPES[name] = float
            elif "Mapped[bool" in annotation:
                value = False
                PLAYER_ATTRIBUTE_TYPES[name] = bool
            elif "Mapped[str" in annotation:
                value = ""
                PLAYER_ATTRIBUTE_TYPES[name] = str
            elif "Mapped[dict" in annotation:
                value = {}
                PLAYER_ATTRIBUTE_TYPES[name] = dict
            elif "Mapped[list" in annotation:
                value = []
                PLAYER_ATTRIBUTE_TYPES[name] = list
            if "None" in annotation:
                value = None
            for keyword in field.value.keywords:
                if keyword.arg == "default":
                    try:
                        value = ast.literal_eval(keyword.value)
                    except (ValueError, TypeError):
                        factories = {"dict": dict, "list": list}
                        if isinstance(keyword.value, ast.Name) and keyword.value.id in factories:
                            value = factories[keyword.value.id]()
                        else:
                            value = defaults.get(name, value)
            defaults.setdefault(name, value)
    defaults["completed_trials"] = []
    return defaults


PLAYER_DEFAULTS = player_defaults()


def jump_targets(next_field: Any) -> list[str]:
    """提取实际可执行的跳转；默认分支之后的分支不会执行。"""
    if isinstance(next_field, str):
        return [next_field] if next_field else []
    targets = []
    if isinstance(next_field, list):
        for branch in next_field:
            if not isinstance(branch, dict):
                continue
            target = branch.get("goto")
            if isinstance(target, str) and target:
                targets.append(target)
            if "if" not in branch:
                break
    return targets


class StoryDebugger:
    """静态检查器；可达性表示可能的路径，不代表条件组合一定可满足。"""

    def __init__(self, story_file: str):
        self.story_file = str(story_file)
        self.story_data = {}
        self.nodes = {}
        self.errors = []
        self.warnings = []
        self.node_references = defaultdict(list)

    def load_story(self) -> bool:
        print(f"\n[1/7] 加载剧情文件: {self.story_file}")
        try:
            data = json.loads(Path(self.story_file).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            self.errors.append(f"加载失败: {error}")
            return False
        if not isinstance(data, dict):
            self.errors.append("剧情顶层必须是对象")
            return False
        self.story_data = data
        return True

    def validate_structure(self) -> bool:
        print("\n[2/7] 验证基本结构")
        for name in ("id", "start_node"):
            if not isinstance(self.story_data.get(name), str) or not self.story_data[name].strip():
                self.errors.append(f"{name} 必须是非空字符串")
        for name in ("title", "description"):
            if name in self.story_data and not isinstance(self.story_data[name], str):
                self.errors.append(f"{name} 必须是字符串")
        nodes = self.story_data.get("nodes")
        if not isinstance(nodes, dict) or not nodes:
            self.errors.append("nodes 必须是非空对象")
            return False
        self.nodes = nodes
        for node_id in nodes:
            if not isinstance(node_id, str) or not node_id:
                self.errors.append("节点ID必须是非空字符串")
        start = self.story_data.get("start_node")
        if isinstance(start, str) and start not in nodes:
            self.errors.append(f"起始节点不存在: {start}")
        return not self.errors

    def validate_nodes(self) -> bool:
        print("\n[3/7] 验证节点配置")
        for node_id, node in self.nodes.items():
            location = f"节点 '{node_id}'"
            if not isinstance(node, dict):
                self.errors.append(f"{location}: 必须是对象；条件路由数组应放在 next 中")
                continue
            node_type = node.get("type")
            if not isinstance(node_type, str) or node_type not in NODE_TYPES:
                self.errors.append(f"{location}: type 必须为 story、choice 或 end")
                continue
            if "content" in node and not isinstance(node["content"], str):
                self.errors.append(f"{location}: content 必须是字符串")
            elif "content" not in node and node_type != "end":
                self.warnings.append(f"{location}: 缺少 content 字段")
            if "image" in node:
                image = node["image"]
                if not isinstance(image, str) or not image:
                    self.errors.append(f"{location}: image 必须是非空字符串")
                else:
                    try:
                        image_exists = (Path(self.story_file).parent / image).is_file()
                    except (OSError, ValueError):
                        image_exists = False
                    if not image_exists:
                        self.warnings.append(f"{location}: 配图文件不存在或路径无效: {image}")
            if node_type == "story":
                if "options" in node:
                    self.errors.append(f"{location}: story 节点不能使用 options，请改为 choice")
                self._validate_jump(node.get("next"), location)
                self._collect_references(node_id, node.get("next"))
            elif node_type == "choice":
                options = node.get("options")
                if not isinstance(options, list) or not options:
                    self.errors.append(f"{location}: options 必须是非空列表")
                    continue
                if "next" in node:
                    self.warnings.append(f"{location}: choice 节点自身的 next 不会执行")
                option_ids = set()
                for index, option in enumerate(options, 1):
                    option_location = f"{location} 选项 {index}"
                    if not isinstance(option, dict):
                        self.errors.append(f"{option_location}: 必须是对象")
                        continue
                    option_id = option.get("id")
                    if type(option_id) is not int or not 1 <= option_id <= 9:
                        self.errors.append(f"{option_location}: id 必须是 1—9 的整数（游戏仅接收单个数字）")
                    elif option_id in option_ids:
                        self.errors.append(f"{option_location}: 选项ID重复: {option_id}")
                    else:
                        option_ids.add(option_id)
                    if not isinstance(option.get("text"), str) or not option["text"]:
                        self.errors.append(f"{option_location}: text 必须是非空字符串")
                    self._validate_jump(option.get("next"), option_location)
                    self._collect_references(node_id, option.get("next"))
            elif "next" in node or "options" in node:
                self.warnings.append(f"{location}: 结束节点中的 next/options 不会执行")
        return not self.errors

    def _validate_jump(self, next_field: Any, location: str):
        if isinstance(next_field, str) and next_field:
            return
        if not isinstance(next_field, list) or not next_field:
            self.errors.append(f"{location}: next 必须是非空节点ID或条件路由列表")
            return
        found_default = False
        for index, branch in enumerate(next_field, 1):
            branch_location = f"{location} next 分支 {index}"
            if not isinstance(branch, dict):
                self.errors.append(f"{branch_location}: 必须是对象")
                continue
            if not isinstance(branch.get("goto"), str) or not branch["goto"]:
                self.errors.append(f"{branch_location}: goto 必须是非空节点ID")
            if found_default:
                self.warnings.append(f"{branch_location}: 位于默认分支之后，永远不会执行")
            if "if" not in branch:
                found_default = True
        if not found_default:
            self.warnings.append(f"{location}: 条件跳转没有默认分支，条件均不满足时会停留原节点")

    def _collect_references(self, from_node: str, next_field: Any):
        for target in jump_targets(next_field):
            self.node_references[target].append(from_node)

    def check_references(self) -> bool:
        print("\n[4/7] 检查节点引用")
        for target, sources in self.node_references.items():
            if target not in self.nodes:
                self.errors.append(f"引用的节点不存在: '{target}' (被 {sources} 引用)")
        return not self.errors

    def _get_next_nodes(self, node: Any) -> list[str]:
        if not isinstance(node, dict):
            return []
        if node.get("type") == "story":
            return jump_targets(node.get("next"))
        if node.get("type") == "choice" and isinstance(node.get("options"), list):
            return [target for option in node["options"] if isinstance(option, dict)
                    for target in jump_targets(option.get("next"))]
        return []

    def analyze_paths(self) -> bool:
        print("\n[5/7] 分析剧情路径")
        start = self.story_data.get("start_node")
        if not isinstance(start, str) or start not in self.nodes:
            return False
        graph = {key: self._get_next_nodes(node) for key, node in self.nodes.items()}
        visited = set()
        queue = deque([start])
        while queue:
            node_id = queue.popleft()
            if node_id in visited or node_id not in self.nodes:
                continue
            visited.add(node_id)
            queue.extend(graph[node_id])
        ends = {key for key in visited if isinstance(self.nodes[key], dict)
                and self.nodes[key].get("type") == "end"}
        unreachable = sorted(set(self.nodes) - visited)
        if unreachable:
            self.warnings.append(f"不可达节点: {unreachable}")
        if not ends:
            self.errors.append("从起始节点无法到达任何结束节点")
        reverse = defaultdict(list)
        for source, targets in graph.items():
            for target in targets:
                reverse[target].append(source)
        can_finish = set()
        queue = deque(ends)
        while queue:
            node_id = queue.popleft()
            if node_id not in can_finish:
                can_finish.add(node_id)
                queue.extend(reverse[node_id])
        trapped = sorted(visited - can_finish)
        if trapped:
            self.errors.append(f"可达节点无法到达任何结局（含无出口循环或断路）: {trapped}")
        print(f"  可达节点: {len(visited)}/{len(self.nodes)}，可达结束节点: {len(ends)}")
        return not self.errors

    def validate_conditions(self) -> bool:
        print("\n[6/7] 验证条件语法")
        for node_id, node in self.nodes.items():
            if not isinstance(node, dict):
                continue
            location = f"节点 '{node_id}'"
            self._validate_jump_conditions(node.get("next"), location)
            options = node.get("options", [])
            if isinstance(options, list):
                for index, option in enumerate(options, 1):
                    if not isinstance(option, dict):
                        continue
                    option_location = f"{location} 选项 {index}"
                    if "conditions" in option:
                        self._validate_condition(option["conditions"], option_location)
                    self._validate_jump_conditions(option.get("next"), option_location)
        return not self.errors

    def _validate_jump_conditions(self, next_field: Any, location: str):
        if isinstance(next_field, list):
            for index, branch in enumerate(next_field, 1):
                if isinstance(branch, dict) and "if" in branch:
                    self._validate_condition(branch["if"], f"{location} next 分支 {index}")

    def _validate_condition(self, condition: Any, location: str):
        if not isinstance(condition, dict):
            self.errors.append(f"{location}: 条件必须是对象")
            return
        for key, check in condition.items():
            if key in ("and", "or"):
                if not isinstance(check, list):
                    self.errors.append(f"{location}: '{key}' 必须是条件列表")
                else:
                    if not check:
                        self.warnings.append(f"{location}: 空 {key} 条件恒为 {key == 'and'}")
                    for index, sub in enumerate(check):
                        self._validate_condition(sub, f"{location} {key}[{index}]")
                continue
            if not isinstance(check, dict) or not check:
                self.errors.append(f"{location}: '{key}' 的检查必须是非空对象")
                continue
            if key.startswith("player_") and key[7:] not in PLAYER_DEFAULTS:
                self.warnings.append(f"{location}: 未知玩家属性 '{key}'，该条件不会满足")
            for operator, expected in check.items():
                if operator not in runtime.CONDITION_OPERATORS:
                    self.errors.append(f"{location}: 无效运算符 '{operator}'")
                elif operator in ("in", "not_in") and not isinstance(expected, (list, dict, str)):
                    self.errors.append(f"{location}: '{operator}' 右侧必须是列表、对象或字符串")
                elif operator in (">", ">=", "<", "<=") and (isinstance(expected, bool) or not isinstance(expected, (int, float, str))):
                    self.errors.append(f"{location}: '{operator}' 右侧必须是数值或字符串")
                elif key == "player_completed_trials" and operator == "contains" and not isinstance(expected, str):
                    self.errors.append(f"{location}: 通关记录 contains 必须指定试炼ID字符串")

    def validate_effects(self) -> bool:
        print("\n[7/7] 验证效果配置")
        for node_id, node in self.nodes.items():
            if not isinstance(node, dict):
                continue
            location = f"节点 '{node_id}'"
            if "effects" in node:
                self._validate_effect(node["effects"], location)
                effects = node["effects"]
                if isinstance(effects, dict):
                    ignored = sorted(set(effects) & {"player", "variables"})
                    if node.get("type") == "end" and ignored:
                        self.warnings.append(f"{location}: 结束节点不会执行 {ignored}，请移至结束前的 story 节点或选项")
                    if node.get("type") == "choice" and effects:
                        self.warnings.append(f"{location}: choice 节点自身的 effects 不会执行，请移入选项")
                    if node.get("type") == "story" and set(effects) & {"trial_success", "first_trial_reward"}:
                        self.warnings.append(f"{location}: 普通节点中的通关特殊效果不会执行")
            options = node.get("options", [])
            if isinstance(options, list):
                for index, option in enumerate(options, 1):
                    if isinstance(option, dict) and "effects" in option:
                        self._validate_effect(option["effects"], f"{location} 选项 {index}")
                        effects = option["effects"]
                        if isinstance(effects, dict) and set(effects) & {"trial_success", "first_trial_reward", "rewards"}:
                            self.warnings.append(f"{location} 选项 {index}: 特殊通关效果和奖励展示仅在结束节点处理")
        return not self.errors

    def _validate_effect(self, effects: Any, location: str):
        if not isinstance(effects, dict):
            self.errors.append(f"{location}: effects 必须是对象")
            return
        for section, changes in effects.items():
            if section not in EFFECT_SECTIONS:
                self.warnings.append(f"{location}: 未知 effects 段 '{section}'，游戏不会执行")
            elif section in ("trial_success", "first_trial_reward"):
                if type(changes) is not bool:
                    self.errors.append(f"{location}: {section} 必须是布尔值")
                if section == "first_trial_reward" and changes:
                    self.warnings.append(f"{location}: first_trial_reward 已下架，不会给予奖励")
            elif not isinstance(changes, dict):
                self.errors.append(f"{location}: {section} 必须是对象")
            elif section != "rewards":
                for name, change in changes.items():
                    if isinstance(change, str) and change.startswith(("+", "-")) and not RELATIVE_CHANGE.fullmatch(change):
                        self.errors.append(f"{location}: {section}.{name} 相对变化必须是 '+整数' 或 '-整数'")
                    if section == "player":
                        if name not in PLAYER_DEFAULTS:
                            self.errors.append(f"{location}: 未知玩家属性 '{name}'，无法保存到玩家模型")
                        else:
                            expected_type = PLAYER_ATTRIBUTE_TYPES.get(name)
                            relative = isinstance(change, str) and bool(RELATIVE_CHANGE.fullmatch(change))
                            if expected_type in (int, float):
                                valid = relative or type(change) is int or (expected_type is float and type(change) is float)
                                if not valid:
                                    self.errors.append(f"{location}: player.{name} 必须是{ '整数' if expected_type is int else '数值' }或相对变化字符串")
                            elif relative:
                                self.errors.append(f"{location}: player.{name} 不是数值属性，不能使用相对变化")
                            elif expected_type in (str, bool, dict, list) and not (isinstance(change, expected_type) or (change is None and PLAYER_DEFAULTS[name] is None)):
                                self.errors.append(f"{location}: player.{name} 属性类型不符")

    def generate_report(self) -> str:
        lines = ["=" * 60, "Story Debugger 报告", "=" * 60, f"文件: {self.story_file}"]
        for key, label in (("id", "剧情ID"), ("title", "标题")):
            if key in self.story_data:
                lines.append(f"{label}: {self.story_data[key]}")
        lines.append(f"节点总数: {len(self.nodes)}")
        counts = Counter(node.get("type", "unknown") if isinstance(node, dict) and isinstance(node.get("type", "unknown"), str)
                         else "invalid" for node in self.nodes.values())
        lines.extend(f"  - {key}: {value}" for key, value in sorted(counts.items()))
        for label, marker, messages in (("错误", "ERROR", self.errors), ("警告", "WARN", self.warnings)):
            lines.append(f"\n{label} ({len(messages)}):")
            lines.extend(f"  {index}. [{marker}] {message}" for index, message in enumerate(messages, 1))
        lines.append("\n[FAIL] 请修复错误后重新检查" if self.errors else "\n[PASS] 静态检查通过，请继续验证条件分支和效果")
        lines.append("说明：静态可达性不证明每种玩家状态都能通关。")
        return "\n".join(lines)

    def run_full_check(self) -> bool:
        self.story_data = {}
        self.nodes = {}
        self.errors.clear()
        self.warnings.clear()
        self.node_references.clear()
        if not self.load_story():
            return False
        self.validate_structure()
        self.validate_nodes()
        self.check_references()
        self.analyze_paths()
        self.validate_conditions()
        self.validate_effects()
        return not self.errors


class OfflinePlayer:
    """模拟玩家，只修改内存中的状态。"""

    def __init__(self, state: dict):
        object.__setattr__(self, "state", state)

    def __getattr__(self, name):
        if name in self.state:
            return self.state[name]
        raise AttributeError(name)

    def __setattr__(self, name, value):
        self.state[name] = value

    def get_completed_trials(self):
        trials = self.state.get("completed_trials", [])
        if isinstance(trials, str):
            try:
                trials = json.loads(trials)
            except json.JSONDecodeError:
                return []
        return list(trials) if isinstance(trials, list) else []

    def add_completed_trial(self, trial_id):
        trials = self.get_completed_trials()
        if trial_id not in trials:
            trials.append(trial_id)
        self.state["completed_trials"] = trials

    def get_current_coordinates(self):
        if self.state.get("dungeon_level", 0) > 0:
            return self.state.get("dungeon_x", 0), self.state.get("dungeon_y", 0)
        return self.state.get("real_world_x", 0), self.state.get("real_world_y", 0)


class InteractiveDebugger:
    """使用游戏共用的条件、跳转、格式化和效果规则执行离线试炼。"""

    def __init__(self, story_file: str, player_state: dict | None = None):
        self.story_file = str(story_file)
        self.story_data = {}
        self.current_node = None
        self.initial_player_state = copy.deepcopy(PLAYER_DEFAULTS)
        if player_state:
            self.initial_player_state.update(copy.deepcopy(player_state))
        self.player_state = copy.deepcopy(self.initial_player_state)
        self.variables = {}
        self.runtime = runtime.StoryRuntime()
        self.finished = False
        self.history = []

    @property
    def player(self):
        return OfflinePlayer(self.player_state)

    def load(self) -> bool:
        checker = StoryDebugger(self.story_file)
        success = checker.run_full_check()
        if checker.errors or checker.warnings:
            print(checker.generate_report())
        if not success:
            return False
        self.story_data = checker.story_data
        self.restart()
        return True

    def restart(self):
        self.current_node = self.story_data.get("start_node")
        self.player_state = copy.deepcopy(self.initial_player_state)
        self.variables = {"current_story_id": self.story_data.get("id", "")}
        self.finished = False
        self.history = []

    def run(self):
        print(f"\n交互式试炼调试器：{self.story_data.get('title', '未命名试炼')}")
        print("n/next 继续；数字 选择；s/state 玩家状态；v/vars [变量=JSON] 剧情变量")
        print("p/player [属性=JSON] 修改玩家；t/trace 执行记录；r/restart 重置；q/quit 退出")
        if self.current_node is None:
            self.restart()
        while True:
            self._show_node()
            try:
                command = input("\n> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已退出")
                break
            verb, _, argument = command.partition(" ")
            verb = verb.lower()
            if verb in ("q", "quit"):
                break
            if verb in ("r", "restart"):
                self.restart()
            elif verb in ("s", "state"):
                self._show_state()
            elif verb in ("v", "vars"):
                if argument:
                    self._edit_variable(argument)
                self._show_variables()
            elif verb in ("p", "player"):
                self._edit_player(argument)
            elif verb in ("t", "trace"):
                for item in self.history:
                    print(json.dumps(item, ensure_ascii=False))
            elif verb in ("n", "next"):
                self._next_node()
            elif len(verb) == 1 and verb in "123456789":
                self._choose_option(int(verb))
            else:
                print("未知命令")

    def _node(self):
        return self.story_data.get("nodes", {}).get(self.current_node)

    def _show_node(self):
        node = self._node()
        if not isinstance(node, dict):
            print(f"[ERROR] 无效节点: {self.current_node}")
            return
        print(f"\n{'=' * 60}\n节点: {self.current_node} ({node.get('type')})")
        print(self.runtime.format_content(node.get("content", ""), self.player, self.variables))
        if node.get("image"):
            print(f"配图: {Path(self.story_file).parent / node['image']}")
        if node.get("type") == "choice":
            options = self.runtime.visible_options(node, self.player, self.variables)
            for option in options:
                print(f"  {option['id']}. {option['text']}")
            hidden = len(node.get("options", [])) - len(options)
            if hidden:
                print(f"  （{hidden} 个选项因条件不满足而隐藏）")
            if not options:
                print("[WARN] 当前玩家状态没有可选项，请检查条件或调整测试状态")
        if node.get("type") == "end":
            print("试炼结束")
            for reward, amount in node.get("effects", {}).get("rewards", {}).items():
                print(f"  奖励展示: {reward}: {amount}（仅展示）")

    def _show_state(self):
        print(json.dumps(self.player_state, ensure_ascii=False, indent=2))

    def _show_variables(self):
        print(json.dumps(self.variables, ensure_ascii=False, indent=2))

    def _edit_variable(self, assignment):
        key, separator, raw = assignment.partition("=")
        if not separator or not key.strip():
            print("格式: v 变量名=JSON值")
            return
        if key.strip() == "current_story_id":
            print("current_story_id 由当前剧本自动设置")
            return
        try:
            self.variables[key.strip()] = json.loads(raw)
        except json.JSONDecodeError:
            print("无效的JSON值；字符串请加双引号")

    def _edit_player(self, assignment=""):
        if assignment:
            attr, separator, raw = assignment.partition("=")
            if not separator:
                print("格式: p 属性名=JSON值")
                return
        else:
            try:
                attr = input("要修改的属性（回车跳过）: ").strip()
                if not attr:
                    return
                raw = input("新值（数字、布尔值、字符串或JSON列表）: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消属性编辑")
                return
        attr = attr.strip()
        if attr not in self.player_state:
            print(f"未知玩家属性: {attr}")
            return
        current = self.player_state[attr]
        expected_type = PLAYER_ATTRIBUTE_TYPES.get(attr, type(current))
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            if isinstance(current, str):
                value = raw
            else:
                print("无效的JSON值")
                return
        if attr == "completed_trials":
            valid = isinstance(value, list) and all(isinstance(item, str) for item in value)
        elif expected_type is bool:
            valid = isinstance(value, bool)
        elif expected_type is int:
            valid = type(value) is int or (current is None and value is None)
        elif expected_type is float:
            valid = (isinstance(value, (int, float)) and not isinstance(value, bool)) or (current is None and value is None)
        elif expected_type is str:
            valid = isinstance(value, str) or (current is None and value is None)
        elif expected_type in (dict, list):
            valid = isinstance(value, expected_type) or (current is None and value is None)
        elif current is None:
            valid = True  # 日期等未参与数字比较的 nullable 字段可设置 JSON 值。
        else:
            valid = isinstance(value, type(current))
        if not valid:
            print(f"属性类型不符: {attr}")
            return
        self.player_state[attr] = value
        print(f"已设置 {attr} = {value}")

    def _apply_effects(self, effects):
        changes = effects.get("player", {})
        new_values = runtime.effect_changes(changes, self.player_state)
        new_variables = runtime.apply_variable_effects(effects, self.variables)
        permanent_changed = any(name in PERMANENT_ATTRIBUTES and value != self.player_state.get(name)
                                for name, value in new_values.items())
        self.player_state.update(new_values)
        # 在线永久属性写入口在实际变更后收紧血量/理智上限；离线使用无装备基线。
        if permanent_changed:
            self.player_state["hp"] = min(self.player_state["hp"], self.player_state["max_hp"])
            self.player_state["mp"] = min(self.player_state["mp"], self.player_state["max_mp"])
        self.variables = new_variables

    def _advance(self, action):
        before_player = copy.deepcopy(self.player_state)
        before_vars = copy.deepcopy(self.variables)
        previous = self.current_node
        try:
            self._apply_effects(action.get("effects", {}))
            target = self.runtime.resolve_next(action.get("next"), self.player, self.variables)
        except (ValueError, TypeError, AttributeError) as error:
            self.player_state = before_player
            self.variables = before_vars
            print(f"[ERROR] 效果或跳转执行失败: {error}")
            return
        if target and target in self.story_data["nodes"]:
            self.current_node = target
            node = self._node()
            if node.get("type") == "end":
                runtime.record_trial_success(node.get("effects", {}), self.player, self.variables)
                self.finished = True
        elif target:
            print(f"[ERROR] 跳转目标不存在: {target}")
        else:
            print("[WARN] 没有匹配的跳转，停留原节点；本次普通效果已执行")
        changes = {key: value for key, value in self.player_state.items() if value != before_player.get(key)}
        variables = {key: value for key, value in self.variables.items() if value != before_vars.get(key)}
        self.history.append({"from": previous, "to": self.current_node, "player": changes, "variables": variables})
        if changes or variables:
            print(f"[TRACE] 玩家变化: {changes}；变量变化: {variables}")

    def _next_node(self):
        node = self._node()
        if not isinstance(node, dict) or self.finished or node.get("type") == "end":
            print("试炼已结束或当前节点无效")
        elif node.get("type") != "story":
            print("请选择选项数字")
        else:
            self._advance(node)

    def _choose_option(self, option_id: int):
        node = self._node()
        if not isinstance(node, dict) or self.finished or node.get("type") != "choice":
            print("当前不是可选择的节点")
            return
        for option in node.get("options", []):
            if option.get("id") == option_id:
                if not self.runtime.evaluate_condition(option.get("conditions", {}), self.player, self.variables):
                    print("不满足选择条件")
                    return
                self._advance(option)
                return
        print(f"选项 {option_id} 不存在")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="试炼脚本静态检查与离线调试")
    parser.add_argument("story_path", nargs="?", help="剧本JSON文件或剧本目录")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互调试单个剧本")
    parser.add_argument("--check-all", action="store_true", help="批量检查；未指定路径时检查游戏剧本目录")
    parser.add_argument("--report", type=Path, help="将检查报告保存到指定文件")
    args = parser.parse_args(argv)
    if args.story_path is None and not args.check_all:
        parser.error("请提供剧本路径，或使用 --check-all")
    target = Path(args.story_path) if args.story_path else STORIES_DIR
    if args.interactive:
        if not target.is_file() or args.check_all or args.report:
            parser.error("交互调试需要单个JSON文件，不能与 --check-all/--report 合用")
        debugger = InteractiveDebugger(str(target))
        if not debugger.load():
            return 1
        debugger.run()
        return 0
    files = sorted(target.glob("*.json")) if target.is_dir() else [target]
    if not files:
        print(f"[ERROR] 目录中没有JSON剧本: {target}", file=sys.stderr)
        return 1
    if args.report:
        for file in files:
            try:
                same_file = args.report.exists() and file.exists() and args.report.samefile(file)
            except OSError as error:
                parser.error(f"无法核实报告路径: {error}")
            if same_file or args.report.resolve() == file.resolve():
                parser.error("报告路径不能覆盖剧本文件（含符号链接和硬链接）")
    reports = []
    passed = 0
    for file in files:
        checker = StoryDebugger(str(file))
        passed += checker.run_full_check()
        report = checker.generate_report()
        reports.append(report)
        print(report)
    summary = f"\n检查完成: {len(files)} 个剧本，{passed} 个通过，{len(files) - passed} 个失败"
    print(summary)
    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text("\n\n".join(reports) + summary, encoding="utf-8")
        except (OSError, UnicodeError) as error:
            print(f"[ERROR] 保存报告失败: {error}", file=sys.stderr)
            return 1
        print(f"报告已保存到: {args.report}")
    return 0 if passed == len(files) else 1


if __name__ == "__main__":
    sys.exit(main())
