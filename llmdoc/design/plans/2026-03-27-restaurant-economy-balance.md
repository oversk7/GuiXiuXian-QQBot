# Restaurant Economy Balance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement customer tier system, tiered dish matching, and data transparency panels so all recipe tiers have strategic value.

**Architecture:** Modify settlement logic to split customers into 3 tiers (common/wealthy/vip) that only consume matching recipe tiers. Add cost calculation to CookingService. Enhance commands display with customer flow analysis and profit data.

**Tech Stack:** Python 3.12, NoneBot2, SQLAlchemy 2.0, YAML config

**Spec:** `docs/superpowers/specs/2026-03-27-restaurant-economy-balance-design.md`

---

### Task 1: Add customer tier constants and helper to settlement_service.py

**Files:**
- Modify: `plugins/xiuxian_game/cooking/settlement_service.py`

This task adds the configuration constants and two pure helper methods without changing any existing logic yet.

- [ ] **Step 1: Add customer tier constants at class level**

Add after the existing `EVENT_TRIGGER_CHANCE` constant in `SettlementService`:

```python
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
```

- [ ] **Step 2: Add `_get_customer_ratio` helper method**

Add to `SettlementService` class:

```python
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
```

- [ ] **Step 3: Add `_split_customers_by_tier` helper method**

```python
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
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/cooking/settlement_service.py
git commit -m "feat(restaurant): add customer tier constants and helpers"
```

---

### Task 2: Rewrite settlement core logic with tiered customer matching

**Files:**
- Modify: `plugins/xiuxian_game/cooking/settlement_service.py`

This is the core change: rewrite `_settle_restaurant` to use tiered customer matching and the new reputation calculation.

- [ ] **Step 1: Add `_match_dishes_to_customers` method**

This method implements the dish-to-customer matching algorithm from the spec:

```python
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

    Returns:
        {
            "tier_results": {
                "common": {"served": int, "unserved": int, "income": int, "dishes": [...]},
                "wealthy": {...},
                "vip": {...}
            },
            "total_income": int,
            "total_sold": int,
            "unsold_dishes": int,
            "dishes_by_tier": {tier: {"made": int, "sold": int}}
        }
    """
    # 按recipe tier分桶, 每个桶存放该tier的所有菜品
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
        count = customer_counts[customer_type]
        acceptable_tiers = self.CUSTOMER_TIER_RECIPE_MAP[customer_type]

        # 收集该客群可用的菜品,优先高tier
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
        group_income = 0
        for dish in served_dishes:
            group_income += dish["price"]

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
```

- [ ] **Step 2: Rewrite `_settle_restaurant` method**

Replace the existing customer consumption section (steps 3-6 in the original) with the new tiered logic. The key changes are:

1. After cooking (step 2), call `_split_customers_by_tier` to split total customer count
2. Call `_match_dishes_to_customers` to match dishes to customer tiers
3. Apply signature dish bonus within matching (or after)
4. Use new reputation formula
5. Handle random events: `extra_customers` distributed by ratio
6. Generate expanded log details with `customer_breakdown`

Replace the `_settle_restaurant` method body from "# 3. Customers consume" through "# 9. Generate log" with:

```python
        # 3. 按声望拆分客流
        customer_counts = self._split_customers_by_tier(
            customer_count, restaurant.reputation
        )

        # 4. 匹配菜品到客人
        match_result = self._match_dishes_to_customers(dishes_made, customer_counts)
        tier_results = match_result["tier_results"]
        income = match_result["total_income"]
        dishes_sold = match_result["total_sold"]

        # 5. 声望加成应用到收入 (保留原逻辑)
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
                # 额外客人按当前声望比例分配
                extra_counts = self._split_customers_by_tier(
                    abs(extra), restaurant.reputation
                )
                if extra > 0:
                    # 额外客人尝试消费剩余菜品
                    extra_match = self._match_dishes_to_customers(
                        # 从未售出的菜品中匹配
                        [d for d in dishes_made if d not in
                         [dd for tr in tier_results.values() for dd in tr["dishes"]]],
                        extra_counts
                    )
                    income += int(extra_match["total_income"] * reputation_bonus_mult)
                    event_income_bonus += int(extra_match["total_income"] * reputation_bonus_mult)
                    dishes_sold += extra_match["total_sold"]
                    # 更新tier_results
                    for ct in ["common", "wealthy", "vip"]:
                        tier_results[ct]["served"] += extra_match["tier_results"][ct]["served"]
                        customer_counts[ct] += extra_counts[ct]
                elif extra < 0:
                    # 减少客人(已经算过了,只更新customer_count显示)
                    for ct in ["common", "wealthy", "vip"]:
                        customer_counts[ct] = max(0, customer_counts[ct] - extra_counts[ct])
                customer_count += extra

        # 8. 计算声望变化 (新公式: 固定值,按客人类型分别计算)
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
```

- [ ] **Step 3: Update log generation to include customer_breakdown**

Replace the log_details dict:

```python
        # 9. 生成日志 (扩展格式)
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
            "net_profit": income - expense,
            "event": {
                "name": event["name"] if event else None,
                "description": event["description"] if event else None,
                "income_bonus": event_income_bonus,
                "expense_bonus": event_expense_bonus,
                "reputation_bonus": event_reputation_bonus,
            } if event else None
        }
```

- [ ] **Step 4: Remove old `_calculate_reputation_change` method**

The old method is no longer needed since reputation is now calculated inline. Delete the entire `_calculate_reputation_change` method.

- [ ] **Step 5: Commit**

```bash
git add plugins/xiuxian_game/cooking/settlement_service.py
git commit -m "feat(restaurant): rewrite settlement with tiered customer matching"
```

---

### Task 3: Update settlement report with customer flow analysis

**Files:**
- Modify: `plugins/xiuxian_game/cooking/settlement_service.py` (method `get_settlement_report`)

- [ ] **Step 1: Rewrite `get_settlement_report` to include customer flow analysis**

Update the method to parse `customer_breakdown` from logs and display satisfaction rates per tier. Also add recipe profit to top dishes using `CookingService.calculate_recipe_cost`.

Replace the `get_settlement_report` method:

```python
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

        # 客流分析显示
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

        # 产能利用率
        total_made = stats.get("total_dishes_made", 0)
        total_sold = stats.get("total_dishes_made", 0) - stats.get("total_dishes_failed", 0)
        msg += f"\n👥 总顾客: {stats['total_customers']}人\n"
        msg += f"🍽️ 制作: {total_made}道 | 失败: {stats['total_dishes_failed']}道\n"
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
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/cooking/settlement_service.py
git commit -m "feat(restaurant): add customer flow analysis to settlement report"
```

---

### Task 4: Add recipe cost calculation to CookingService

**Files:**
- Modify: `plugins/xiuxian_game/cooking/cooking_service.py`

- [ ] **Step 1: Add `calculate_recipe_cost` method**

Add to `CookingService` class:

```python
    def calculate_recipe_cost(self, recipe_id: str) -> int:
        """
        计算食谱的食材成本

        遍历recipe.ingredients, 查items_config获取每个食材的price, 累加

        Args:
            recipe_id: 食谱ID

        Returns:
            总食材成本(金币), 找不到返回0
        """
        recipe = self.recipe_manager.get_recipe(recipe_id)
        if not recipe:
            return 0

        from ..config import config
        total_cost = 0
        for item_id, qty in recipe.ingredients.items():
            item_cfg = config.items_config["by_id"].get(item_id)
            if item_cfg:
                total_cost += item_cfg.price * qty

        return total_cost
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/cooking/cooking_service.py
git commit -m "feat(cooking): add recipe cost calculation method"
```

---

### Task 5: Add customer flow estimate to RestaurantService

**Files:**
- Modify: `plugins/xiuxian_game/cooking/restaurant_service.py`

- [ ] **Step 1: Add `estimate_customer_flow` method**

Add to `RestaurantService` class:

```python
    def estimate_customer_flow(
        self,
        area: int,
        reputation: int,
        level: int
    ) -> Dict:
        """
        预估客流量和分层(供【餐厅】命令显示)

        Returns:
            {
                "total": int,
                "common": int, "wealthy": int, "vip": int,
                "common_pct": float, "wealthy_pct": float, "vip_pct": float
            }
        """
        from .settlement_service import SettlementService
        ss = SettlementService()

        base_customer = 5 + level * 2
        reputation_multiplier = 1.0 + (reputation / 2000.0)
        potential = int(base_customer * reputation_multiplier)
        total = min(area, potential)

        ratio = ss._get_customer_ratio(reputation)
        wealthy_count = int(total * ratio["wealthy"])
        vip_count = int(total * ratio["vip"])
        common_count = total - wealthy_count - vip_count

        return {
            "total": total,
            "common": common_count,
            "wealthy": wealthy_count,
            "vip": vip_count,
            "common_pct": ratio["common"] * 100,
            "wealthy_pct": ratio["wealthy"] * 100,
            "vip_pct": ratio["vip"] * 100,
        }
```

- [ ] **Step 2: Update `get_restaurant_status` to show customer flow and capacity info**

Replace the existing `get_restaurant_status` method's message generation section:

```python
        # 客流预估
        flow = self.estimate_customer_flow(
            restaurant.area, restaurant.reputation, restaurant.level
        )

        # 获取厨师产能
        chefs = await uow.chefs.get_by_restaurant_id(restaurant.id)
        total_speed = sum(c.speed for c in chefs) if chefs else 0

        # 最近一次结算的产能利用率
        logs = await uow.restaurant_logs.get_by_restaurant_id(restaurant.id, limit=1)
        capacity_text = ""
        if logs and total_speed > 0:
            import json
            try:
                details = json.loads(logs[0].details_json)
                sold = details.get("dishes_sold", 0)
                made = logs[0].dishes_made
                if made > 0:
                    util_rate = int(sold / made * 100)
                    capacity_text = f"\n  产能利用率: {util_rate}% (上小时售出{sold}/{made}道)"
            except (json.JSONDecodeError, TypeError):
                pass

        # 24h收支摘要
        stats = await uow.restaurant_logs.get_recent_stats(restaurant.id, 24)

        msg = (
            f"🏪 餐厅状态 Lv.{restaurant.level}\n"
            f"━━━━━━━━━━━━━\n"
            f"📊 基础信息\n"
            f"  席位: {restaurant.area} | 厨房: Lv.{restaurant.kitchen_level} | "
            f"仓库: Lv.{restaurant.storage_level} ({used_storage}/{restaurant.storage_capacity})\n"
            f"  声望: {restaurant.reputation} | {status_emoji} {status_text}\n"
            f"\n👥 客流概况 (当前声望下)\n"
            f"  预计客流: ~{flow['total']}人/时\n"
            f"  ├ 普通食客: ~{flow['common']}人 ({flow['common_pct']:.0f}%) → 消费白/绿菜\n"
            f"  ├ 富商: ~{flow['wealthy']}人 ({flow['wealthy_pct']:.0f}%) → 消费绿/蓝/紫菜\n"
            f"  └ 贵宾: ~{flow['vip']}人 ({flow['vip_pct']:.0f}%) → 消费紫/橙菜\n"
            f"\n⚙️ 产能\n"
            f"  厨师: {chef_count}/{restaurant.max_chefs}人 | "
            f"总产能: {total_speed}道/时{capacity_text}\n"
            f"\n💰 近24h摘要\n"
            f"  收入: {stats['total_income']}金 | 支出: {stats['total_expense']}金\n"
            f"  净利润: {stats['net_profit']}金"
        )
```

- [ ] **Step 3: Commit**

```bash
git add plugins/xiuxian_game/cooking/restaurant_service.py
git commit -m "feat(restaurant): add customer flow estimate and enhanced status display"
```

---

### Task 6: Add dish profit command and update commands.py

**Files:**
- Modify: `plugins/xiuxian_game/cooking/commands.py`

- [ ] **Step 1: Add the 【菜品利润】 command**

Add after the `recipe_guide_cmd` handler:

```python
# ==================== 菜品利润分析 ====================

dish_profit_cmd = on_command("菜品利润", aliases={"利润分析"}, priority=5, block=True)


@dish_profit_cmd.handle()
async def handle_dish_profit(event: MessageEvent):
    """【菜品利润】- 查看菜品利润分析"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await dish_profit_cmd.finish("⛔ 请先创建角色")

        recipes = await cooking_service.get_player_recipes(uow, player.id)

        if not recipes:
            await dish_profit_cmd.finish("⛔ 你还没有学会任何食谱\n使用【食谱图鉴】查看所有食谱")

        # 客群映射
        tier_customer_map = {
            "white": "普通食客",
            "green": "普通/富商",
            "blue": "富商",
            "purple": "富商/贵宾",
            "orange": "贵宾"
        }

        tier_names = {
            "white": "白", "green": "绿", "blue": "蓝",
            "purple": "紫", "orange": "橙"
        }

        msg = "📋 菜品利润分析\n━━━━━━━━━━━━━\n"

        # 按tier分组
        for tier in ["white", "green", "blue", "purple", "orange"]:
            tier_recipes = [r for r in recipes if r.tier == tier]
            if not tier_recipes:
                continue

            for recipe in tier_recipes:
                cost = cooking_service.calculate_recipe_cost(recipe.recipe_id)
                profit = recipe.base_price - cost
                profit_rate = int(profit / cost * 100) if cost > 0 else 0
                customer = tier_customer_map.get(recipe.tier, "")

                msg += (
                    f"  {recipe.name}({tier_names[tier]}) | "
                    f"售{recipe.base_price} 本{cost} "
                    f"利{profit}({profit_rate}%) | "
                    f"{customer}\n"
                )

        msg += "\n💡 菜单应覆盖各层客群，避免客人吃不到合适的菜"

        await dish_profit_cmd.finish(msg)
```

- [ ] **Step 2: Commit**

```bash
git add plugins/xiuxian_game/cooking/commands.py
git commit -m "feat(restaurant): add dish profit analysis command"
```

---

### Task 7: Update help.py and knowledge YAML

**Files:**
- Modify: `plugins/xiuxian_game/player/help.py`
- Modify: `plugins/xiuxian_game/data/knowledge/cooking_help.yaml`

- [ ] **Step 1: Update help.py cooking section**

In the cooking handler's content string, add the profit command to the report section:

Find the line:
```python
        f"{cmd('经营报表')} 24h收支 | {cmd('经营日志')} 详细日志 | {cmd('餐厅排行')} 声望排行\n"
```

Replace with:
```python
        f"{cmd('经营报表')} 24h收支 | {cmd('经营日志')} 详细日志 | {cmd('餐厅排行')} 声望排行\n"
        f"{cmd('菜品利润')} 查看各菜品利润率和适合客群\n"
```

Also add explanation about customer tiers after the "**菜肴品质**" section:

```python
        "***\n"
        "**客流分层**\n"
        "普通食客(60%) 只点白/绿菜 | 富商(30%) 点绿/蓝/紫菜 | 贵宾(10%) 只点紫/橙菜\n"
        "声望越高,富商和贵宾比例越大 | 菜单需混搭覆盖各层客群\n"
```

- [ ] **Step 2: Update cooking_help.yaml**

Add keywords `菜品利润`, `利润分析`, `客流分层`, `客流` to the keywords list.

In the body, add to the 📊 经营报表 section:
```
  【菜品利润】 查看各菜品售价、成本、利润率和适合客群
```

Add a new section before 重要提示:
```
  ━━━━━━━━━━━━━
  👥 客流分层：
  餐厅客人分为三种类型，各自偏好不同等级的菜品：
  • 普通食客(60%) → 只消费白色/绿色菜品（量大）
  • 富商(30%) → 消费绿色/蓝色/紫色菜品（中高消费）
  • 贵宾(10%) → 只消费紫色/橙色菜品（稀少高消费）
  声望越高，富商和贵宾比例越大（最高各40%/20%）
  💡 菜单应混搭覆盖各层客群，全上最贵的菜反而会亏！
  💡 使用【菜品利润】查看每道菜的利润和适合客群
```

Update the 重要提示 section, change:
```
  • 声望影响客流：完美菜肴+5声望，缺货-2~5声望
```
to:
```
  • 声望影响客流：满足客人+声望，客人吃不到菜-声望
  • 不同客群惩罚不同：富商不满-5，普通食客-3，贵宾-2
```

- [ ] **Step 3: Update the help.py command card to include 菜品利润**

Find the cooking card in the `MODULE_CARDS` section:
```python
    ("烹饪餐厅", "#f97316", [
        "【创建餐厅】 【餐厅】 【开店/打烊】",
        "【招募厨师】 【雇佣 编号】",
        "【烹饪 菜名 数量】 【食谱】",
        "【补货/取货 食材名 数量】",
        "【设置菜单 菜名...】 【菜单】",
        "【经营报表】 【经营日志】",
```

Add `【菜品利润】` to the last line:
```python
        "【经营报表】 【经营日志】 【菜品利润】",
```

- [ ] **Step 4: Commit**

```bash
git add plugins/xiuxian_game/player/help.py plugins/xiuxian_game/data/knowledge/cooking_help.yaml
git commit -m "docs(restaurant): update help and knowledge base with customer tiers and profit command"
```

---

### Task 8: Final integration commit and deploy

**Files:** None (verification only)

- [ ] **Step 1: Verify no syntax errors**

```bash
cd D:/QQbot/GuiXiuXian2 && python -c "from plugins.xiuxian_game.cooking.settlement_service import SettlementService; from plugins.xiuxian_game.cooking.cooking_service import CookingService; from plugins.xiuxian_game.cooking.restaurant_service import RestaurantService; print('All imports OK')"
```

- [ ] **Step 2: Git push and deploy**

```bash
git push
```

Then SSH to server and pull:
```bash
ssh root@***REMOVED*** "su - admin -c 'cd /home/admin/GuiXiuXian2 && git pull'"
```

- [ ] **Step 3: Update spec status**

In `docs/superpowers/specs/2026-03-27-restaurant-economy-balance-design.md`, change status from "设计完成，待实现" to "已完成".
