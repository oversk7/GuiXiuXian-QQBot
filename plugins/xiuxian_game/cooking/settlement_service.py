"""
经营结算服务 - 每小时自动结算

提供:
- 每小时餐厅经营结算
- 客流计算
- 厨师制作菜品
- 收入支出计算
- 声望变化
- 日志生成
"""

import random
import json
from typing import Dict, List, Tuple
from datetime import datetime, timedelta
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.restaurant_log import RestaurantLog
from ..models.chef import ChefPersonality
from .cooking_service import RecipeManager, DishQuality


class SettlementService:
    """
    经营结算服务 - 每小时自动结算餐厅经营状况

    流程:
    1. 计算客流量(基于面积和声望)
    2. 厨师制作菜品(消耗食材)
    3. 顾客消费(产生收入)
    4. 扣除厨师工资
    5. 计算声望变化
    6. 生成经营日志
    """

    def __init__(self):
        self.recipe_manager = RecipeManager()

    async def settle_all_restaurants(self, uow: UnitOfWork) -> int:
        """
        结算所有营业中的餐厅

        Args:
            uow: 工作单元

        Returns:
            结算的餐厅数量
        """
        open_restaurants = await uow.restaurants.get_open_restaurants()

        settled_count = 0
        for restaurant in open_restaurants:
            try:
                await self._settle_restaurant(uow, restaurant.id)
                settled_count += 1
            except Exception as e:
                logger.error(f"❌ 餐厅 {restaurant.id} 结算失败: {e}")
                continue

        if settled_count > 0:
            logger.info(f"✅ 完成 {settled_count} 家餐厅的小时结算")

        return settled_count

    async def _settle_restaurant(self, uow: UnitOfWork, restaurant_id: int):
        """
        结算单个餐厅(私有方法)

        Args:
            uow: 工作单元
            restaurant_id: 餐厅ID
        """

        period_start = datetime.now()
        period_end = period_start + timedelta(hours=1)

        # 获取餐厅信息
        restaurant = await uow.restaurants.get_by_id(restaurant_id)
        if not restaurant or not restaurant.is_open:
            return

        # 获取所有厨师
        chefs = await uow.chefs.get_by_restaurant_id(restaurant_id)
        if not chefs:
            # 没有厨师无法经营
            return

        # 1. 计算客流量
        customer_count = self._calculate_customer_count(
            restaurant.area,
            restaurant.reputation,
            restaurant.level
        )

        # 2. 厨师制作菜品
        dishes_made = []  # 成功制作的菜品
        dishes_failed = 0  # 失败次数
        chef_details = []  # 厨师详细记录

        for chef in chefs:
            chef_result = await self._chef_cook_dishes(
                uow, chef, restaurant
            )
            dishes_made.extend(chef_result["dishes"])
            dishes_failed += chef_result["failed"]
            chef_details.append(chef_result)

        # 3. 顾客消费
        income = 0
        dishes_sold = min(len(dishes_made), customer_count)

        for i in range(dishes_sold):
            dish = dishes_made[i]
            # 售价 = 基础售价 × 品质倍率 × 声望加成
            reputation_bonus = 1.0 + (restaurant.reputation / 5000.0)
            dish_income = int(dish["price"] * reputation_bonus)
            income += dish_income

        # 4. 扣除厨师工资
        expense = sum(chef.salary for chef in chefs)

        # 5. 计算声望变化
        reputation_change = self._calculate_reputation_change(
            customer_count,
            dishes_sold,
            dishes_failed,
            dishes_made
        )

        # 6. 更新餐厅数据
        restaurant.total_income += income
        restaurant.total_expense += expense
        restaurant.reputation = max(0, min(10000, restaurant.reputation + reputation_change))
        restaurant.last_settlement = period_start
        await uow.restaurants.update(restaurant)

        # 7. 生成日志
        log_details = {
            "customer_count": customer_count,
            "dishes_sold": dishes_sold,
            "unsold_dishes": len(dishes_made) - dishes_sold,
            "chef_details": chef_details,
            "dishes_made": dishes_made,
            "reputation_change": reputation_change
        }

        log = RestaurantLog(
            restaurant_id=restaurant_id,
            period_start=period_start,
            period_end=period_end,
            income=income,
            expense=expense,
            customers=customer_count,
            dishes_made=len(dishes_made),
            dishes_failed=dishes_failed,
            details_json=json.dumps(log_details, ensure_ascii=False),
            reputation_change=reputation_change,
            created_at=period_start
        )
        await uow.restaurant_logs.add(log)

        await uow.commit()

        logger.info(
            f"🏪 餐厅 {restaurant_id} 结算完成: "
            f"收入 {income}金 | 支出 {expense}金 | "
            f"顾客 {customer_count} | 售出 {dishes_sold} | "
            f"声望 {reputation_change:+d}"
        )

    def _calculate_customer_count(
        self,
        area: int,
        reputation: int,
        level: int
    ) -> int:
        """
        计算客流量

        客流 = min(面积席位, 基础客流 × 声望系数)
        基础客流 = 5 + 餐厅等级 × 2
        声望系数 = 1.0 + (声望 / 2000)
        """
        base_customer = 5 + level * 2
        reputation_multiplier = 1.0 + (reputation / 2000.0)
        potential_customer = int(base_customer * reputation_multiplier)

        # 客流不能超过席位
        actual_customer = min(area, potential_customer)

        # 添加随机浮动 ±10%
        variance = int(actual_customer * 0.1)
        actual_customer += random.randint(-variance, variance)

        return max(0, actual_customer)

    async def _chef_cook_dishes(
        self,
        uow: UnitOfWork,
        chef,
        restaurant
    ) -> Dict:
        """
        厨师制作菜品(一小时内)

        Returns:
            {
                "chef_name": str,
                "dishes": [{"name": str, "quality": str, "price": int}, ...],
                "failed": int
            }
        """

        # 1. 从餐厅菜单获取可制作的食谱
        menu_items = await uow.restaurant_menus.get_active_menu(restaurant.id)
        if not menu_items:
            # 没有设置菜单,无法制作
            return {
                "chef_name": chef.name,
                "chef_personality": chef.personality,
                "dishes": [],
                "failed": 0
            }

        # 获取菜单中的食谱ID列表
        available_recipe_ids = [menu.recipe_id for menu in menu_items]

        dishes = []
        failed = 0
        personality_comments = []  # 收集厨师性格旁白

        # 厨师制作菜品(根据速度)
        for i in range(chef.speed):
            # 1. 从菜单随机选择一个食谱
            recipe_id = random.choice(available_recipe_ids)
            recipe = self.recipe_manager.get_recipe(recipe_id)
            if not recipe:
                failed += 1
                continue

            # 2. 检查仓库食材是否足够
            ingredients_available = True
            for item_id, needed_qty in recipe.ingredients.items():
                storage = await uow.restaurant_storage.get_by_restaurant_and_item(
                    restaurant.id, item_id
                )
                if not storage or storage.quantity < needed_qty:
                    ingredients_available = False
                    break

            if not ingredients_available:
                # 食材不足,跳过这道菜(不计入失败)
                continue

            # 3. 判定烹饪成功/失败
            from .cooking_service import CookingService
            cooking_service = CookingService()

            success_rate = cooking_service._calculate_success_rate(
                chef.skill, recipe.category, chef.specialty
            )
            is_success = random.random() * 100 < success_rate

            if is_success:
                # 4a. 成功 - 判定品质
                quality = cooking_service._determine_quality(
                    chef.skill, recipe.category, chef.specialty
                )
                quality_multiplier = cooking_service._get_quality_multiplier(quality)
                dish_price = int(recipe.base_price * quality_multiplier)

                dishes.append({
                    "name": recipe.name,
                    "quality": quality,
                    "price": dish_price,
                    "buff": recipe.buff if quality == DishQuality.PERFECT else None
                })

                # 生成性格旁白
                comment = self._get_personality_comment(chef.personality, True)
                personality_comments.append(comment)

                # 5a. 消耗100%食材
                for item_id, qty in recipe.ingredients.items():
                    await uow.restaurant_storage.consume_ingredient(
                        restaurant.id, item_id, qty
                    )
            else:
                # 4b. 失败 - 产出黑暗料理
                failed += 1
                dishes.append({
                    "name": f"黑暗{recipe.name}",
                    "quality": DishQuality.DARK,
                    "price": int(recipe.base_price * 0.1),
                    "buff": None
                })

                # 生成失败时的性格旁白
                comment = self._get_personality_comment(chef.personality, False)
                personality_comments.append(comment)

                # 5b. 失败消耗50%食材
                for item_id, qty in recipe.ingredients.items():
                    consumed = max(1, int(qty * 0.5))  # 至少消耗1份
                    await uow.restaurant_storage.consume_ingredient(
                        restaurant.id, item_id, consumed
                    )

        return {
            "chef_name": chef.name,
            "chef_personality": chef.personality,
            "dishes": dishes,
            "failed": failed,
            "personality_comments": personality_comments  # 添加性格旁白列表
        }

    def _calculate_reputation_change(
        self,
        customer_count: int,
        dishes_sold: int,
        dishes_failed: int,
        dishes_made: List[Dict]
    ) -> int:
        """
        计算声望变化

        规则:
        - 成功服务: +1~3/顾客
        - 缺货: -2~5
        - 黑暗料理: -2/个
        - 完美菜肴: +5/个
        """

        reputation_change = 0

        # 成功服务的顾客
        reputation_change += dishes_sold * random.randint(1, 3)

        # 缺货惩罚
        unsatisfied_customers = customer_count - dishes_sold
        if unsatisfied_customers > 0:
            reputation_change -= unsatisfied_customers * random.randint(2, 5)

        # 黑暗料理惩罚
        dark_dishes = sum(1 for d in dishes_made if d.get("quality") == DishQuality.DARK)
        reputation_change -= dark_dishes * 2

        # 完美菜肴奖励
        perfect_dishes = sum(1 for d in dishes_made if d.get("quality") == DishQuality.PERFECT)
        reputation_change += perfect_dishes * 5

        return reputation_change

    def _get_personality_comment(
        self,
        personality: str,
        success: bool
    ) -> str:
        """
        根据厨师性格生成旁白文本

        Args:
            personality: 性格类型
            success: 是否成功

        Returns:
            旁白文本
        """

        comments = {
            ChefPersonality.DILIGENT: [
                "擦了擦汗，又熟练地开始准备下一道菜",
                "认真地检查火候，确保每道菜都完美" if success else "虽然失败了，但立刻振作起来重新开始"
            ],
            ChefPersonality.LAZY: [
                "打了个哈欠，慢悠悠地拿起了锅铲",
                "懒洋洋地翻了翻锅" if success else "失败了也不在意，继续摸鱼"
            ],
            ChefPersonality.PERFECTIONIST: [
                "对摆盘不满意，重新调整了三次",
                "挑剔地检查每一个细节" if success else "因为不够完美而沮丧"
            ],
            ChefPersonality.FRUGAL: [
                "心疼地看着用掉的食材，嘟囔着太浪费了",
                "精打细算地控制用量" if success else "浪费了食材而懊恼"
            ],
            ChefPersonality.TALKATIVE: [
                "一边炒菜一边给顾客讲自己当年学艺的故事",
                "滔滔不绝地介绍这道菜的做法" if success else "即使失败了也还在聊天"
            ]
        }

        personality_comments = comments.get(personality, ["默默地工作着"])
        return random.choice(personality_comments)

    async def get_settlement_report(
        self,
        uow: UnitOfWork,
        restaurant_id: int,
        hours: int = 24
    ) -> str:
        """
        获取经营报表(最近N小时)

        Args:
            uow: 工作单元
            restaurant_id: 餐厅ID
            hours: 统计小时数

        Returns:
            报表文本
        """

        stats = await uow.restaurant_logs.get_recent_stats(restaurant_id, hours)
        logs = await uow.restaurant_logs.get_by_restaurant_id(restaurant_id, limit=hours)

        msg = f"📊 经营报表(最近{hours}小时)\n\n"
        msg += f"💰 总收入: {stats['total_income']}金\n"
        msg += f"💸 总支出: {stats['total_expense']}金\n"
        msg += f"📈 净利润: {stats['net_profit']}金\n\n"
        msg += f"👥 总顾客: {stats['total_customers']}人\n"
        msg += f"🍽️ 制作: {stats['total_dishes_made']}道\n"
        msg += f"💀 失败: {stats['total_dishes_failed']}道\n"
        msg += f"⭐ 声望变化: {stats['total_reputation_change']:+d}\n"

        return msg
