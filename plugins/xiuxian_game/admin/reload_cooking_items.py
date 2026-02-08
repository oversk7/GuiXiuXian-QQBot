"""
管理员命令: 重新加载烹饪系统物品配置
"""
from nonebot import on_command
from nonebot.adapters import Event
from nonebot.permission import SUPERUSER
from nonebot import logger

reload_cooking_items = on_command(
    "重载烹饪物品",
    permission=SUPERUSER,
    priority=1,
    block=True
)

@reload_cooking_items.handle()
async def handle_reload_cooking_items(event: Event):
    """重新加载烹饪系统的菜肴物品配置"""
    try:
        from ..cooking.cooking_service import RecipeManager
        from ..cooking.dish_item_generator import DishItemGenerator
        from ..config import config

        # 重新加载食谱
        recipe_manager = RecipeManager()
        recipe_count = len(recipe_manager._recipes)

        # 重新注册菜肴物品
        DishItemGenerator.register_dish_items_to_config(config, recipe_manager)

        # 统计注册的菜肴物品数量
        dish_count = sum(1 for k in config.items_config["by_id"].keys() if k.startswith("dish_"))

        logger.success(f"[Admin] 重载烹饪物品配置成功")

        await reload_cooking_items.finish(
            f"✅ 烹饪系统物品配置重载成功！\n"
            f"📋 食谱总数: {recipe_count}\n"
            f"🍽️ 菜肴物品总数: {dish_count}\n"
            f"提示: 如果仍有问题，请重启Bot"
        )

    except Exception as e:
        logger.error(f"[Admin] 重载烹饪物品配置失败: {e}")
        import traceback
        traceback.print_exc()

        await reload_cooking_items.finish(
            f"❌ 重载失败: {str(e)}\n"
            f"请查看日志获取详细信息"
        )
