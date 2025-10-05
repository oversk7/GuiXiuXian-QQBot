"""
周主题查询命令
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from ..utils import message_add_head
from .weekly_theme import WeeklyThemeManager


# 查看本周主题
theme_cmd = on_command("本周主题", aliases={"周主题", "主题"}, block=True, priority=5)


@theme_cmd.handle()
async def handle_theme(event: MessageEvent):
    """查看本周主题"""
    theme_info = WeeklyThemeManager.get_theme_info()
    await theme_cmd.finish(message_add_head(theme_info, event))

