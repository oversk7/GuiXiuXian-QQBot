"""
原生 Markdown 工具函数

QQ 原生 Markdown 通用构建器，提供蓝字交互标签、彩色文字和消息构建。
"""
import re

from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown

_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{3,8}$|^[A-Za-z]+$")
_FALLBACK_COLOR = "#BFA7FF"
RARITY_COLORS = {
    "green": "#35C75A",
    "blue": "#35C7FF",
    "purple": "#BFA7FF",
    "orange": "#FFB000",
    "red": "#FF5C6C",
}


def cmd(show: str, text: str = "") -> str:
    """
    生成 QQ 原生 Markdown 蓝字交互标签

    Args:
        show: 用户看到的蓝色可点击文字
        text: 点击后实际输入的命令（默认与 show 相同）
    """
    actual = (text or show).replace('"', '&quot;')
    show_safe = show.replace('"', '&quot;')
    return f'<qqbot-cmd-input text="{actual}" show="{show_safe}" reference="false"/>'


def _escape_katex_text(text: str) -> str:
    """转义 KaTeX \text{} 中容易破坏渲染的字符。"""
    replacements = {
        "\\": "\\\\",
        "{": "\\{",
        "}": "\\}",
        "$": "\\$",
        "%": "\\%",
        "&": "\\&",
        "#": "\\#",
        "_": "\\_",
    }
    return "".join(replacements.get(ch, ch) for ch in text)


def color_text(text: str, color: str) -> str:
    """用 QQ Markdown 的 KaTeX 颜色语法渲染彩色文字。"""
    safe_text = _escape_katex_text(str(text))
    safe_color = color.strip().replace("{", "").replace("}", "")
    if not _COLOR_RE.fullmatch(safe_color):
        safe_color = _FALLBACK_COLOR
    return f"$\\textcolor{{{safe_color}}}{{\\text{{{safe_text}}}}}$"


def color_rarity(text: str, rarity: str) -> str:
    """仅为有辨识度的品质标签上色；白色品质保持普通文本。"""
    color = RARITY_COLORS.get(rarity)
    return color_text(text, color) if color else text


def build_markdown(content: str) -> MessageSegment:
    """
    构建原生 Markdown MessageSegment

    自动将 \\n 替换为 \\r（QQ 原生 Markdown 换行要求）
    """
    text = content.replace('\r\n', '\r').replace('\n', '\r')
    md = MessageMarkdown(content=text)
    return MessageSegment.markdown(md)
