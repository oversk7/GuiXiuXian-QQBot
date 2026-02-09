"""
菜肴物品动态生成器

在系统启动时,根据食谱配置动态生成菜肴物品配置,
并注册到 items_config 中,使其可以作为正常物品添加到背包
"""
from typing import Dict
from nonebot import logger
from ..models.inventory import ItemConfig, ItemType


class DishItemGenerator:
    """菜肴物品生成器 - 动态创建菜肴物品配置"""

    QUALITY_NAMES = {
        "dark": "黑暗",
        "normal": "",  # 普通品质不加前缀
        "fine": "精致",
        "perfect": "完美"
    }

    QUALITY_RARITY = {
        "dark": "white",
        "normal": "white",
        "fine": "green",
        "perfect": "blue"
    }

    @staticmethod
    def generate_dish_items(recipe_manager) -> Dict[str, ItemConfig]:
        """
        根据食谱生成菜肴物品配置

        Args:
            recipe_manager: RecipeManager实例

        Returns:
            菜肴物品配置字典 {item_id: ItemConfig}
        """
        dish_items = {}
        recipes = recipe_manager._recipes

        logger.info(f"🔍 [DEBUG] 开始生成菜肴物品，食谱数量: {len(recipes)}")

        for recipe_id, recipe in recipes.items():
            logger.debug(f"  处理食谱: {recipe_id} - {recipe.name}")
            # 为每个食谱的每种品质生成菜肴物品
            for quality, quality_name in DishItemGenerator.QUALITY_NAMES.items():
                dish_item_id = f"dish_{recipe_id}_{quality}"
                dish_name = f"{quality_name}{recipe.name}" if quality_name else recipe.name
                rarity = DishItemGenerator.QUALITY_RARITY[quality]

                # 计算菜肴价格
                quality_multipliers = {
                    "dark": 0.1,
                    "normal": 1.0,
                    "fine": 1.5,
                    "perfect": 2.5
                }
                dish_price = int(recipe.base_price * quality_multipliers[quality])

                # 创建ItemConfig
                item_data = {
                    "item_id": dish_item_id,
                    "name": dish_name,
                    "type": "DISH",
                    "rarity": rarity,
                    "description": f"{recipe.description} (品质:{quality_name if quality_name else '普通'})",
                    "price": dish_price,
                    "effect_type": "BUFF",  # 菜肴使用BUFF效果类型
                    "effect_params": {},
                    "tags": ["dish", f"tier_{recipe.tier}", f"quality_{quality}"]
                }

                # 如果是完美品质且有buff,添加效果参数
                if quality == "perfect" and recipe.buff:
                    item_data["effect_params"] = recipe.buff

                try:
                    dish_config = ItemConfig(item_data)
                    dish_items[dish_item_id] = dish_config
                    logger.debug(f"    ✅ 生成菜肴: {dish_item_id} - {dish_name}")
                except Exception as e:
                    logger.error(f"    ❌ 生成菜肴失败 {dish_item_id}: {e}")

        logger.info(f"✅ 动态生成 {len(dish_items)} 个菜肴物品配置")
        return dish_items

    @staticmethod
    def register_dish_items_to_config(config_instance, recipe_manager):
        """
        将动态生成的菜肴物品注册到config.items_config

        Args:
            config_instance: 配置实例
            recipe_manager: RecipeManager实例
        """
        logger.info(f"🔍 [DEBUG] 开始注册菜肴物品到配置系统")
        logger.info(f"🔍 [DEBUG] 当前 config.items_config['by_id'] 中的物品数: {len(config_instance.items_config.get('by_id', {}))}")

        dish_items = DishItemGenerator.generate_dish_items(recipe_manager)

        logger.info(f"🔍 [DEBUG] generate_dish_items 返回了 {len(dish_items)} 个菜肴")

        # 注册到 by_id
        if "by_id" not in config_instance.items_config:
            config_instance.items_config["by_id"] = {}
            logger.warning(f"⚠️ items_config 中没有 by_id，已创建")

        registered_count = 0
        for item_id, item_config in dish_items.items():
            config_instance.items_config["by_id"][item_id] = item_config
            registered_count += 1
            if registered_count <= 5:  # 只显示前5个
                logger.debug(f"  注册到 by_id: {item_id} -> {item_config.name}")

        # 注册到 by_name
        if "by_name" not in config_instance.items_config:
            config_instance.items_config["by_name"] = {}
            logger.warning(f"⚠️ items_config 中没有 by_name，已创建")

        for item_id, item_config in dish_items.items():
            config_instance.items_config["by_name"][item_config.name] = item_config

        logger.info(f"✅ 成功注册 {len(dish_items)} 个菜肴物品到配置系统")
        logger.info(f"🔍 [DEBUG] 注册后 config.items_config['by_id'] 中的物品数: {len(config_instance.items_config['by_id'])}")

        # 验证注册结果
        dish_count_check = sum(1 for k in config_instance.items_config["by_id"].keys() if k.startswith("dish_"))
        logger.info(f"🔍 [DEBUG] 验证: by_id 中以 'dish_' 开头的物品数: {dish_count_check}")
