"""
里界系统 Markdown 模板助手

利用 QQ 官方 Markdown 模板实现可点击按钮的交互式消息。
"""
import re
from typing import List, Optional

from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams

# 模板ID
TEMPLATE_LONG_TEXT = "102499345_1772280837"   # 长文字展示（可折叠，3按钮）
TEMPLATE_TEXT = "102499345_1770890617"         # 文字展示（4按钮）
TEMPLATE_FEEDBACK = "102499345_1769177016"     # 反馈类（8按钮）

# 清理 Markdown 特殊字符
_SANITIZE_RE = re.compile(r'[#*_\[\]`>|]')


def _sanitize(text: str) -> str:
    """移除 Markdown 特殊字符，换行统一为 \\r"""
    text = text.replace('\n', '\r')
    text = _SANITIZE_RE.sub('', text)
    return text


def build_scene_markdown(
    title: str,
    desc: str,
    hint: str = "",
    btn1: str = "观察",
    btn2: str = "搜刮",
    btn3: str = "前往",
) -> MessageSegment:
    """
    构建场景描述消息（长文字模版，可折叠展开）

    用于：进入里界、前往场景、观察结果
    """
    params = [
        MessageMarkdownParams(key="title", values=[_sanitize(title)]),
        MessageMarkdownParams(key="desc", values=[_sanitize(desc)]),
        MessageMarkdownParams(key="hint", values=[_sanitize(hint) if hint else "快捷操作"]),
        MessageMarkdownParams(key="t1", values=[btn1]),
        MessageMarkdownParams(key="t2", values=[btn2]),
        MessageMarkdownParams(key="t3", values=[btn3]),
    ]
    markdown = MessageMarkdown(custom_template_id=TEMPLATE_LONG_TEXT, params=params)
    return MessageSegment.markdown(markdown)


def build_result_markdown(
    title: str,
    desc: str,
    btn1: str = "前往",
    btn2: str = "搜刮",
    btn3: str = "道具",
    btn4: str = "里界信息",
) -> MessageSegment:
    """
    构建结果/状态消息（文字展示模版，4按钮）

    用于：骰子判定结果、里界信息、对话、道具列表
    """
    params = [
        MessageMarkdownParams(key="title", values=[_sanitize(title)]),
        MessageMarkdownParams(key="desc", values=[_sanitize(desc)]),
        MessageMarkdownParams(key="t1", values=[btn1]),
        MessageMarkdownParams(key="t2", values=[btn2]),
        MessageMarkdownParams(key="t3", values=[btn3]),
        MessageMarkdownParams(key="t4", values=[btn4]),
    ]
    markdown = MessageMarkdown(custom_template_id=TEMPLATE_TEXT, params=params)
    return MessageSegment.markdown(markdown)


def build_choices_markdown(
    title: str,
    result: str,
    buttons: List[str],
) -> MessageSegment:
    """
    构建选择/列表消息（反馈类模版，最多8个按钮）

    用于：前往目的地列表、特殊事件选择
    buttons 中的文本会作为可点击命令按钮
    """
    # 最多8个按钮
    btn_keys = [f"btn{i+1}" for i in range(8)]

    params = [
        MessageMarkdownParams(key="title", values=[_sanitize(title)]),
        MessageMarkdownParams(key="result", values=[_sanitize(result)]),
    ]

    for i, key in enumerate(btn_keys):
        if i < len(buttons):
            params.append(MessageMarkdownParams(key=key, values=[buttons[i]]))
        else:
            # 空按钮用空格占位（QQ模板要求所有参数都要有值）
            params.append(MessageMarkdownParams(key=key, values=[" "]))

    markdown = MessageMarkdown(custom_template_id=TEMPLATE_FEEDBACK, params=params)
    return MessageSegment.markdown(markdown)


def build_destination_buttons(destinations: list, current_scene_name: str = "") -> MessageSegment:
    """
    构建目的地选择消息

    destinations: SceneNode 列表
    """
    result_lines = []
    if current_scene_name:
        result_lines.append(f"当前位置: {current_scene_name}")
    result_lines.append("选择目的地:")

    # 每个目的地生成一个"前往 场景名"按钮
    buttons = []
    for dest in destinations[:8]:  # 最多8个
        display_name = dest.display_name if hasattr(dest, 'display_name') else str(dest)
        buttons.append(f"前往 {display_name}")

    return build_choices_markdown(
        title="可前往地点",
        result="\r".join(result_lines),
        buttons=buttons,
    )


def build_event_choices(title: str, desc: str, choices: list) -> MessageSegment:
    """
    构建特殊事件选择消息

    choices: [{"label": "选项文本", ...}, ...]
    """
    buttons = []
    for choice in choices[:8]:
        label = choice.get("label", "")
        buttons.append(f"选择 {label}")

    return build_choices_markdown(
        title=title,
        result=_sanitize(desc),
        buttons=buttons,
    )
