"""在线剧情与离线调试器共享的纯运行逻辑，仅依赖标准库。"""
import re
from numbers import Real
from typing import Any


CONDITION_OPERATORS = frozenset({"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "contains"})


def _completed_trials(player: Any) -> list:
    getter = getattr(player, "get_completed_trials", None)
    if not callable(getter):
        return []
    trials = getter()
    return list(trials) if isinstance(trials, (list, tuple, set, frozenset)) else []


class StoryRuntime:
    """无持久化副作用的条件、路由、显示运行器。"""

    def evaluate_condition(self, condition: Any, player: Any, variables: dict) -> bool:
        """同层所有条目按 AND 组合，包括混合的 and/or 与普通条件。"""
        if not isinstance(condition, dict) or not isinstance(variables, dict):
            return False
        for key, check in condition.items():
            if key in ("and", "or"):
                if not isinstance(check, list):
                    return False
                results = [self.evaluate_condition(item, player, variables) for item in check]
                if not (all(results) if key == "and" else any(results)):
                    return False
            elif not isinstance(key, str):
                return False
            else:
                if key.startswith("player_"):
                    attr = key[7:]
                    value = _completed_trials(player) if attr == "completed_trials" else getattr(player, attr, None)
                else:
                    value = variables.get(key[6:] if key.startswith("story_") else key)
                if not self._check_value(value, check):
                    return False
        return True

    def _check_value(self, value: Any, check: Any) -> bool:
        if value is None or not isinstance(check, dict) or not check:
            return False
        for operator, expected in check.items():
            if operator not in CONDITION_OPERATORS:
                return False
            try:
                if operator in ("==", "!=", ">", ">=", "<", "<="):
                    numeric = (isinstance(value, Real) and not isinstance(value, bool)
                               and isinstance(expected, Real) and not isinstance(expected, bool))
                    if not numeric and type(value) is not type(expected):
                        return False
                    if operator in (">", ">=", "<", "<=") and not (numeric or isinstance(value, str)):
                        return False
                if operator == "==":
                    matched = value == expected
                elif operator == "!=":
                    matched = value != expected
                elif operator == ">":
                    matched = value > expected
                elif operator == ">=":
                    matched = value >= expected
                elif operator == "<":
                    matched = value < expected
                elif operator == "<=":
                    matched = value <= expected
                elif operator == "in":
                    matched = value in expected
                elif operator == "not_in":
                    matched = value not in expected
                else:
                    matched = expected in value
                if not matched:
                    return False
            except (TypeError, ValueError, OverflowError):
                return False
        return True

    def resolve_next(self, next_field: Any, player: Any, variables: dict) -> str | None:
        if isinstance(next_field, str):
            return next_field
        if isinstance(next_field, list):
            for branch in next_field:
                if not isinstance(branch, dict):
                    continue
                if "if" not in branch or self.evaluate_condition(branch["if"], player, variables):
                    target = branch.get("goto")
                    return target if isinstance(target, str) else None
        return None

    def format_content(self, content: str, player: Any, variables: dict) -> str:
        if not isinstance(content, str):
            return ""
        trials = _completed_trials(player)

        def replace(match):
            name = match.group(1)
            if name.startswith("trial_completed_"):
                return str(name[len("trial_completed_"):] in trials)
            if name.startswith("player_"):
                attr = name[7:]
                if attr in ("x", "y"):
                    getter = getattr(player, "get_current_coordinates", None)
                    coordinates = getter() if callable(getter) else (getattr(player, "x", 0), getattr(player, "y", 0))
                    if not isinstance(coordinates, (tuple, list)) or len(coordinates) != 2:
                        coordinates = (0, 0)
                    return str(coordinates[0 if attr == "x" else 1])
                if attr == "completed_trials":
                    return str(trials)
                if attr == "name":
                    return str(getattr(player, "nickname", ""))
                if attr == "guild_id":
                    return str(getattr(player, attr, None) or "无")
                default = "" if attr in ("sex", "region") else 0
                return str(getattr(player, attr, default))
            if name in variables:
                return str(variables[name])
            return match.group(0)

        return re.sub(r"\{([^{}]+)\}", replace, content)

    def visible_options(self, node: Any, player: Any, variables: dict) -> list:
        if not isinstance(node, dict) or not isinstance(node.get("options", []), list):
            return []
        return [option for option in node.get("options", [])
                if isinstance(option, dict) and ("conditions" not in option
                or self.evaluate_condition(option["conditions"], player, variables))]


def effect_changes(changes: dict, current_values: dict) -> dict:
    """返回受影响字段的新值；带正负号的字符串是整数相对变化。"""
    result = {}
    for name, change in changes.items():
        if isinstance(change, str) and change.startswith(("+", "-")):
            result[name] = current_values.get(name, 0) + int(change)
        else:
            result[name] = change
    return result


def apply_variable_effects(effects: dict, variables: dict) -> dict:
    """应用 effects['variables'] 并返回独立的变量字典。"""
    result = variables.copy()
    result.update(effect_changes(effects.get("variables", {}), variables))
    return result


def record_trial_success(effects: dict, player: Any, variables: dict) -> None:
    """保持现有完美结局记录规则，并避免重复添加通关记录。"""
    story_id = variables.get("current_story_id", "")
    if effects.get("trial_success") and story_id:
        trial_id = f"{story_id}_完美" if variables.get("perfect_ending", False) else story_id
        if trial_id not in _completed_trials(player):
            player.add_completed_trial(trial_id)
