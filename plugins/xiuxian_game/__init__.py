from nonebot.plugin import PluginMetadata
from nonebot import get_driver
from nonebot.message import run_postprocessor
from nonebot.matcher import Matcher

from .config import Config
from .models.db import init_db
from . import command_guard
from . import message_guard
from . import observability
from . import http_client_patch

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
    llm_usage,  # LLM用量统计（管理员指令【AI用量】）
    battle,  # 战斗系统（包含PVP切磋）
    world_boss,
    guild_boss,  # 公会镇诡（公会Boss，开坛引诡全会合力镇压）
    fishing,
    cooking,  # 烹饪与餐厅经营系统
    spirit_field,  # 灵田系统（种植/偷菜/诡兽守田）
    admin,  # 管理员功能（包含抽奖系统）
    achievement,  # 成就系统
    dialogue,  # NPC AI对话系统（包含管理员命令）
    global_ban_interceptor,  # 全局封禁拦截器
    group_welcome,  # 新人进群欢迎
    event,  # 除夕叩门活动系统
    lower_world,  # 下位世界·第四天灾入侵系统
    sponsor,  # 赞助商店系统（诡烛氪金货币）
    auction,  # 拍卖行系统（稀有物品限时竞价）
    pet,  # 宠物伴侣系统
    web,  # Web 地图可视化
    rule_horror,  # 规则怪谈玩法（LLM 生成怪谈冒险，移植自 MaiBot 插件）
)

driver = get_driver()

@driver.on_startup
async def _():
    await init_db()

    from nonebot import logger

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


@run_postprocessor
async def _handle_db_deadlock(matcher: Matcher, exception: Exception | None):
    """全局后处理器：数据库死锁时给用户发送友好提示而非沉默失败"""
    if exception is None:
        return
    from sqlalchemy.exc import OperationalError
    # 递归检查异常链（包括 __cause__）
    exc = exception
    while exc is not None:
        if isinstance(exc, OperationalError) and getattr(exc, 'orig', None) and getattr(exc.orig, 'args', (None,))[0] == 1213:
            try:
                await matcher.send("⚠️ 操作冲突，请稍后再试")
            except Exception:
                pass
            return
        exc = getattr(exc, '__cause__', None)
