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
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.restaurant_log import RestaurantLog
from ..models.chef import ChefPersonality
from .cooking_service import CookingService, RecipeManager, DishQuality
from .chef_service import ChefService


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
        self.cooking_service = CookingService()
        self.chef_service = ChefService()

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

        # 3. 按声望拆分客流为3层
        customer_counts = self._split_customers_by_tier(
            customer_count, restaurant.reputation
        )

        # 4. 匹配菜品到客人 (分层消费)
        match_result = self._match_dishes_to_customers(dishes_made, customer_counts)
        tier_results = match_result["tier_results"]
        income = match_result["total_income"]
        dishes_sold = match_result["total_sold"]

        # 5. 声望加成应用到收入
        reputation_bonus_mult = 1.0 + (restaurant.reputation / 5000.0)
        income = int(income * reputation_bonus_mult)

        # 招牌菜加成 (对已售出的招牌菜额外+30%)
        signature_id = getattr(restaurant, 'signature_recipe_id', None)
        if signature_id:
            for tier_name, tr in tier_results.items():
                for dish in tr["dishes"]:
                    if dish.get("recipe_id") == signature_id:
                        sig_bonus = int(dish["price"] * reputation_bonus_mult * 0.3)
                        income += sig_bonus

        # 6. 扣除厨师工资
        expense = sum(chef.salary for chef in chefs)

        # 7. 随机经营事件
        event = self._roll_random_event(restaurant.level)
        event_income_bonus = 0
        event_expense_bonus = 0
        event_reputation_bonus = 0

        if event:
            effect = event["effect"]
            if "income_mult" in effect:
                bonus = int(income * (effect["income_mult"] - 1.0))
                income += bonus
                event_income_bonus = bonus
            if "expense_mult" in effect:
                bonus = int(expense * (effect["expense_mult"] - 1.0))
                expense += bonus
                event_expense_bonus = bonus
            if "reputation" in effect:
                event_reputation_bonus = effect["reputation"]
            if "extra_customers" in effect:
                extra = effect["extra_customers"]
                # 额外客人按当前声望比例分配到三个层级
                extra_counts = self._split_customers_by_tier(
                    abs(extra), restaurant.reputation
                )
                if extra > 0:
                    # 收集未售出的菜品
                    sold_dishes = set()
                    for tr in tier_results.values():
                        for d in tr["dishes"]:
                            sold_dishes.add(id(d))
                    unsold_dishes = [d for d in dishes_made if id(d) not in sold_dishes]
                    # 额外客人消费剩余菜品
                    extra_match = self._match_dishes_to_customers(unsold_dishes, extra_counts)
                    extra_income = int(extra_match["total_income"] * reputation_bonus_mult)
                    income += extra_income
                    event_income_bonus += extra_income
                    dishes_sold += extra_match["total_sold"]
                    for ct in ["common", "wealthy", "vip"]:
                        tier_results[ct]["served"] += extra_match["tier_results"][ct]["served"]
                        customer_counts[ct] += extra_counts[ct]
                elif extra < 0:
                    for ct in ["common", "wealthy", "vip"]:
                        customer_counts[ct] = max(0, customer_counts[ct] - extra_counts[ct])
                customer_count += extra

        # 8. 计算声望变化 (固定值，按客人类型分别计算)
        reputation_change = 0
        for ct in ["common", "wealthy", "vip"]:
            reputation_change += tier_results[ct]["served"] * self.SATISFACTION_BONUS[ct]
            reputation_change -= tier_results[ct]["unserved"] * self.DISSATISFACTION_PENALTY[ct]

        # 完美菜肴额外奖励 (保留)
        perfect_dishes = sum(1 for d in dishes_made if d.get("quality") == DishQuality.PERFECT)
        reputation_change += perfect_dishes * 5

        # 黑暗料理惩罚 (保留)
        dark_dishes = sum(1 for d in dishes_made if d.get("quality") == DishQuality.DARK)
        reputation_change -= dark_dishes * 2

        reputation_change += event_reputation_bonus

        # 9. 将净利润入账玩家金币
        net_profit = income - expense
        player = await uow.players.get_by_id(restaurant.player_id)
        if player:
            player.gold += net_profit  # 净利润可能为负(亏损)
            if player.gold < 0:
                player.gold = 0
            await uow.players.update(player)

        # 8. 更新餐厅数据
        restaurant.total_income += income
        restaurant.total_expense += expense
        restaurant.reputation = max(0, min(10000, restaurant.reputation + reputation_change))
        restaurant.last_settlement = period_start
        await uow.restaurants.update(restaurant)

        # 11. 生成日志 (扩展格式含客流分层)
        log_details = {
            "customer_count": customer_count,
            "customer_breakdown": {
                ct: {
                    "total": customer_counts[ct],
                    "served": tier_results[ct]["served"],
                    "unserved": tier_results[ct]["unserved"]
                }
                for ct in ["common", "wealthy", "vip"]
            },
            "dishes_sold": dishes_sold,
            "unsold_dishes": match_result["unsold_dishes"],
            "dishes_by_tier": match_result["dishes_by_tier"],
            "chef_details": chef_details,
            "dishes_made": dishes_made,
            "reputation_change": reputation_change,
            "net_profit": net_profit,
            "event": {
                "name": event["name"] if event else None,
                "description": event["description"] if event else None,
                "income_bonus": event_income_bonus,
                "expense_bonus": event_expense_bonus,
                "reputation_bonus": event_reputation_bonus,
            } if event else None
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
            success_rate = self.cooking_service._calculate_success_rate(
                chef.skill, recipe.category, chef.specialty
            )
            is_success = random.random() * 100 < success_rate

            if is_success:
                # 4a. 成功 - 判定品质
                quality = self.cooking_service._determine_quality(
                    chef.skill, recipe.category, chef.specialty
                )
                quality_multiplier = self.cooking_service._get_quality_multiplier(quality)
                dish_price = int(recipe.base_price * quality_multiplier)

                dishes.append({
                    "name": recipe.name,
                    "recipe_id": recipe.recipe_id,
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
                    "recipe_id": recipe.recipe_id,
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

        # 计算并发放厨师经验
        exp_gained = 0
        for dish in dishes:
            if dish["quality"] == DishQuality.DARK:
                exp_gained += self.chef_service.EXP_PER_DISH_FAIL
            elif dish["quality"] == DishQuality.PERFECT:
                exp_gained += self.chef_service.EXP_PER_DISH_PERFECT
            else:
                exp_gained += self.chef_service.EXP_PER_DISH_SUCCESS

        can_promote = False
        if exp_gained > 0:
            _, can_promote = self.chef_service.add_chef_experience(chef, exp_gained)
            await uow.chefs.update(chef)

        return {
            "chef_name": chef.name,
            "chef_personality": chef.personality,
            "dishes": dishes,
            "failed": failed,
            "personality_comments": personality_comments,
            "exp_gained": exp_gained,
            "can_promote": can_promote
        }

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

    # 随机经营事件配置
    RANDOM_EVENTS = [
        # 正面事件
        {
            "name": "美食评论家来访",
            "description": "一位著名的美食评论家来到你的餐厅品尝，大为赞赏!",
            "type": "positive",
            "weight": 8,
            "min_level": 1,
            "effect": {"reputation": 15}
        },
        {
            "name": "节日旺季",
            "description": "恰逢节日，街上人流如潮，餐厅生意火爆!",
            "type": "positive",
            "weight": 10,
            "min_level": 1,
            "effect": {"extra_customers": 5}
        },
        {
            "name": "回头客推荐",
            "description": "几位老顾客带了朋友来捧场，口碑传播效果显著!",
            "type": "positive",
            "weight": 12,
            "min_level": 2,
            "effect": {"extra_customers": 3, "reputation": 5}
        },
        {
            "name": "达官贵人包场",
            "description": "一位达官贵人看中了你的餐厅，出手阔绰!",
            "type": "positive",
            "weight": 5,
            "min_level": 3,
            "effect": {"income_mult": 1.5}
        },
        {
            "name": "灵气充沛",
            "description": "今日灵气充沛，厨师们状态极佳，做出的菜品格外美味!",
            "type": "positive",
            "weight": 8,
            "min_level": 1,
            "effect": {"reputation": 8, "income_mult": 1.2}
        },
        # 负面事件
        {
            "name": "食材涨价",
            "description": "市场食材价格上涨，本次经营成本增加!",
            "type": "negative",
            "weight": 10,
            "min_level": 1,
            "effect": {"expense_mult": 1.5}
        },
        {
            "name": "隔壁新店开张",
            "description": "隔壁开了一家新餐厅，分流了不少客人...",
            "type": "negative",
            "weight": 8,
            "min_level": 2,
            "effect": {"extra_customers": -3, "reputation": -3}
        },
        {
            "name": "卫生抽查",
            "description": "修仙城管进行卫生抽查，罚了一笔金币...",
            "type": "negative",
            "weight": 6,
            "min_level": 1,
            "effect": {"expense_mult": 2.0, "reputation": -5}
        },
        {
            "name": "大雨天气",
            "description": "瓢泼大雨，街上行人稀少，客流明显减少...",
            "type": "negative",
            "weight": 10,
            "min_level": 1,
            "effect": {"extra_customers": -4}
        },
    ]

    # 事件触发概率 (每次结算有此概率触发事件)
    EVENT_TRIGGER_CHANCE = 0.25  # 25%

    # 客人类型与接受的菜品等级映射
    CUSTOMER_TIER_RECIPE_MAP = {
        "common":  ["white", "green"],
        "wealthy": ["green", "blue", "purple"],
        "vip":     ["purple", "orange"]
    }

    # 声望区间对应的客流比例
    REPUTATION_CUSTOMER_RATIO = [
        (0,     {"common": 0.65, "wealthy": 0.28, "vip": 0.07}),
        (1000,  {"common": 0.60, "wealthy": 0.30, "vip": 0.10}),
        (3000,  {"common": 0.52, "wealthy": 0.35, "vip": 0.13}),
        (5000,  {"common": 0.45, "wealthy": 0.38, "vip": 0.17}),
        (8000,  {"common": 0.40, "wealthy": 0.40, "vip": 0.20}),
    ]

    # 声望满意奖励 (固定值，可预测)
    SATISFACTION_BONUS = {
        "common": 1,
        "wealthy": 3,
        "vip": 8
    }

    # 声望不满惩罚 (固定值)
    DISSATISFACTION_PENALTY = {
        "common": 3,
        "wealthy": 5,
        "vip": 2
    }

    def _roll_random_event(self, restaurant_level: int) -> Optional[Dict]:
        """
        随机roll经营事件

        Args:
            restaurant_level: 餐厅等级

        Returns:
            事件字典或None(未触发)
        """
        # 先判断是否触发事件
        if random.random() > self.EVENT_TRIGGER_CHANCE:
            return None

        # 筛选符合等级要求的事件
        eligible = [
            e for e in self.RANDOM_EVENTS
            if e["min_level"] <= restaurant_level
        ]

        if not eligible:
            return None

        weights = [e["weight"] for e in eligible]
        return random.choices(eligible, weights=weights, k=1)[0]

    def _match_dishes_to_customers(
        self,
        dishes_made: List[Dict],
        customer_counts: Dict[str, int]
    ) -> Dict:
        """
        按客人类型匹配菜品

        分配优先级: common -> wealthy -> vip
        每组客人只消费CUSTOMER_TIER_RECIPE_MAP中对应tier的菜品
        同一客群有多个可消费tier时,优先消费最高tier
        """
        # 按recipe tier分桶
        tier_order = ["orange", "purple", "blue", "green", "white"]
        dish_pool = {t: [] for t in tier_order}
        for dish in dishes_made:
            recipe = self.recipe_manager.get_recipe(dish.get("recipe_id", ""))
            if recipe:
                dish_pool[recipe.tier].append(dish)

        # 统计每tier做了多少道
        dishes_by_tier = {}
        for t in tier_order:
            if dish_pool[t]:
                dishes_by_tier[t] = {"made": len(dish_pool[t]), "sold": 0}

        tier_results = {}
        total_income = 0
        total_sold = 0

        # 按优先级分配: common -> wealthy -> vip
        for customer_type in ["common", "wealthy", "vip"]:
            count = customer_counts.get(customer_type, 0)
            acceptable_tiers = self.CUSTOMER_TIER_RECIPE_MAP[customer_type]

            # 收集该客群可用的菜品,优先高tier (tier_order已按高→低排列)
            available = []
            for t in tier_order:
                if t in acceptable_tiers:
                    available.extend(dish_pool[t])

            served = min(count, len(available))
            served_dishes = available[:served]

            # 从dish_pool中移除已消费的菜品
            for dish in served_dishes:
                recipe = self.recipe_manager.get_recipe(dish.get("recipe_id", ""))
                if recipe and dish in dish_pool[recipe.tier]:
                    dish_pool[recipe.tier].remove(dish)
                    if recipe.tier in dishes_by_tier:
                        dishes_by_tier[recipe.tier]["sold"] += 1

            # 计算该组收入
            group_income = sum(dish["price"] for dish in served_dishes)

            tier_results[customer_type] = {
                "served": served,
                "unserved": count - served,
                "income": group_income,
                "dishes": served_dishes
            }
            total_income += group_income
            total_sold += served

        unsold = len(dishes_made) - total_sold

        return {
            "tier_results": tier_results,
            "total_income": total_income,
            "total_sold": total_sold,
            "unsold_dishes": unsold,
            "dishes_by_tier": dishes_by_tier
        }

    def _get_customer_ratio(self, reputation: int) -> Dict[str, float]:
        """
        根据声望获取客流比例
        查表逻辑：取不超过当前声望的最大阈值对应的比例
        """
        result = self.REPUTATION_CUSTOMER_RATIO[0][1]
        for threshold, ratio in self.REPUTATION_CUSTOMER_RATIO:
            if reputation >= threshold:
                result = ratio
            else:
                break
        return result

    def _split_customers_by_tier(
        self,
        total_customers: int,
        reputation: int
    ) -> Dict[str, int]:
        """
        将总客流按声望比例拆分为3组
        取整后剩余人数归入common层
        """
        ratio = self._get_customer_ratio(reputation)
        wealthy_count = int(total_customers * ratio["wealthy"])
        vip_count = int(total_customers * ratio["vip"])
        common_count = total_customers - wealthy_count - vip_count
        return {
            "common": max(0, common_count),
            "wealthy": max(0, wealthy_count),
            "vip": max(0, vip_count)
        }

    async def get_settlement_report(
        self,
        uow: UnitOfWork,
        restaurant_id: int,
        hours: int = 24
    ) -> str:
        stats = await uow.restaurant_logs.get_recent_stats(restaurant_id, hours)
        logs = await uow.restaurant_logs.get_by_restaurant_id(restaurant_id, limit=hours)

        msg = f"📊 经营报表(最近{hours}小时)\n\n"
        msg += f"💰 收入: {stats['total_income']}金 | 支出: {stats['total_expense']}金\n"
        msg += f"📈 净利润: {stats['net_profit']}金\n"

        # 客流分析 (聚合所有日志的customer_breakdown)
        tier_totals = {ct: {"total": 0, "served": 0} for ct in ["common", "wealthy", "vip"]}
        dish_sales = {}
        chef_stats = {}

        for log in logs:
            try:
                details = json.loads(log.details_json)
            except (json.JSONDecodeError, TypeError):
                continue

            # 聚合客流分层数据
            breakdown = details.get("customer_breakdown")
            if breakdown:
                for ct in ["common", "wealthy", "vip"]:
                    if ct in breakdown:
                        tier_totals[ct]["total"] += breakdown[ct].get("total", 0)
                        tier_totals[ct]["served"] += breakdown[ct].get("served", 0)

            # 统计菜品销量
            for dish in details.get("dishes_made", []):
                name = dish.get("name", "")
                if name and dish.get("quality") != DishQuality.DARK:
                    if name not in dish_sales:
                        dish_sales[name] = {"count": 0, "recipe_id": dish.get("recipe_id", "")}
                    dish_sales[name]["count"] += 1

            # 统计厨师绩效
            for chef_detail in details.get("chef_details", []):
                cname = chef_detail.get("chef_name", "")
                if not cname:
                    continue
                if cname not in chef_stats:
                    chef_stats[cname] = {"made": 0, "failed": 0}
                chef_stats[cname]["made"] += len(chef_detail.get("dishes", []))
                chef_stats[cname]["failed"] += chef_detail.get("failed", 0)

        # 客流分析显示 (向后兼容: 旧日志无breakdown时不显示)
        has_breakdown = any(tier_totals[ct]["total"] > 0 for ct in tier_totals)
        if has_breakdown:
            tier_names = {"common": "普通食客", "wealthy": "富商", "vip": "贵宾"}
            msg += "\n👥 客流分析\n"
            for ct in ["common", "wealthy", "vip"]:
                total = tier_totals[ct]["total"]
                served = tier_totals[ct]["served"]
                if total > 0:
                    rate = served / total * 100
                    warn = ""
                    if rate < 50:
                        acceptable = self.CUSTOMER_TIER_RECIPE_MAP[ct]
                        tier_cn = {"white": "白", "green": "绿", "blue": "蓝", "purple": "紫", "orange": "橙"}
                        need_tiers = "/".join(tier_cn.get(t, t) for t in acceptable)
                        warn = f" ⚠️ 缺少{need_tiers}色菜品!"
                    msg += f"  {tier_names[ct]}: {total}人 → 满足{served}人({rate:.0f}%){warn}\n"

        msg += f"\n👥 总顾客: {stats['total_customers']}人\n"
        msg += f"🍽️ 制作: {stats['total_dishes_made']}道 | 失败: {stats['total_dishes_failed']}道\n"
        msg += f"⭐ 声望变化: {int(stats['total_reputation_change']):+d}\n"

        # TOP3 热门菜品 (含利润)
        if dish_sales:
            msg += "\n🔥 热门菜品 TOP3:\n"
            sorted_dishes = sorted(dish_sales.items(), key=lambda x: x[1]["count"], reverse=True)[:3]
            for i, (name, data) in enumerate(sorted_dishes, 1):
                profit_text = ""
                recipe_id = data.get("recipe_id", "")
                if recipe_id:
                    cost = self.cooking_service.calculate_recipe_cost(recipe_id)
                    recipe = self.recipe_manager.get_recipe(recipe_id)
                    if recipe and cost > 0:
                        profit_per = recipe.base_price - cost
                        total_profit = profit_per * data["count"]
                        profit_text = f" 利润{total_profit}金"
                msg += f"  {i}. {name} ({data['count']}份){profit_text}\n"

        # 厨师绩效
        if chef_stats:
            msg += "\n👨‍🍳 厨师绩效:\n"
            sorted_chefs = sorted(chef_stats.items(), key=lambda x: x[1]["made"], reverse=True)
            for cname, cstat in sorted_chefs:
                total = cstat["made"] + cstat["failed"]
                success_rate = int(cstat["made"] / total * 100) if total > 0 else 0
                msg += f"  {cname}: {cstat['made']}道 | 成功率{success_rate}%\n"

        return msg
