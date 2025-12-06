from nonebot.plugin import PluginMetadata
from nonebot import get_driver

from .config import Config
from .models.db import init_db
from . import message_guard

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
    ai_guide,  # AI引导系统（包含管理员数据库查询）
    battle,  # 战斗系统（包含PVP切磋）
    world_boss,
    fishing,
    admin,  # 管理员功能（包含抽奖系统）
    achievement,  # 成就系统
    dialogue,  # NPC AI对话系统（包含管理员命令）
)

driver = get_driver()

@driver.on_startup
async def _():
    await init_db()

    # 注册效果系统（物品效果适配器 + 战斗效果桥接器）
    from .domain.effects.adapters import (
        register_all_item_effect_adapters,
        register_all_battle_effect_bridges,
        USE_NEW_EFFECT_SYSTEM
    )
    from nonebot import logger

    try:
        # 注册物品效果适配器
        adapters = register_all_item_effect_adapters()
        logger.success(f"[EffectSystem] 成功注册 {len(adapters)} 个物品效果适配器")

        # 注册战斗效果桥接器
        bridges = register_all_battle_effect_bridges()
        logger.success(f"[EffectSystem] 成功注册 {len(bridges)} 个战斗效果桥接器")

        # Feature Flag状态
        if USE_NEW_EFFECT_SYSTEM:
            logger.success("[EffectSystem] 新效果系统已启用")
        else:
            logger.info("[EffectSystem] 新效果系统已注册但未启用（Feature Flag关闭）")

    except Exception as e:
        logger.error(f"[EffectSystem] 注册效果系统失败: {e}")
        import traceback
        traceback.print_exc()

    # 加载NPC人设配置
    try:
        from pathlib import Path
        from .dialogue.npc_personality import PersonalityManager

        personalities_file = Path(__file__).parent / "data" / "npc_personalities.yaml"
        if personalities_file.exists():
            PersonalityManager.load_from_file(personalities_file)
            personalities_count = len(PersonalityManager.get_all_personalities())
            logger.success(f"[NPCDialogue] 成功加载 {personalities_count} 个NPC人设配置")
        else:
            logger.warning(f"[NPCDialogue] NPC人设配置文件不存在: {personalities_file}")
    except Exception as e:
        logger.error(f"[NPCDialogue] 加载NPC人设配置失败: {e}")
        import traceback
        traceback.print_exc() 