import importlib.util
import sys
import types
from pathlib import Path


class _DummyMessageSegment:
    @staticmethod
    def markdown(markdown):
        return markdown


class _DummyMessageMarkdown:
    def __init__(self, content=None):
        self.content = content


nonebot_mod = types.ModuleType("nonebot")
adapters_mod = types.ModuleType("nonebot.adapters")
qq_mod = types.ModuleType("nonebot.adapters.qq")
models_mod = types.ModuleType("nonebot.adapters.qq.models")
common_mod = types.ModuleType("nonebot.adapters.qq.models.common")
qq_mod.MessageSegment = _DummyMessageSegment
common_mod.MessageMarkdown = _DummyMessageMarkdown
_stubs = {
    "nonebot": nonebot_mod,
    "nonebot.adapters": adapters_mod,
    "nonebot.adapters.qq": qq_mod,
    "nonebot.adapters.qq.models": models_mod,
    "nonebot.adapters.qq.models.common": common_mod,
}
# 强制替换（真模块可能已被其他测试加载），结束后完整还原，保证与运行顺序无关
_saved = {}
for _name, _module in _stubs.items():
    _saved[_name] = sys.modules.get(_name)
    sys.modules[_name] = _module

try:
    MODULE_PATH = Path(__file__).resolve().parents[1] / "plugins" / "xiuxian_game" / "utils_markdown.py"
    SPEC = importlib.util.spec_from_file_location("utils_markdown_under_test", MODULE_PATH)
    assert SPEC and SPEC.loader
    utils_markdown = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(utils_markdown)
finally:
    for _name, _original in _saved.items():
        if _original is None:
            sys.modules.pop(_name, None)
        else:
            sys.modules[_name] = _original

cmd = utils_markdown.cmd
color_text = utils_markdown.color_text
color_rarity = utils_markdown.color_rarity
build_markdown = utils_markdown.build_markdown


def test_color_text_escapes_katex_text():
    result = color_text(r"a_{b}\c#1", "#FFB000")

    assert result == r"$\textcolor{#FFB000}{\text{a\_\{b\}\\c\#1}}$"


def test_build_markdown_does_not_auto_color_content():
    result = build_markdown("# 👤 修士\n**⚔️ 修仙主线**\n❤️生命 **100**/120\n金币 +50")

    assert result.content == "# 👤 修士\r**⚔️ 修仙主线**\r❤️生命 **100**/120\r金币 +50"


def test_build_markdown_keeps_command_tags_clickable():
    button = cmd("修炼")
    result = build_markdown(f"💡 点 {button} 继续")

    assert button in result.content
    assert r"\textcolor" not in result.content


def test_color_rarity_keeps_common_quality_plain():
    assert color_rarity("普通", "white") == "普通"
    assert color_rarity("传说", "orange") == r"$\textcolor{#FFB000}{\text{传说}}$"
