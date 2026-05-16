"""
原生 Markdown 工具函数

QQ 原生 Markdown 通用构建器，提供蓝字交互标签和消息构建。
"""
from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown


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


def color_text(text: str, color: str) -> str:
    """用 QQ Markdown 的 KaTeX 颜色语法渲染彩色文字。"""
    safe_text = text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
    safe_color = color.replace("{", "").replace("}", "")
    return f"$\\textcolor{{{safe_color}}}{{\\text{{{safe_text}}}}}$"


def build_markdown(content: str) -> MessageSegment:
    """
    构建原生 Markdown MessageSegment

    自动将 \\n 替换为 \\r（QQ 原生 Markdown 换行要求）
    """
    text = content.replace('\r\n', '\r').replace('\n', '\r')
    md = MessageMarkdown(content=text)
    return MessageSegment.markdown(md)
