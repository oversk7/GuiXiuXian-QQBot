"""
战斗 Markdown 构建助手

使用 QQ 官方长文字展示模版渲染战斗日志。
模版 ID：102499345_1772280837

约束：
  - desc 内不能包含 Markdown 特殊字符（# * _ [ ] ` > |）
  - 换行必须用 \r 而非 \n
"""
import re

from nonebot.adapters.qq import MessageSegment
from nonebot.adapters.qq.models.common import MessageMarkdown, MessageMarkdownParams

BATTLE_TEMPLATE_ID = "102499345_1772280837"

_SANITIZE_RE = re.compile(r'[#*_\[\]`>|]')


def _sanitize_desc(text: str) -> str:
    """移除 Markdown 特殊字符，并将所有换行统一为 \\r"""
    text = text.replace('\n', '\r')
    text = _SANITIZE_RE.sub('', text)
    return text


def build_battle_markdown(
    title: str,
    battle_log: list[str],
    hint: str,
    btn1: str,
    btn2: str,
    btn3: str,
) -> MessageSegment:
    """
    构建战斗长文字 Markdown 消息段。

    Args:
        title:      模版标题（显示在代码块上方）；不会自动 sanitize，调用方需自行保证内容合法
        battle_log: 战斗日志行列表，各行用 \\r 连接后放入代码块
        hint:       底部提示文字；不会自动 sanitize，调用方需自行保证内容合法
        btn1:       第一个快捷按钮文字
        btn2:       第二个快捷按钮文字
        btn3:       第三个快捷按钮文字

    Returns:
        MessageSegment，可直接 await cmd.finish(segment)
    """
    # 将各行用 \r 连接，并对行内可能存在的 \n 也替换为 \r
    raw = '\r'.join(str(line).replace('\n', '\r') for line in battle_log)
    desc = _sanitize_desc(raw)

    params = [
        MessageMarkdownParams(key="title", values=[title]),
        MessageMarkdownParams(key="desc",  values=[desc]),
        MessageMarkdownParams(key="hint",  values=[hint]),
        MessageMarkdownParams(key="t1",    values=[btn1]),
        MessageMarkdownParams(key="t2",    values=[btn2]),
        MessageMarkdownParams(key="t3",    values=[btn3]),
    ]
    markdown = MessageMarkdown(custom_template_id=BATTLE_TEMPLATE_ID, params=params)
    return MessageSegment.markdown(markdown)
