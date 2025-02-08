from nonebot.plugin import PluginMetadata

from .config import Config

__plugin_meta__ = PluginMetadata(
    name="诡异修仙",
    description="诡异风格的文字修仙游戏",
    usage="通过指令进行修仙冒险",
    config=Config,
)

# 注册子模块
from . import (
    player,
    # battle,
    # dungeon,
    # economy,
    # social,
    # world
) 