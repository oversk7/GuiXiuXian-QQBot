"""剧情 JSON 数据校验

防止 data/stories/*.json 被改坏（手编 JSON 易引入弯引号/尾逗号等语法错误，
坏文件会在启动时加载失败，导致该剧情玩家不可玩）。

校验内容：
1. 所有剧情文件可被 json 解析
2. start_node 存在于 nodes 中
3. 节点引用完整：next / options[].next / 条件路由 goto 指向的节点必须存在
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


def _collect_refs(node):
    """提取一个节点的所有跳转目标。"""
    refs = []
    if isinstance(node, dict):
        if isinstance(node.get("next"), str):
            refs.append(node["next"])
        for opt in node.get("options") or []:
            if isinstance(opt, dict) and isinstance(opt.get("next"), str):
                refs.append(opt["next"])
    elif isinstance(node, list):
        # 条件路由节点: [{"if": ..., "goto": ...}, ...]
        for rule in node:
            if isinstance(rule, dict) and isinstance(rule.get("goto"), str):
                refs.append(rule["goto"])
    return refs


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.name)
def test_node_references_resolve(path):
    nodes = _load(path)["nodes"]
    dangling = []
    for nid, node in nodes.items():
        for ref in _collect_refs(node):
            if ref not in nodes:
                dangling.append(f"{nid} -> {ref}")
    assert not dangling, f"悬空节点引用: {dangling}"
