"""剧情 JSON 数据校验

防止 data/stories/*.json 被改坏（手编 JSON 易引入弯引号/尾逗号等语法错误，
坏文件会在启动时加载失败，导致该剧情玩家不可玩）。

校验内容：
1. 所有剧情文件可被 json 解析
2. start_node 存在于 nodes 中
3. 节点必须为对象，且 type 为 story / choice / end
4. 节点引用完整：next / options[].next / 条件路由 goto 指向的节点必须存在
"""

import json
from pathlib import Path

import pytest

STORIES_DIR = Path(__file__).parent.parent / "plugins" / "xiuxian_game" / "data" / "stories"
STORY_FILES = sorted(STORIES_DIR.glob("*.json"))


def _load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_stories_exist():
    assert STORY_FILES, f"未找到剧情文件: {STORIES_DIR}"


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.name)
def test_story_parses(path):
    data = _load(path)
    assert isinstance(data, dict), "剧情顶层应为对象"
    assert "nodes" in data and isinstance(data["nodes"], dict), "缺少 nodes 字典"


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.name)
def test_start_node_exists(path):
    data = _load(path)
    start = data.get("start_node")
    assert start in data["nodes"], f"start_node '{start}' 不在 nodes 中"


def _validate_node(node):
    assert isinstance(node, dict), "节点应为对象，不能使用裸条件数组"
    node_type = node.get("type")
    assert isinstance(node_type, str) and node_type in {"story", "choice", "end"}, (
        "节点 type 应为 story / choice / end"
    )


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.name)
def test_nodes_are_typed_objects(path):
    for node in _load(path)["nodes"].values():
        _validate_node(node)


def _collect_target_refs(target):
    """next 可以是固定目标，也可以是按顺序匹配的条件路由。"""
    if isinstance(target, str):
        return [target]
    if isinstance(target, list):
        return [
            rule["goto"]
            for rule in target
            if isinstance(rule, dict) and isinstance(rule.get("goto"), str)
        ]
    return []


def _collect_refs(node):
    """提取合法节点及其选项的所有跳转目标。"""
    _validate_node(node)
    refs = _collect_target_refs(node.get("next"))
    for opt in node.get("options") or []:
        if isinstance(opt, dict):
            refs.extend(_collect_target_refs(opt.get("next")))
    return refs


def _assert_references_resolve(nodes):
    dangling = []
    for nid, node in nodes.items():
        for ref in _collect_refs(node):
            if ref not in nodes:
                dangling.append(f"{nid} -> {ref}")
    assert not dangling, f"悬空节点引用: {dangling}"


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.name)
def test_node_references_resolve(path):
    _assert_references_resolve(_load(path)["nodes"])


@pytest.mark.parametrize("in_option", [False, True], ids=["node", "option"])
@pytest.mark.parametrize("conditional", [False, True], ids=["string", "conditions"])
def test_dangling_references_are_detected(in_option, conditional):
    target = (
        [{"if": {"flag": {"==": True}}, "goto": "missing"}, {"goto": "end"}]
        if conditional else "missing"
    )
    node = (
        {"type": "choice", "options": [{"id": 1, "next": target}]}
        if in_option else {"type": "story", "next": target}
    )
    nodes = {"start": node, "end": {"type": "end"}}
    with pytest.raises(AssertionError, match="start -> missing"):
        _assert_references_resolve(nodes)
    nodes["missing"] = {"type": "end"}
    _assert_references_resolve(nodes)


@pytest.mark.parametrize("node", [[{"goto": "end"}], {}, {"type": "unknown"}, {"type": []}])
def test_invalid_node_shapes_are_rejected(node):
    with pytest.raises(AssertionError):
        _collect_refs(node)
