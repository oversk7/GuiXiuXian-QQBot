"""
餐厅服务 - 餐厅创建和管理

提供:
- 创建餐厅
- 餐厅升级(等级、面积、厨房)
- 营业状态管理(开店/打烊)
- 食材仓库管理
- 菜单管理
"""

from typing import Tuple, List, Optional, Dict
from datetime import datetime
from nonebot import logger

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.restaurant import Restaurant, RestaurantStorage, RestaurantMenu
from .cooking_service import RecipeManager


class RestaurantService:
    """
    餐厅服务 - 管理餐厅的创建、升级和运营

    职责:
    - 餐厅创建和初始化
    - 餐厅等级、面积、厨房升级
    - 开店/打烊状态管理
    - 食材仓库补货和管理
    - 营业菜单设置
    """

    # 餐厅升级消耗配置（参考公会建筑规模）
    UPGRADE_COSTS = {
        1: {"coin": 50000, "materials": {"spirit_bone": 100, "iron_rust": 80}},
        2: {"coin": 100000, "materials": {"spirit_bone": 150, "iron_rust": 120, "grave_soil": 200}},
        3: {"coin": 200000, "materials": {"yin_essence": 80, "nightmare_silk": 50, "grave_soil": 300}},
        4: {"coin": 400000, "materials": {"yin_essence": 120, "nightmare_silk": 80, "flesh_crystal": 50}},
        5: {"coin": 800000, "materials": {"flesh_crystal": 100, "soul_crystal": 60, "cursed_mirror_shard": 40}},
        6: {"coin": 1500000, "materials": {"flesh_crystal": 150, "soul_crystal": 100, "cursed_mirror_shard": 70}},
        7: {"coin": 2500000, "materials": {"soul_crystal": 150, "cursed_mirror_shard": 100, "demon_heart": 30}},
        8: {"coin": 4000000, "materials": {"demon_heart": 50, "void_essence": 40, "cursed_mirror_shard": 120}},
        9: {"coin": 6000000, "materials": {"demon_heart": 80, "void_essence": 60, "god_tear": 20}},
    }

    # 面积扩张消耗(每次+5席位)
    AREA_EXPANSION_BASE_COST = 2000  # 基础消耗,每次翻倍

    # 厨房升级费用配置
    KITCHEN_UPGRADE_COSTS = {
        2: 20000,   # Lv1→2
        3: 80000,   # Lv2→3
        4: 300000,  # Lv3→4
        5: 800000,  # Lv4→5
    }

    # 仓库升级配置 {仓库等级: (容量, 餐厅等级要求, 金币费用)}
    STORAGE_UPGRADE_CONFIG = {
        2: (100, 2, 5000),
        3: (180, 4, 20000),
        4: (300, 6, 80000),
        5: (500, 8, 200000),
    }

    def __init__(self):
        self.recipe_manager = RecipeManager()

    async def create_restaurant(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        创建餐厅(每个玩家只能拥有一家)

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息)
        """

        # 检查是否已有餐厅
        existing = await uow.restaurants.get_by_player_id(player_id)
        if existing:
            return False, "⛔ 你已经拥有一家餐厅了"

        # 创建餐厅
        restaurant = Restaurant(
            player_id=player_id,
            level=1,
            area=10,  # 初始10席
            kitchen_level=1,
            reputation=0,
            max_chefs=1,  # 初始只能雇1个厨师
            storage_capacity=50,
            is_open=False,  # 默认打烊
            total_income=0,
            total_expense=0,
            created_at=datetime.now(),
            last_settlement=datetime.now()
        )
        await uow.restaurants.add(restaurant)

        # 学会默认食谱(白色家常菜)
        from ..models.player_recipe import PlayerRecipe
        default_recipe_ids = self.recipe_manager.get_default_recipes()

        for recipe_id in default_recipe_ids:
            already_learned = await uow.player_recipes.has_recipe(player_id, recipe_id)
            if already_learned:
                continue
            player_recipe = PlayerRecipe(
                player_id=player_id,
                recipe_id=recipe_id,
                learned_at=datetime.now()
            )
            await uow.player_recipes.add(player_recipe)

        await uow.commit()

        return True, (
            f"🏪 成功创建餐厅!\n\n"
            f"📊 初始状态:\n"
            f"  等级: Lv.{restaurant.level}\n"
            f"  席位: {restaurant.area}席\n"
            f"  厨房等级: Lv.{restaurant.kitchen_level}\n"
            f"  厨师上限: {restaurant.max_chefs}人\n"
            f"  仓库容量: {restaurant.storage_capacity}\n\n"
            f"📖 已自动学会 {len(default_recipe_ids)} 个家常菜食谱\n"
            f"使用【食谱】查看，【烹饪 菜名 数量】开始做菜"
        )

    async def upgrade_restaurant(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        升级餐厅等级

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        if restaurant.level >= 10:
            return False, "⛔ 餐厅已达最高等级(Lv.10)"

        # 获取升级消耗
        next_level = restaurant.level + 1
        cost_config = self.UPGRADE_COSTS.get(restaurant.level)

        if not cost_config:
            return False, f"⛔ 未找到等级 {restaurant.level} 的升级配置"

        # 检查金币
        player = await uow.players.get_by_id(player_id)
        if player.gold < cost_config["coin"]:
            return False, f"⛔ 金币不足! 需要 {cost_config['coin']}金币"

        # 检查材料
        materials = cost_config.get("materials", {})
        missing_materials = []

        for material_id, needed_qty in materials.items():
            material_count = await uow.items.get_material_total_quantity(player_id, material_id)
            if material_count < needed_qty:
                # 获取材料中文名称
                from ..config import config
                material_cfg = config.items_config["by_id"].get(material_id)
                material_name = material_cfg.name if material_cfg else material_id
                missing_materials.append(f"{material_name}(需要{needed_qty},拥有{material_count})")

        if missing_materials:
            return False, f"⛔ 材料不足: {', '.join(missing_materials)}"

        # 扣除消耗
        player.gold -= cost_config["coin"]
        await uow.players.update(player)

        # 扣除材料
        for material_id, qty in materials.items():
            items = await uow.items.get_by_player_and_item_id(player_id, material_id)
            remaining = qty
            for item in items:
                if remaining <= 0:
                    break

                if item.quantity >= remaining:
                    item.quantity -= remaining
                    if item.quantity == 0:
                        await uow.items.delete(item.id)
                    else:
                        await uow.items.update(item)
                    remaining = 0
                else:
                    remaining -= item.quantity
                    await uow.items.delete(item.id)

        # 升级餐厅
        old_level = restaurant.level
        restaurant.level = next_level

        # 更新厨师上限(每2级+1)
        restaurant.max_chefs = 1 + (next_level // 2)

        await uow.restaurants.update(restaurant)
        await uow.commit()

        return True, (
            f"✅ 餐厅升级成功!\n\n"
            f"📊 Lv.{old_level} → Lv.{next_level}\n"
            f"👨‍🍳 厨师上限: {restaurant.max_chefs}人\n"
            f"💰 消耗: {cost_config['coin']}金币"
        )

    async def expand_area(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        扩张餐厅面积(每次+5席)

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        if restaurant.area >= 50:
            return False, "⛔ 面积已达上限(50席)"

        # 计算消耗(每次翻倍)
        expansion_count = (restaurant.area - 10) // 5  # 已扩张次数
        cost = self.AREA_EXPANSION_BASE_COST * (2 ** expansion_count)

        # 检查金币
        player = await uow.players.get_by_id(player_id)
        if player.gold < cost:
            return False, f"⛔ 金币不足! 需要 {cost}金币"

        # 扣除金币
        player.gold -= cost
        await uow.players.update(player)

        # 扩张面积
        old_area = restaurant.area
        restaurant.area += 5
        await uow.restaurants.update(restaurant)

        await uow.commit()

        return True, (
            f"✅ 扩张成功!\n\n"
            f"📊 {old_area}席 → {restaurant.area}席\n"
            f"💰 消耗: {cost}金币"
        )

    async def upgrade_kitchen(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        升级厨房等级

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        if restaurant.kitchen_level >= 5:
            return False, "⛔ 厨房已达最高等级(Lv.5)"

        # 厨房升级要求对应餐厅等级
        required_restaurant_level = {
            2: 3,  # 厨房Lv2需要餐厅Lv3
            3: 5,
            4: 7,
            5: 9
        }

        next_kitchen_level = restaurant.kitchen_level + 1
        required_level = required_restaurant_level.get(next_kitchen_level, 0)

        if restaurant.level < required_level:
            return False, f"⛔ 需要餐厅等级达到 Lv.{required_level} 才能升级厨房"

        # 检查并扣除升级费用
        cost = self.KITCHEN_UPGRADE_COSTS.get(next_kitchen_level, 0)
        if cost > 0:
            player = await uow.players.get_by_id(player_id)
            if player.gold < cost:
                return False, f"⛔ 金币不足! 升级厨房需要 {cost}金币"
            player.gold -= cost
            await uow.players.update(player)

        # 升级厨房
        old_kitchen_level = restaurant.kitchen_level
        restaurant.kitchen_level = next_kitchen_level
        await uow.restaurants.update(restaurant)

        await uow.commit()

        # 解锁提示
        unlock_msg = {
            2: "可制作绿色特色菜",
            3: "可制作蓝色招牌菜",
            4: "可制作紫色宴席菜",
            5: "可制作橙色传说菜"
        }

        return True, (
            f"✅ 厨房升级成功!\n\n"
            f"📊 Lv.{old_kitchen_level} → Lv.{next_kitchen_level}\n"
            f"💰 消耗: {cost}金币\n"
            f"🎉 解锁: {unlock_msg.get(next_kitchen_level, '')}"
        )

    async def upgrade_storage(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str]:
        """
        升级仓库等级(Lv.1-5)

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        if restaurant.storage_level >= 5:
            return False, "⛔ 仓库已达最高等级(Lv.5，容量500)"

        next_level = restaurant.storage_level + 1
        new_capacity, required_restaurant_level, cost = self.STORAGE_UPGRADE_CONFIG[next_level]

        if restaurant.level < required_restaurant_level:
            return False, (
                f"⛔ 仓库升至 Lv.{next_level} 需要餐厅等级达到 Lv.{required_restaurant_level}\n"
                f"当前餐厅等级: Lv.{restaurant.level}"
            )

        player = await uow.players.get_by_id(player_id)
        if player.gold < cost:
            return False, f"⛔ 金币不足! 升级仓库需要 {cost}金币"

        player.gold -= cost
        await uow.players.update(player)

        old_level = restaurant.storage_level
        old_capacity = restaurant.storage_capacity
        restaurant.storage_level = next_level
        restaurant.storage_capacity = new_capacity
        await uow.restaurants.update(restaurant)

        await uow.commit()

        return True, (
            f"✅ 仓库升级成功!\n\n"
            f"📊 Lv.{old_level} → Lv.{next_level}\n"
            f"📦 容量: {old_capacity} → {new_capacity}\n"
            f"💰 消耗: {cost}金币"
        )

    async def toggle_open(
        self,
        uow: UnitOfWork,
        player_id: str,
        is_open: bool
    ) -> Tuple[bool, str]:
        """
        切换营业状态(开店/打烊)

        Args:
            uow: 工作单元
            player_id: 玩家ID
            is_open: True=开店, False=打烊

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        if restaurant.is_open == is_open:
            status_text = "营业中" if is_open else "打烊"
            return False, f"⛔ 餐厅已经是{status_text}状态"

        # 开店时的前置检验
        if is_open:
            chef_count = await uow.chefs.count_by_restaurant(restaurant.id)
            if chef_count == 0:
                return False, "⛔ 无法开店：还没有雇佣任何厨师\n使用【招募厨师】开始招募"

            menu_items = await uow.restaurant_menus.get_active_menu(restaurant.id)
            if not menu_items:
                return False, "⛔ 无法开店：还未设置营业菜单\n使用【设置菜单 菜名1 菜名2】设置菜品"

        restaurant.is_open = is_open
        await uow.restaurants.update(restaurant)
        await uow.commit()

        status_text = "开始营业" if is_open else "暂停营业"
        msg = f"✅ {status_text}!"

        # 开店时检查仓库食材是否充足，给出警告（不阻止）
        if is_open:
            storage_items = await uow.restaurant_storage.get_by_restaurant(restaurant.id)
            total_qty = sum(item.quantity for item in storage_items) if storage_items else 0
            if total_qty == 0:
                msg += "\n\n⚠️ 警告：仓库没有任何食材！厨师将无法制作菜品\n💡 使用【补货 食材名 数量】补充食材"
            elif total_qty < 10:
                msg += f"\n\n⚠️ 警告：仓库食材仅剩 {total_qty} 份，可能很快耗尽\n💡 使用【补货 食材名 数量】补充食材"

        return True, msg

    async def restock_ingredient(
        self,
        uow: UnitOfWork,
        player_id: str,
        item_id: str,
        quantity: int
    ) -> Tuple[bool, str]:
        """
        补货(从玩家背包转移食材到餐厅仓库)

        Args:
            uow: 工作单元
            player_id: 玩家ID
            item_id: 食材ID
            quantity: 数量

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        # 1. 检查背包中是否有足够食材
        item_count = await uow.items.get_material_total_quantity(player_id, item_id)
        if item_count < quantity:
            return False, f"⛔ 背包中食材不足(需要 {quantity},拥有 {item_count})"

        # 2. 检查仓库容量
        current_storage = await uow.restaurant_storage.get_total_quantity_by_restaurant(restaurant.id)
        if current_storage + quantity > restaurant.storage_capacity:
            return False, f"⛔ 餐厅仓库容量不足(当前 {current_storage}/{restaurant.storage_capacity})"

        # 3. 从背包扣除食材
        items = await uow.items.get_by_player_and_item_id(player_id, item_id)
        remaining = quantity
        for item in items:
            if remaining <= 0:
                break

            if item.quantity >= remaining:
                item.quantity -= remaining
                if item.quantity == 0:
                    await uow.items.delete(item.id)
                else:
                    await uow.items.update(item)
                remaining = 0
            else:
                remaining -= item.quantity
                await uow.items.delete(item.id)

        # 4. 添加到餐厅仓库
        storage = await uow.restaurant_storage.get_by_restaurant_and_item(restaurant.id, item_id)
        if storage:
            # 已存在,增加数量
            storage.quantity += quantity
            await uow.restaurant_storage.update(storage)
        else:
            # 新增仓库记录
            new_storage = RestaurantStorage(
                restaurant_id=restaurant.id,
                item_id=item_id,
                quantity=quantity
            )
            await uow.restaurant_storage.add(new_storage)

        await uow.commit()

        # 获取物品名称用于显示
        from ..config import config
        item_cfg = config.items_config["by_id"].get(item_id)
        item_name = item_cfg.name if item_cfg else item_id

        return True, f"✅ 成功补货【{item_name}】× {quantity}\n当前仓库: {current_storage + quantity}/{restaurant.storage_capacity}"

    async def withdraw_ingredient(
        self,
        uow: UnitOfWork,
        player_id: str,
        item_id: str,
        quantity: int
    ) -> Tuple[bool, str]:
        """
        取货(从餐厅仓库转移食材到玩家背包)

        Args:
            uow: 工作单元
            player_id: 玩家ID
            item_id: 食材ID
            quantity: 数量

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        # 1. 检查仓库中是否有足够食材
        storage = await uow.restaurant_storage.get_by_restaurant_and_item(restaurant.id, item_id)
        if not storage or storage.quantity < quantity:
            current_qty = storage.quantity if storage else 0
            return False, f"⛔ 仓库中食材不足(需要 {quantity},拥有 {current_qty})"

        # 2. 检查背包容量
        from ..models.inventory import ItemInstance
        try:
            # 尝试添加到背包(会自动检查容量)
            await ItemInstance.add_item(uow.session, player_id, item_id, quantity)
        except ValueError as e:
            return False, f"⛔ 背包空间不足: {str(e)}"

        # 3. 从仓库扣除食材
        storage.quantity -= quantity
        if storage.quantity == 0:
            # 数量归零,删除仓库记录
            await uow.restaurant_storage.delete(storage)
        else:
            # 更新仓库记录
            await uow.restaurant_storage.update(storage)

        await uow.commit()

        # 获取物品名称用于显示
        from ..config import config
        item_cfg = config.items_config["by_id"].get(item_id)
        item_name = item_cfg.name if item_cfg else item_id

        # 计算当前仓库总量
        current_storage = await uow.restaurant_storage.get_total_quantity_by_restaurant(restaurant.id)

        return True, f"✅ 成功取货【{item_name}】× {quantity}\n当前仓库: {current_storage}/{restaurant.storage_capacity}"

    async def set_menu(
        self,
        uow: UnitOfWork,
        player_id: str,
        recipe_ids: List[str]
    ) -> Tuple[bool, str]:
        """
        设置营业菜单

        Args:
            uow: 工作单元
            player_id: 玩家ID
            recipe_ids: 食谱ID列表

        Returns:
            (是否成功, 消息)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅，请先创建"

        # 1. 验证所有食谱都已学会
        for recipe_id in recipe_ids:
            # 检查食谱是否存在
            recipe = self.recipe_manager.get_recipe(recipe_id)
            if not recipe:
                return False, f"⛔ 食谱不存在: {recipe_id}"

            # 检查玩家是否学会该食谱
            has_recipe = await uow.player_recipes.has_recipe(player_id, recipe_id)
            if not has_recipe:
                return False, f"⛔ 你还没有学会【{recipe.name}】\n使用【食谱图鉴】查看可学习的食谱"

            # 检查厨房等级是否满足
            if recipe.tier == "green" and restaurant.kitchen_level < 2:
                return False, f"⛔ 【{recipe.name}】需要厨房Lv2才能制作"
            elif recipe.tier == "blue" and restaurant.kitchen_level < 3:
                return False, f"⛔ 【{recipe.name}】需要厨房Lv3才能制作"
            elif recipe.tier == "purple" and restaurant.kitchen_level < 4:
                return False, f"⛔ 【{recipe.name}】需要厨房Lv4才能制作"
            elif recipe.tier == "orange" and restaurant.kitchen_level < 5:
                return False, f"⛔ 【{recipe.name}】需要厨房Lv5才能制作"

        # 2. 清除旧菜单
        await uow.restaurant_menus.clear_menu(restaurant.id)

        # 3. 添加新菜单
        from ..models.restaurant import RestaurantMenu
        for recipe_id in recipe_ids:
            menu_item = RestaurantMenu(
                restaurant_id=restaurant.id,
                recipe_id=recipe_id,
                is_active=True
            )
            await uow.restaurant_menus.add(menu_item)

        recipe_names = [self.recipe_manager.get_recipe(rid).name for rid in recipe_ids]
        return True, f"✅ 成功设置菜单 ({len(recipe_ids)}道菜)\n当前菜品: {', '.join(recipe_names)}"

    async def get_restaurant_status(
        self,
        uow: UnitOfWork,
        player_id: str
    ) -> Tuple[bool, str, Optional[Restaurant]]:
        """
        查看餐厅状态

        Args:
            uow: 工作单元
            player_id: 玩家ID

        Returns:
            (是否成功, 消息, 餐厅对象)
        """

        restaurant = await uow.restaurants.get_by_player_id(player_id)
        if not restaurant:
            return False, "⛔ 你还没有餐厅。使用【创建餐厅】开始经营", None

        # 获取厨师数量
        chef_count = await uow.chefs.count_by_restaurant(restaurant.id)

        # 获取仓库使用量
        used_storage = await uow.restaurant_storage.get_total_quantity_by_restaurant(restaurant.id)

        # 营业状态
        status_emoji = "🟢" if restaurant.is_open else "🔴"
        status_text = "营业中" if restaurant.is_open else "打烊"

        msg = (
            f"🏪 餐厅状态\n\n"
            f"📊 等级: Lv.{restaurant.level} | 厨房: Lv.{restaurant.kitchen_level}\n"
            f"🪑 面积: {restaurant.area}席 | {status_emoji} {status_text}\n"
            f"👨‍🍳 厨师: {chef_count}/{restaurant.max_chefs}人\n"
            f"⭐ 声望: {restaurant.reputation}\n"
            f"📦 仓库: Lv.{restaurant.storage_level} | {used_storage}/{restaurant.storage_capacity}\n\n"
            f"💰 累计收入: {restaurant.total_income}金\n"
            f"💸 累计支出: {restaurant.total_expense}金\n"
            f"📈 净利润: {restaurant.total_income - restaurant.total_expense}金"
        )

        return True, msg, restaurant

    async def get_restaurant_ranking(
        self,
        uow: UnitOfWork,
        player_id: str,
        limit: int = 10
    ) -> str:
        """
        获取餐厅排行榜(按声望排序)

        Args:
            uow: 工作单元
            player_id: 当前玩家ID(用于标注自己)
            limit: 显示数量

        Returns:
            排行榜文本
        """
        top_restaurants = await uow.restaurants.get_top_by_reputation(limit)

        if not top_restaurants:
            return "🏆 餐厅排行榜\n\n暂无餐厅数据"

        msg = "🏆 餐厅排行榜 (按声望)\n━━━━━━━━━━━━━\n\n"

        rank_icons = {1: "🥇", 2: "🥈", 3: "🥉"}

        for idx, rest in enumerate(top_restaurants, 1):
            icon = rank_icons.get(idx, f"{idx}.")
            status = "🟢" if rest.is_open else "🔴"
            is_me = " ← 你" if rest.player_id == player_id else ""

            # 获取玩家名
            owner = await uow.players.get_by_id(rest.player_id)
            owner_name = owner.name if owner else "未知"

            net_profit = rest.total_income - rest.total_expense
            msg += (
                f"{icon} {owner_name}的餐厅{is_me}\n"
                f"  Lv.{rest.level} | ⭐{rest.reputation} | {status}\n"
                f"  净利润: {net_profit}金\n\n"
            )

        return msg
