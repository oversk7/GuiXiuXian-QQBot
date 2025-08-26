from nonebot.plugin import PluginMetadata
from nonebot import get_driver
from .config import Config
from .models.db import init_db

__plugin_meta__ = PluginMetadata(
    name="诡修仙",
    description="诡异风格的文字修仙游戏",
    usage="通过指令进行修仙冒险",
    config=Config,
)

# 注册子模块
from . import (
    log,
    player,
    cultivate,
    economy,
    world,
    item,
    entertainment,
    guild,
    alchemy,
    social,
    story,
    daily_task,  # 每日任务系统
    backup,
    ai_guide,  # AI引导系统（包含管理员数据库查询）
    battle,  # 战斗系统（包含PVP切磋）
    world_boss,
    fishing  # 钓鱼系统
)

# 导入跨平台绑定模块
from . import platform_binding_commands

driver = get_driver()

@driver.on_startup
async def _():
    await init_db() 