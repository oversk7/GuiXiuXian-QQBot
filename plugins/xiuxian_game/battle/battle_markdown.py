"""
战斗 Markdown 构建助手

使用 QQ 原生 Markdown 渲染战斗日志卡片：
  # 标题 + 代码块战斗日志 + 分隔线 + 引用块提示 + 蓝字快捷指令页脚

日志放在代码块内展示（等宽、可折叠），仅需防止日志行中出现
``` 破坏围栏；换行归一化（\\n → \\r）由 build_markdown 统一处理。
"""
from nonebot.adapters.qq import MessageSegment

from ..utils_markdown import build_markdown, cmd


def _sanitize_log_line(line: str) -> str:
    """防止日志行中的 ``` 破坏代码块围栏"""
    return str(line).replace('```', "'''")


def build_battle_markdown(
    title: str,
    battle_log: list[str],
    hint: str,
    btn1: str,
    btn2: str,
    btn3: str,
) -> MessageSegment:
    """
    构建战斗原生 Markdown 消息段。

    Args:
        title:      卡片大标题（# 一级标题）
        battle_log: 战斗日志行列表，放入代码块等宽展示
        hint:       底部提示文字（引用块），可含多行
        btn1:       第一个快捷指令文字
        btn2:       第二个快捷指令文字
        btn3:       第三个快捷指令文字

    Returns:
        MessageSegment，可直接 await cmd.finish(segment)
    """
    log_text = '\n'.join(_sanitize_log_line(line) for line in battle_log)

    lines = [
        f"# {title}",
        "```",
        log_text,
        "```",
        "***",
    ]
    for hint_line in str(hint).splitlines():
        if hint_line.strip():
            lines.append(f"> {hint_line}")
    lines.append(f"{cmd(btn1)} | {cmd(btn2)} | {cmd(btn3)}")

    return build_markdown('\n'.join(lines))
