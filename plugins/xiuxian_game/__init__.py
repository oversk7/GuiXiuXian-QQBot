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
    cooking,  # 烹饪与餐厅经营系统
    spirit_field,  # 灵田系统（种植/偷菜/诡兽守田）
    admin,  # 管理员功能（包含抽奖系统）
    achievement,  # 成就系统
    dialogue,  # NPC AI对话系统（包含管理员命令）
    global_ban_interceptor,  # 全局封禁拦截器
    inner_realm,  # 里界系统
    event,  # 除夕叩门活动系统
    lower_world,  # 下位世界·第四天灾入侵系统
    sponsor,  # 赞助商店系统（诡烛氪金货币）
    auction,  # 拍卖行系统（稀有物品限时竞价）
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

    # 动态注册菜肴物品配置
    try:
        from .cooking.cooking_service import RecipeManager
        from .cooking.dish_item_generator import DishItemGenerator
        from .config import config

        # 强制加载食谱
        RecipeManager.reload()
        recipe_manager = RecipeManager()
        recipe_count = len(recipe_manager._recipes)

        if recipe_count == 0:
            logger.warning("[CookingSystem] 食谱配置为空！请检查 data/recipes.yaml 文件")
        else:
            # 注册菜肴物品配置
            DishItemGenerator.register_dish_items_to_config(config, recipe_manager)

            # 验证注册结果
            dish_count = sum(1 for k in config.items_config.get("by_id", {}).keys() if k.startswith("dish_"))
            logger.success(f"[CookingSystem] 菜肴物品配置已动态注册: {recipe_count}个食谱 -> {dish_count}个菜肴物品")

    except Exception as e:
        logger.error(f"[CookingSystem] 注册菜肴物品配置失败: {e}")
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

    # 初始化 AI 知识库 BM25 检索器
    try:
        from .ai_knowledge_retriever import initialize_knowledge_retriever
        initialize_knowledge_retriever()
        logger.success("[KnowledgeRetriever] AI知识库BM25检索器初始化完成")
    except Exception as e:
        logger.error(f"[KnowledgeRetriever] AI知识库检索器初始化失败: {e}")
        import traceback
        traceback.print_exc()