import importlib.util
import sys
import types
from pathlib import Path


class _DummyMessageSegment:
    @staticmethod
    def markdown(markdown):
        return markdown

    @staticmethod
    def keyboard(keyboard):
        return keyboard


class _DummyMessageMarkdown:
    def __init__(self, content=None):
        self.content = content


class _DummyModel:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _DummyMessage(list):
    pass


nonebot_mod = types.ModuleType("nonebot")
adapters_mod = types.ModuleType("nonebot.adapters")
qq_mod = types.ModuleType("nonebot.adapters.qq")
models_mod = types.ModuleType("nonebot.adapters.qq.models")
common_mod = types.ModuleType("nonebot.adapters.qq.models.common")
qq_mod.MessageSegment = _DummyMessageSegment
qq_mod.Message = _DummyMessage
common_mod.MessageMarkdown = _DummyMessageMarkdown
for _model_name in ("Action", "Button", "InlineKeyboard", "InlineKeyboardRow",
                    "MessageKeyboard", "Permission", "RenderData"):
    setattr(common_mod, _model_name, type(_model_name, (_DummyModel,), {}))
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


def test_plain_command_text_removes_markup_from_tutorial_fallback():
    content = f"🎯 **谋生之道**\n下一步：{cmd('打工')}\n> {cmd('新手任务')} 随时查看进度"

    assert utils_markdown.plain_command_text(content) == (
        "🎯 谋生之道\n下一步：【打工】\n【新手任务】 随时查看进度"
    )


def test_plain_command_text_preserves_actual_command_arguments():
    content = f"# 下一步\n{cmd('去上京', '导航 上京')}\n{cmd('改名', '改名 小\"鬼\"')}"

    assert utils_markdown.plain_command_text(content) == '下一步\n【导航 上京】\n【改名 小"鬼"】'


def test_color_rarity_keeps_common_quality_plain():
    assert color_rarity("普通", "white") == "普通"
    assert color_rarity("传说", "orange") == r"$\textcolor{#FFB000}{\text{传说}}$"


def test_build_markdown_with_buttons_returns_message():
    result = build_markdown("# 测试", buttons=[[("↑ 上", "上"), "探索"]])

    assert isinstance(result, list) and len(result) == 2
    markdown_seg, keyboard_seg = result
    assert markdown_seg.content == "# 测试"
    row = keyboard_seg.content.rows[0]
    assert len(row.buttons) == 2
    tuple_btn, str_btn = row.buttons
    assert tuple_btn.render_data.label == "↑ 上"
    assert tuple_btn.action.data == "上"
    assert tuple_btn.action.type == 2  # 指令按钮：点击自动填入 @bot 指令
    assert tuple_btn.action.permission.type == 2  # 所有人可点
    assert str_btn.render_data.label == "探索"
    assert str_btn.action.data == "探索"
    # 按钮 ID 在同一 keyboard 内唯一
    assert tuple_btn.id != str_btn.id


def test_keyboard_clamps_to_five_rows_and_five_buttons():
    rows = [[f"b{r}{c}" for c in range(7)] for r in range(7)]
    keyboard_seg = utils_markdown.keyboard(rows)

    assert len(keyboard_seg.content.rows) == 5
    assert all(len(row.buttons) == 5 for row in keyboard_seg.content.rows)
