"""玩家指令必须写进知识库 yaml。

data/knowledge/*.yaml 同时是游戏内帮助页和 AI 助手检索的唯一来源：指令没写进去，
帮助页里找不到，AI 助手也检索不到，只会回答"该功能暂不支持"。
这里静态扫描所有 on_command 注册（不导入插件），要求指令名或任一别名以【指令】
形式出现在某个 yaml 里，这样它在帮助页和 AI 回复里都能渲染成可点击按钮。

存量缺口记在 knowledge_coverage_baseline.yaml，只拦新增；补进 yaml 后要从基线删掉。
"""
import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game"
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"
BASELINE = Path(__file__).with_name("knowledge_coverage_baseline.yaml")

_CMD_TAG = re.compile(r"【([^】\n]+)】")


def _is_admin(path: Path, call: ast.Call) -> bool:
    """管理员指令不面向玩家，不要求进知识库：带 permission 参数，或放在 admin 目录/文件里。"""
    rel = path.relative_to(ROOT)
    if any("admin" in part for part in rel.with_suffix("").parts):
        return True
    return any(kw.arg == "permission" for kw in call.keywords)


def registered_player_commands() -> dict:
    """返回 {指令名: (别名列表, 相对路径)}；指令名不是字面量的动态注册跳过（如帮助页本身）。"""
    commands = {}
    for path in sorted(ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))  # 个别源码文件带 BOM
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "on_command" and node.args):
                continue
            name = node.args[0]
            if not (isinstance(name, ast.Constant) and isinstance(name.value, str)):
                continue
            if _is_admin(path, node):
                continue
            aliases = []
            for kw in node.keywords:
                if kw.arg == "aliases" and isinstance(kw.value, (ast.Set, ast.List, ast.Tuple)):
                    aliases = [e.value for e in kw.value.elts
                               if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            commands[name.value] = (aliases, path.relative_to(ROOT).as_posix())
    return commands


def documented_commands() -> set:
    """yaml 里出现过的指令：【】标签整体、标签首词，以及 help_command / help_aliases。"""
    documented = set()
    for path in KNOWLEDGE_DIR.glob("*.yaml"):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for tag in _CMD_TAG.findall(str(data.get("body", ""))):
            tag = tag.strip()
            if tag:
                documented.add(tag)
                documented.add(tag.split()[0])
        if data.get("help_command"):
            documented.add(data["help_command"])
        documented.update(data.get("help_aliases") or [])
    return documented


def undocumented_commands() -> dict:
    documented = documented_commands()
    return {name: source for name, (aliases, source) in registered_player_commands().items()
            if not any(n in documented for n in [name, *aliases])}


def load_baseline() -> set:
    return set(yaml.safe_load(BASELINE.read_text(encoding="utf-8")) or [])


def test_new_player_commands_are_documented_in_knowledge_yaml():
    missing = {name: source for name, source in undocumented_commands().items()
               if name not in load_baseline()}
    assert not missing, (
        "以下指令没有以【指令】形式写进 data/knowledge/*.yaml，帮助页和 AI 助手都查不到，"
        "请补到对应主题的 yaml：\n"
        + "\n".join(f"  {name}  ({source})" for name, source in sorted(missing.items()))
    )


def test_baseline_only_lists_remaining_gaps():
    stale = load_baseline() - set(undocumented_commands())
    assert not stale, (
        "以下指令已补进 yaml 或已删除，请从 tests/knowledge_coverage_baseline.yaml 移除：\n"
        + "\n".join(f"  {name}" for name in sorted(stale))
    )
