from nonebot.plugin import PluginMetadata
from nonebot import get_driver

from .config import Config
from .data.db import init_db

__plugin_meta__ = PluginMetadata(
    name="诡修仙",
    description="诡异风格的文字修仙游戏",
    usage="通过指令进行修仙冒险",
    config=Config,
)

# 注册子模块
from . import (
    player,
    cultivate,
    battle,
    # dungeon,
    # economy,
    # social,
    # world
)

driver = get_driver()

@driver.on_startup
async def _():
    await init_db() 