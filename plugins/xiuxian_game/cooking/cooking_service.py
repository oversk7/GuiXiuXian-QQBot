"""
烹饪服务 - 核心烹饪逻辑

提供手动烹饪功能，包括:
- 食谱验证和食材检查
- 烹饪品质判定
- 菜肴生成
"""

import random
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from nonebot import logger
import yaml
from pathlib import Path

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.chef import ChefTier, CookingCategory
from ..models.inventory import ItemType


class RecipeData:
    """食谱数据类"""

    def __init__(self, data: dict):
        self.recipe_id: str = data["recipe_id"]
        self.name: str = data["name"]
        self.category: str = data["category"]  # fish/soup/grill/steam/dessert
        self.tier: str = data["tier"]  # white/green/blue/purple/orange
        self.kitchen_level: int = data["kitchen_level"]
        self.ingredients: Dict[str, int] = data["ingredients"]  # {item_id: quantity}
        self.base_price: int = data["base_price"]
        self.description: str = data["description"]
        self.buff: Optional[Dict] = data.get("buff")


class RecipeManager:
    """食谱管理器 - 加载和缓存食谱配置"""

    _instance = None
    _recipes: Dict[str, RecipeData] = {}
    _recipes_by_tier: Dict[str, List[RecipeData]] = {
        "white": [],
        "green": [],
        "blue": [],
        "purple": [],
        "orange": []
    }

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_recipes()
        return cls._instance

    def _load_recipes(self):
        """从 YAML 文件加载所有食谱"""
        recipes_file = Path(__file__).parent.parent / "data" / "recipes.yaml"

        if not recipes_file.exists():
            logger.error(f"食谱配置文件不存在: {recipes_file}")
            return

        try:
            with open(recipes_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            for recipe_data in data.get("recipes", []):
                recipe = RecipeData(recipe_data)
                self._recipes[recipe.recipe_id] = recipe
                self._recipes_by_tier[recipe.tier].append(recipe)

            logger.info(f"✅ 成功加载 {len(self._recipes)} 个食谱配置")
        except Exception as e:
            logger.error(f"❌ 加载食谱配置失败: {e}")

    def get_recipe(self, recipe_id: str) -> Optional[RecipeData]:
        """获取指定食谱"""
        return self._recipes.get(recipe_id)

    def get_recipe_by_name(self, name: str) -> Optional[RecipeData]:
        """根据名称获取食谱"""
        for recipe in self._recipes.values():
            if recipe.name == name:
                return recipe
        return None

    def get_recipes_by_tier(self, tier: str) -> List[RecipeData]:
        """获取指定稀有度的所有食谱"""
        return self._recipes_by_tier.get(tier, [])

    def get_all_recipes(self) -> List[RecipeData]:
        """获取所有食谱"""
        return list(self._recipes.values())

    def get_default_recipes(self) -> List[str]:
        """获取默认食谱ID列表(白色家常菜)"""
        return [recipe.recipe_id for recipe in self._recipes_by_tier["white"]]


class DishQuality:
    """菜肴品质枚举"""
    DARK = "dark"          # 黑暗料理(失败)
    NORMAL = "normal"      # 普通
    FINE = "fine"          # 精致
    PERFECT = "perfect"    # 完美


class CookingService:
    """
    烹饪服务 - 核心烹饪逻辑

    负责:
    - 验证食谱和厨房等级
    - 检查食材库存
    - 烹饪品质判定
    - 消耗食材并生成菜肴
    """

    def __init__(self):
        self.recipe_manager = RecipeManager()

    async def cook_dish(
        self,
        uow: UnitOfWork,
        player_id: str,
        recipe_id: str,
        quantity: int = 1,
        chef_skill: int = 70,  # 默认成功率70%(手动烹饪无厨师加成)
        chef_specialty: Optional[str] = None
    ) -> Tuple[bool, str, Optional[List[Dict]]]:
        """
        烹饪菜肴(手动烹饪或餐厅经营)

        Args:
            uow: 工作单元
            player_id: 玩家ID
            recipe_id: 食谱ID
            quantity: 数量
            chef_skill: 厨艺值(影响成功率和品质)
            chef_specialty: 厨师擅长类别(可选)

        Returns:
            (是否成功, 消息, 菜肴列表)
            菜肴列表格式: [{"name": "菜名", "quality": "品质", "price": 售价}, ...]
        """

        # 1. 验证食谱
        recipe = self.recipe_manager.get_recipe(recipe_id)
        if not recipe:
            return False, f"⛔ 未找到食谱: {recipe_id}", None

        # 2. 检查玩家是否学会该食谱
        has_recipe = await uow.player_recipes.has_recipe(player_id, recipe_id)
        if not has_recipe:
            return False, f"⛔ 你还没有学会【{recipe.name}】的做法", None

        # 3. 检查食材库存(从玩家背包)
        player = await uow.players.get_by_id(player_id)
        if not player:
            return False, "⛔ 玩家不存在", None

        # 检查每种食材的库存
        for item_id, needed_qty in recipe.ingredients.items():
            total_needed = needed_qty * quantity

            # 获取玩家背包中的该物品数量
            item_count = await uow.items.count_by_player_and_item(player_id, item_id)

            if item_count < total_needed:
                return False, f"⛔ 食材不足: {item_id} (需要 {total_needed}，拥有 {item_count})", None

        # 4. 执行烹饪并生成菜肴
        results = []
        total_consumed = {}  # 记录总消耗食材

        for i in range(quantity):
            # 判定烹饪成功/失败
            success_rate = self._calculate_success_rate(chef_skill, recipe.category, chef_specialty)
            is_success = random.random() * 100 < success_rate

            if is_success:
                # 成功 - 判定品质
                quality = self._determine_quality(chef_skill, recipe.category, chef_specialty)
                quality_multiplier = self._get_quality_multiplier(quality)
                dish_price = int(recipe.base_price * quality_multiplier)

                results.append({
                    "name": recipe.name,
                    "quality": quality,
                    "price": dish_price,
                    "buff": recipe.buff if quality == DishQuality.PERFECT else None
                })

                # 消耗100%食材
                for item_id, qty in recipe.ingredients.items():
                    total_consumed[item_id] = total_consumed.get(item_id, 0) + qty
            else:
                # 失败 - 产出黑暗料理
                results.append({
                    "name": f"黑暗{recipe.name}",
                    "quality": DishQuality.DARK,
                    "price": int(recipe.base_price * 0.1),
                    "buff": None
                })

                # 失败只消耗50%食材
                for item_id, qty in recipe.ingredients.items():
                    consumed = int(qty * 0.5)
                    total_consumed[item_id] = total_consumed.get(item_id, 0) + consumed

        # 5. 扣除食材
        for item_id, consumed_qty in total_consumed.items():
            # 从玩家背包扣除食材
            items = await uow.items.get_by_player_and_item(player_id, item_id)

            remaining = consumed_qty
            for item in items:
                if remaining <= 0:
                    break

                if item.quantity >= remaining:
                    item.quantity -= remaining
                    if item.quantity == 0:
                        await uow.items.delete(item)
                    else:
                        await uow.items.update(item)
                    remaining = 0
                else:
                    remaining -= item.quantity
                    await uow.items.delete(item)

        # 6. 添加菜肴到背包(作为DISH类型物品)
        for dish in results:
            # 动态生成菜肴的item_id: dish_{recipe_id}_{quality}
            # 例如: dish_braised_carp_normal, dish_braised_carp_perfect
            dish_item_id = self._generate_dish_item_id(recipe.recipe_id, dish["quality"])

            # 使用ItemInstance.add_item添加到背包
            # 菜肴作为DISH类型,可堆叠
            from ..models.inventory import ItemInstance
            try:
                await ItemInstance.add_item(uow.session, player_id, dish_item_id, 1)
            except ValueError as e:
                # 如果背包满了,返回错误
                return False, f"⛔ 背包空间不足: {str(e)}", None

        # 7. 提交事务
        await uow.commit()

        # 8. 生成结果消息
        success_count = sum(1 for r in results if r["quality"] != DishQuality.DARK)
        fail_count = len(results) - success_count

        msg = f"🍳 烹饪完成!\n"
        msg += f"📊 成功: {success_count} | 失败: {fail_count}\n\n"

        for dish in results:
            quality_emoji = self._get_quality_emoji(dish["quality"])
            msg += f"{quality_emoji} {dish['name']} (售价: {dish['price']}金)\n"

        return True, msg, results

    def _calculate_success_rate(
        self,
        chef_skill: int,
        recipe_category: str,
        chef_specialty: Optional[str]
    ) -> float:
        """
        计算烹饪成功率

        基础成功率 = 厨艺值
        擅长加成 = +10% (如果厨师擅长该类别)
        """
        success_rate = float(chef_skill)

        # 擅长类别加成
        if chef_specialty and chef_specialty == recipe_category:
            success_rate += 10.0

        return min(success_rate, 100.0)  # 最高100%

    def _determine_quality(
        self,
        chef_skill: int,
        recipe_category: str,
        chef_specialty: Optional[str]
    ) -> str:
        """
        判定菜肴品质

        根据厨艺值和擅长类别roll品质:
        1. 先roll完美率
        2. 再roll精致率
        3. 否则为普通
        """
        # 基础品质率(这里简化处理,实际应该从厨师等级获取)
        # 假设: 厨艺70 = 学徒, 80=帮厨, 88=厨师, 94=大厨, 98=特级厨师
        if chef_skill >= 98:
            perfect_rate, fine_rate = 28, 45
        elif chef_skill >= 94:
            perfect_rate, fine_rate = 18, 35
        elif chef_skill >= 88:
            perfect_rate, fine_rate = 10, 25
        elif chef_skill >= 80:
            perfect_rate, fine_rate = 5, 18
        else:
            perfect_rate, fine_rate = 2, 10

        # 擅长类别加成
        if chef_specialty and chef_specialty == recipe_category:
            perfect_rate += 15
            fine_rate += 15

        # Roll品质
        roll = random.random() * 100

        if roll < perfect_rate:
            return DishQuality.PERFECT
        elif roll < fine_rate:
            return DishQuality.FINE
        else:
            return DishQuality.NORMAL

    def _get_quality_multiplier(self, quality: str) -> float:
        """获取品质对应的售价倍率"""
        multipliers = {
            DishQuality.DARK: 0.1,
            DishQuality.NORMAL: 1.0,
            DishQuality.FINE: 1.5,
            DishQuality.PERFECT: 2.5
        }
        return multipliers.get(quality, 1.0)

    def _get_quality_emoji(self, quality: str) -> str:
        """获取品质对应的emoji"""
        emojis = {
            DishQuality.DARK: "💀",
            DishQuality.NORMAL: "🍽️",
            DishQuality.FINE: "✨",
            DishQuality.PERFECT: "🌟"
        }
        return emojis.get(quality, "🍴")

    def _generate_dish_item_id(self, recipe_id: str, quality: str) -> str:
        """
        生成菜肴物品ID

        格式: dish_{recipe_id}_{quality}
        例如: dish_braised_carp_normal, dish_braised_carp_perfect

        Args:
            recipe_id: 食谱ID
            quality: 品质(dark/normal/fine/perfect)

        Returns:
            菜肴物品ID
        """
        return f"dish_{recipe_id}_{quality}"

    async def learn_recipe(
        self,
        uow: UnitOfWork,
        player_id: str,
        recipe_id: str
    ) -> Tuple[bool, str]:
        """
        学习食谱

        Args:
            uow: 工作单元
            player_id: 玩家ID
            recipe_id: 食谱ID

        Returns:
            (是否成功, 消息)
        """
        # 验证食谱存在
        recipe = self.recipe_manager.get_recipe(recipe_id)
        if not recipe:
            return False, f"⛔ 未找到食谱: {recipe_id}"

        # 检查是否已学会
        has_recipe = await uow.player_recipes.has_recipe(player_id, recipe_id)
        if has_recipe:
            return False, f"⛔ 你已经学会了【{recipe.name}】"

        # 添加食谱记录
        from ..models.player_recipe import PlayerRecipe
        player_recipe = PlayerRecipe(
            player_id=player_id,
            recipe_id=recipe_id,
            learned_at=datetime.now()
        )
        await uow.player_recipes.add(player_recipe)
        await uow.commit()

        return True, f"✅ 成功学会食谱【{recipe.name}】!"

    async def get_player_recipes(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> List[RecipeData]:
        """
        获取玩家已学会的所有食谱

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            食谱列表
        """
        recipe_ids = await uow.player_recipes.get_recipe_ids_by_player(player_id)

        recipes = []
        for recipe_id in recipe_ids:
            recipe = self.recipe_manager.get_recipe(recipe_id)
            if recipe:
                recipes.append(recipe)

        return recipes
