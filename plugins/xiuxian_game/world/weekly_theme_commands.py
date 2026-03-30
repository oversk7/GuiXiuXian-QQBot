"""
周主题查询命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..utils_markdown import cmd, build_markdown
from .weekly_theme import WeeklyThemeManager


# 查看本周主题
theme_cmd = on_command("本周主题", aliases={"周主题", "主题"}, block=True, priority=5)


@theme_cmd.handle()
async def handle_theme(event: MessageEvent):
    """查看本周主题"""
    theme_info = WeeklyThemeManager.get_theme_info()
    buttons = f"\n***\n{cmd('探索')} | {cmd('面板')}"
    await theme_cmd.finish(build_markdown(theme_info + buttons))

