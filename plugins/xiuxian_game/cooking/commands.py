"""
烹饪与餐厅系统 - 指令处理器

包含所有烹饪和餐厅相关的指令:
- 烹饪、食谱
- 餐厅创建、升级、状态查看
- 开店、打烊
- 厨师招募、雇佣、解雇、查看
- 经营报表
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent
from nonebot.params import CommandArg
from nonebot.typing import T_State
from nonebot.adapters.qq import Message

from ..models.db import AsyncSessionLocal
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..platform_utils import get_unified_player
from ..utils_markdown import cmd, build_markdown
from .cooking_service import CookingService, RecipeManager
from .chef_service import ChefService
from .restaurant_service import RestaurantService
from .settlement_service import SettlementService

# ==================== 服务实例 ====================

cooking_service = CookingService()
chef_service = ChefService()
restaurant_service = RestaurantService()
settlement_service = SettlementService()
recipe_manager = RecipeManager()

# ==================== 烹饪相关指令 ====================

cook_cmd = on_command("烹饪", aliases={"做菜", "制作菜肴"}, priority=5, block=True)


@cook_cmd.handle()
async def handle_cook(event: MessageEvent, args: Message = CommandArg()):
    """【烹饪 菜名 数量】- 手动制作菜肴"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await cook_cmd.finish("⛔ 用法: 烹饪 <菜名> [数量]\n例如: 烹饪 红烧鲤鱼 2")

    # 解析参数
    parts = args_text.split()
    dish_name = parts[0]
    quantity = 1

    if len(parts) > 1:
        try:
            quantity = int(parts[1])
            if quantity <= 0 or quantity > 99:
                await cook_cmd.finish("⛔ 数量必须在 1-99 之间")
        except ValueError:
            await cook_cmd.finish("⛔ 数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        # 获取玩家
        player = await get_unified_player(uow.session, event)
        if not player:
            await cook_cmd.finish("⛔ 请先创建角色")

        # 根据菜名查找食谱
        recipe = recipe_manager.get_recipe_by_name(dish_name)
        if not recipe:
            await cook_cmd.finish(f"⛔ 未找到菜肴【{dish_name}】\n使用【食谱】查看已学会的食谱")

        # 烹饪
        success, msg, dishes = await cooking_service.cook_dish(
            uow, player.id, recipe.recipe_id, quantity
        )

        await cook_cmd.finish(build_markdown(msg + f"\n***\n{cmd('食谱')} | {cmd('烹饪 菜名', '烹饪 ')} | {cmd('菜品利润')} | {cmd('食谱图鉴')}"))


recipes_cmd = on_command("食谱", aliases={"我的食谱", "已学食谱"}, priority=5, block=True)


@recipes_cmd.handle()
async def handle_recipes(event: MessageEvent):
    """【食谱】- 查看已学会的食谱"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await recipes_cmd.finish("⛔ 请先创建角色")

        recipes = await cooking_service.get_player_recipes(uow, player.id)

        if not recipes:
            await recipes_cmd.finish("⛔ 你还没有学会任何食谱")

        # 按稀有度分组
        recipes_by_tier = {
            "white": [],
            "green": [],
            "blue": [],
            "purple": [],
            "orange": []
        }

        for recipe in recipes:
            recipes_by_tier[recipe.tier].append(recipe)

        # 生成消息
        msg = "# 📖 已学会的食谱\n***\n"

        tier_names = {
            "white": "⚪ 家常菜",
            "green": "🟢 特色菜",
            "blue": "🔵 招牌菜",
            "purple": "🟣 宴席菜",
            "orange": "🟠 传说菜"
        }

        for tier, tier_name in tier_names.items():
            tier_recipes = recipes_by_tier[tier]
            if tier_recipes:
                msg += f"**{tier_name}**\n"
                for recipe in tier_recipes:
                    # 将食材ID转换为中文名称
                    from ..config import config
                    ingredients_parts = []
                    for item_id, qty in recipe.ingredients.items():
                        item_cfg = config.items_config["by_id"].get(item_id)
                        item_name = item_cfg.name if item_cfg else item_id
                        ingredients_parts.append(f"{item_name}×{qty}")
                    ingredients_text = " + ".join(ingredients_parts)

                    msg += f"  - {recipe.name} (**{recipe.base_price}**金)\n"
                    msg += f"    {ingredients_text}\n"
                msg += "\n"

        msg += f"***\n{cmd('烹饪 菜名', '烹饪 ')} | {cmd('菜品利润')} | {cmd('食谱图鉴')}"

        await recipes_cmd.finish(build_markdown(msg))


recipe_guide_cmd = on_command("食谱图鉴", aliases={"所有食谱", "全部食谱"}, priority=5, block=True)


@recipe_guide_cmd.handle()
async def handle_recipe_guide(event: MessageEvent):
    """【食谱图鉴】- 查看所有食谱(含未学会)"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await recipe_guide_cmd.finish("⛔ 请先创建角色")

        # 获取玩家已学食谱ID
        learned_ids = set(await uow.player_recipes.get_recipe_ids_by_player(player.id))

        # 获取所有食谱
        all_recipes = recipe_manager.get_all_recipes()

        tier_names = {
            "white": "⚪ 家常菜 (厨房Lv.1)",
            "green": "🟢 特色菜 (厨房Lv.2)",
            "blue": "🔵 招牌菜 (厨房Lv.3)",
            "purple": "🟣 宴席菜 (厨房Lv.4)",
            "orange": "🟠 传说菜 (厨房Lv.5)"
        }

        tier_order = ["white", "green", "blue", "purple", "orange"]

        # 按稀有度分组
        recipes_by_tier = {t: [] for t in tier_order}
        for recipe in all_recipes:
            recipes_by_tier[recipe.tier].append(recipe)

        learned_count = len(learned_ids)
        total_count = len(all_recipes)

        msg = f"# 📖 食谱图鉴 ({learned_count}/{total_count})\n***\n"

        for tier in tier_order:
            tier_recipes = recipes_by_tier[tier]
            if not tier_recipes:
                continue

            tier_learned = sum(1 for r in tier_recipes if r.recipe_id in learned_ids)
            msg += f"**{tier_names[tier]}** ({tier_learned}/{len(tier_recipes)})\n"

            for recipe in tier_recipes:
                learned = recipe.recipe_id in learned_ids
                status = "✅" if learned else "🔒"
                msg += f"  {status} {recipe.name} (**{recipe.base_price}**金)\n"

            msg += "\n"

        msg += "✅ 已学会 | 🔒 未解锁\n"
        msg += f"***\n{cmd('食谱')} | {cmd('烹饪 菜名', '烹饪 ')} | {cmd('菜品利润')}"

        await recipe_guide_cmd.finish(build_markdown(msg))


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

        msg = "# 📋 菜品利润分析\n***\n"

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
                    f"售**{recipe.base_price}** 本**{cost}** "
                    f"利**{profit}**({profit_rate}%) | "
                    f"{customer}\n"
                )

        msg += "\n💡 菜单应覆盖各层客群，避免客人吃不到合适的菜"
        msg += f"\n***\n{cmd('食谱')} | {cmd('烹饪 菜名', '烹饪 ')} | {cmd('食谱图鉴')} | {cmd('查菜单')}"

        await dish_profit_cmd.finish(build_markdown(msg))


# ==================== 餐厅相关指令 ====================

create_restaurant_cmd = on_command("创建餐厅", aliases={"开餐厅"}, priority=5, block=True)


@create_restaurant_cmd.handle()
async def handle_create_restaurant(event: MessageEvent):
    """【创建餐厅】- 创建你的餐厅"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await create_restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.create_restaurant(uow, player.id)
        await create_restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('开店')} | {cmd('经营报表')} | {cmd('我的厨师')}"))


restaurant_cmd = on_command("餐厅", aliases={"我的餐厅", "餐厅状态"}, priority=5, block=True)


@restaurant_cmd.handle()
async def handle_restaurant(event: MessageEvent):
    """【餐厅】- 查看餐厅状态"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg, restaurant = await restaurant_service.get_restaurant_status(uow, player.id)
        await restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('开店')} | {cmd('经营报表')} | {cmd('我的厨师')}"))


upgrade_restaurant_cmd = on_command("餐厅升级", aliases={"升级餐厅"}, priority=5, block=True)


@upgrade_restaurant_cmd.handle()
async def handle_upgrade_restaurant(event: MessageEvent):
    """【餐厅升级】- 升级餐厅等级"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await upgrade_restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.upgrade_restaurant(uow, player.id)
        await upgrade_restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('开店')} | {cmd('经营报表')} | {cmd('我的厨师')}"))


expand_restaurant_cmd = on_command("扩张餐厅", aliases={"餐厅扩张", "扩大面积"}, priority=5, block=True)


@expand_restaurant_cmd.handle()
async def handle_expand_restaurant(event: MessageEvent):
    """【扩张餐厅】- 扩展餐厅面积"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await expand_restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.expand_area(uow, player.id)
        await expand_restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('开店')} | {cmd('经营报表')} | {cmd('我的厨师')}"))


upgrade_kitchen_cmd = on_command("升级厨房", aliases={"厨房升级"}, priority=5, block=True)


@upgrade_kitchen_cmd.handle()
async def handle_upgrade_kitchen(event: MessageEvent):
    """【升级厨房】- 升级厨房等级"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await upgrade_kitchen_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.upgrade_kitchen(uow, player.id)
        await upgrade_kitchen_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('开店')} | {cmd('经营报表')} | {cmd('我的厨师')}"))


open_restaurant_cmd = on_command("开店", aliases={"营业", "开始营业"}, priority=5, block=True)


@open_restaurant_cmd.handle()
async def handle_open_restaurant(event: MessageEvent):
    """【开店】- 开始营业"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await open_restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.toggle_open(uow, player.id, True)
        await open_restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('经营报表')} | {cmd('查菜单')}"))


close_restaurant_cmd = on_command("打烊", aliases={"关店", "停止营业"}, priority=5, block=True)


@close_restaurant_cmd.handle()
async def handle_close_restaurant(event: MessageEvent):
    """【打烊】- 暂停营业"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await close_restaurant_cmd.finish("⛔ 请先创建角色")

        success, msg = await restaurant_service.toggle_open(uow, player.id, False)
        await close_restaurant_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('经营报表')} | {cmd('查菜单')}"))


# ==================== 厨师相关指令 ====================

recruit_chef_cmd = on_command("招募厨师", aliases={"招募", "招厨师"}, priority=5, block=True)


@recruit_chef_cmd.handle()
async def handle_recruit_chef(event: MessageEvent):
    """【招募厨师】- 生成随机厨师候选"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await recruit_chef_cmd.finish("⛔ 请先创建角色")

        # 检查是否有餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await recruit_chef_cmd.finish("⛔ 你还没有餐厅，请先使用【创建餐厅】")

        # 清理过期候选
        expired = await chef_service.clean_expired_candidates(uow, player.id)

        # 检查冷却时间
        can_recruit, cooldown_msg, remaining = await chef_service.check_recruit_cooldown(
            uow, restaurant.id, player.id
        )
        if not can_recruit:
            await recruit_chef_cmd.finish(cooldown_msg)

        # 计算招募费用
        recruit_cost = chef_service.calculate_recruit_cost(restaurant)

        # 检查金币
        if player.gold < recruit_cost:
            await recruit_chef_cmd.finish(
                f"⛔ 招募费不足! 需要 {recruit_cost}金币\n"
                f"💡 提示: 当日招募次数越多,费用越高\n"
                f"   首次500金 → 第2次1000金 → 第3次2000金 → 第4次+5000金"
            )

        # 扣除招募费
        player.gold -= recruit_cost
        await uow.players.update(player)

        # 生成候选
        success, msg, candidates = await chef_service.recruit_chefs(
            uow, player.id, restaurant.id, count=4
        )

        # 显示费用信息
        today_count = restaurant.daily_recruit_count + 1  # 包含本次
        next_cost_info = ""
        if today_count < 3:
            next_cost = chef_service.RECRUIT_COST_SCALING.get(today_count, 5000)
            next_cost_info = f"\n💰 下次招募费用: {next_cost}金币 (当日第{today_count + 1}次)"

        final_msg = (
            f"💰 支付招募费: {recruit_cost}金币 (当日第{today_count}次)"
            f"{next_cost_info}\n\n"
            f"{msg}"
        )

        await recruit_chef_cmd.finish(build_markdown(final_msg + f"\n***\n{cmd('我的厨师')} | {cmd('招募厨师')} | {cmd('餐厅')}"))


hire_chef_cmd = on_command("雇佣", aliases={"雇佣厨师"}, priority=5, block=True)


@hire_chef_cmd.handle()
async def handle_hire_chef(event: MessageEvent, args: Message = CommandArg()):
    """【雇佣 编号】- 雇佣候选厨师"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await hire_chef_cmd.finish("⛔ 用法: 雇佣 <编号>\n例如: 雇佣 1")

    try:
        candidate_index = int(args_text)
    except ValueError:
        await hire_chef_cmd.finish("⛔ 编号必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await hire_chef_cmd.finish("⛔ 请先创建角色")

        # 获取餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await hire_chef_cmd.finish("⛔ 你还没有餐厅")

        success, msg = await chef_service.hire_chef(uow, player.id, candidate_index, restaurant.id)
        await hire_chef_cmd.finish(build_markdown(msg + f"\n***\n{cmd('我的厨师')} | {cmd('招募厨师')} | {cmd('餐厅')}"))


fire_chef_cmd = on_command("解雇", aliases={"解雇厨师", "开除"}, priority=5, block=True)


@fire_chef_cmd.handle()
async def handle_fire_chef(event: MessageEvent, args: Message = CommandArg()):
    """【解雇 厨师名】- 解雇厨师"""

    chef_name = args.extract_plain_text().strip()

    if not chef_name:
        await fire_chef_cmd.finish("⛔ 用法: 解雇 <厨师名>\n例如: 解雇 小福贵")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await fire_chef_cmd.finish("⛔ 请先创建角色")

        # 获取餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await fire_chef_cmd.finish("⛔ 你还没有餐厅")

        success, msg = await chef_service.fire_chef(uow, restaurant.id, chef_name)
        await fire_chef_cmd.finish(build_markdown(msg + f"\n***\n{cmd('我的厨师')} | {cmd('招募厨师')} | {cmd('餐厅')}"))


my_chefs_cmd = on_command("我的厨师", aliases={"厨师", "厨师列表"}, priority=5, block=True)


@my_chefs_cmd.handle()
async def handle_my_chefs(event: MessageEvent):
    """【我的厨师】- 查看已雇佣的厨师"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await my_chefs_cmd.finish("⛔ 请先创建角色")

        # 获取餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await my_chefs_cmd.finish("⛔ 你还没有餐厅")

        chefs = await chef_service.get_restaurant_chefs(uow, restaurant.id)

        if not chefs:
            await my_chefs_cmd.finish("⛔ 还没有雇佣厨师\n使用【招募厨师】开始招募")

        # 生成消息
        msg = f"# 👨‍🍳 我的厨师 ({len(chefs)}/{restaurant.max_chefs})\n***\n"

        tier_names = {
            "apprentice": "学徒厨师",
            "helper": "帮厨",
            "cook": "厨师",
            "head_chef": "大厨",
            "master_chef": "特级厨师"
        }

        category_names = {
            "fish": "鱼鲜",
            "soup": "汤煲",
            "grill": "烤制",
            "steam": "蒸煮",
            "dessert": "甜点"
        }

        for chef in chefs:
            tier_name = tier_names.get(chef.tier, chef.tier)
            specialty_name = category_names.get(chef.specialty, chef.specialty)

            msg += f"**{chef.name}** ({tier_name})\n"
            msg += f"  厨艺: **{chef.skill}** | 速度: **{chef.speed}**道/时\n"
            msg += f"  擅长: {specialty_name} | 时薪: **{chef.salary}**金\n"

            # 显示经验进度
            from ..models.chef import ChefTier
            current_tier = ChefTier(chef.tier)
            required_exp = chef_service.PROMOTION_EXP.get(current_tier)
            if required_exp:
                exp = getattr(chef, 'experience', 0) or 0
                progress = min(100, int(exp / required_exp * 100))
                bar_filled = progress // 10
                bar_empty = 10 - bar_filled
                bar = "█" * bar_filled + "░" * bar_empty
                msg += f"  经验: **{exp}**/{required_exp} [{bar}] {progress}%\n"
            else:
                msg += f"  经验: MAX (已满级)\n"

            msg += "\n"

        msg += f"***\n{cmd('我的厨师')} | {cmd('招募厨师')} | {cmd('餐厅')}"

        await my_chefs_cmd.finish(build_markdown(msg))


promote_chef_cmd = on_command("培训厨师", aliases={"厨师培训", "升级厨师"}, priority=5, block=True)


@promote_chef_cmd.handle()
async def handle_promote_chef(event: MessageEvent, args: Message = CommandArg()):
    """【培训厨师 厨师名】- 培训厨师升级"""

    chef_name = args.extract_plain_text().strip()

    if not chef_name:
        await promote_chef_cmd.finish(
            "⛔ 用法: 培训厨师 <厨师名>\n"
            "例如: 培训厨师 小福贵\n"
            "💡 厨师需要积累足够经验才能培训升级"
        )

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await promote_chef_cmd.finish("⛔ 请先创建角色")

        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await promote_chef_cmd.finish("⛔ 你还没有餐厅")

        success, msg = await chef_service.promote_chef(
            uow, player.id, restaurant.id, chef_name
        )
        await promote_chef_cmd.finish(build_markdown(msg + f"\n***\n{cmd('我的厨师')} | {cmd('招募厨师')} | {cmd('餐厅')}"))


# ==================== 经营报表 ====================

report_cmd = on_command("经营报表", aliases={"报表", "餐厅报表"}, priority=5, block=True)


@report_cmd.handle()
async def handle_report(event: MessageEvent):
    """【经营报表】- 查看经营统计"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await report_cmd.finish("⛔ 请先创建角色")

        # 获取餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await report_cmd.finish("⛔ 你还没有餐厅")

        msg = await settlement_service.get_settlement_report(uow, restaurant.id, hours=24)
        await report_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅')} | {cmd('经营日志')} | {cmd('菜品利润')}"))


log_cmd = on_command("经营日志", aliases={"日志", "餐厅日志"}, priority=5, block=True)


@log_cmd.handle()
async def handle_log(event: MessageEvent):
    """【经营日志】- 查看最近一次的详细经营日志"""
    import json

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await log_cmd.finish("⛔ 请先创建角色")

        # 获取餐厅
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await log_cmd.finish("⛔ 你还没有餐厅")

        # 获取最近一次的日志
        logs = await uow.restaurant_logs.get_by_restaurant_id(restaurant.id, limit=1)
        if not logs:
            await log_cmd.finish("⛔ 还没有经营日志")

        log = logs[0]
        details = json.loads(log.details_json)

        msg_lines = [
            "# 📜 餐厅经营日志",
            "***",
            f"⏰ 时段: {log.period_start.strftime('%m-%d %H:%M')}",
            f"💰 收入: **{log.income}**金 | 支出: **{log.expense}**金",
            f"📈 净利润: **{log.income - log.expense}**金",
            f"👥 顾客数: **{log.customers}**人",
            f"🍽️ 制作菜品: **{log.dishes_made}**道 | 失败: **{log.dishes_failed}**道",
            f"⭐ 声望变化: **{log.reputation_change:+d}**",
            "",
            "**👨‍🍳 厨师工作详情:**",
            "***"
        ]

        # 展示每个厨师的详细情况
        chef_details = details.get("chef_details", [])
        for chef_detail in chef_details:
            chef_name = chef_detail.get("chef_name", "未知厨师")
            dishes = chef_detail.get("dishes", [])
            failed = chef_detail.get("failed", 0)
            comments = chef_detail.get("personality_comments", [])

            msg_lines.append(f"\n👨‍🍳 {chef_name}:")
            msg_lines.append(f"  制作: {len(dishes)}道 | 失败: {failed}道")

            # 展示性格旁白(随机选择2-3条)
            if comments:
                sample_count = min(3, len(comments))
                import random
                sampled_comments = random.sample(comments, sample_count)
                msg_lines.append("  💬 性格片段:")
                for comment in sampled_comments:
                    msg_lines.append(f"    「{comment}」")

        # 展示随机事件
        event_data = details.get("event")
        if event_data and event_data.get("name"):
            msg_lines.append("")
            msg_lines.append("***")
            event_type_icon = "🎉" if event_data.get("income_bonus", 0) >= 0 and event_data.get("reputation_bonus", 0) >= 0 else "⚠️"
            msg_lines.append(f"{event_type_icon} 经营事件: **{event_data['name']}**")
            msg_lines.append(f"  {event_data.get('description', '')}")
            if event_data.get("income_bonus", 0) != 0:
                sign = "+" if event_data["income_bonus"] > 0 else ""
                msg_lines.append(f"  💰 收入影响: **{sign}{event_data['income_bonus']}**金")
            if event_data.get("expense_bonus", 0) != 0:
                sign = "+" if event_data["expense_bonus"] > 0 else ""
                msg_lines.append(f"  💸 支出影响: **{sign}{event_data['expense_bonus']}**金")
            if event_data.get("reputation_bonus", 0) != 0:
                sign = "+" if event_data["reputation_bonus"] > 0 else ""
                msg_lines.append(f"  ⭐ 声望影响: **{sign}{event_data['reputation_bonus']}**")

        msg_lines.append("")
        msg_lines.append("***")
        msg_lines.append(f"{cmd('餐厅')} | {cmd('经营日志')} | {cmd('菜品利润')}")

        await log_cmd.finish(build_markdown("\n".join(msg_lines)))


# ==================== 仓库管理 ====================

restock_cmd = on_command("补货", aliases={"餐厅补货", "转移食材"}, priority=5, block=True)


@restock_cmd.handle()
async def handle_restock(event: MessageEvent, args: Message = CommandArg()):
    """【补货 食材名 数量】- 从背包转移食材到餐厅仓库"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await restock_cmd.finish("⛔ 用法: 补货 <食材名> <数量>\n例如: 补货 鲤鱼 10")

    # 解析参数
    parts = args_text.split()
    if len(parts) < 2:
        await restock_cmd.finish("⛔ 用法: 补货 <食材名> <数量>\n例如: 补货 鲤鱼 10")

    item_name = parts[0]
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            await restock_cmd.finish("⛔ 数量必须大于0")
    except ValueError:
        await restock_cmd.finish("⛔ 数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await restock_cmd.finish("⛔ 请先创建角色")

        # 根据物品名查找物品ID
        from ..config import config
        item_id = None
        for iid, item_cfg in config.items_config["by_id"].items():
            if item_cfg.name == item_name:
                item_id = iid
                break

        if not item_id:
            await restock_cmd.finish(f"⛔ 未找到食材: {item_name}")

        success, msg = await restaurant_service.restock_ingredient(uow, player.id, item_id, quantity)
        await restock_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅仓库')} | {cmd('补货 菜名 数量', '补货 ')} | {cmd('餐厅')}"))


withdraw_cmd = on_command("取货", aliases={"餐厅取货", "取出食材"}, priority=5, block=True)


@withdraw_cmd.handle()
async def handle_withdraw(event: MessageEvent, args: Message = CommandArg()):
    """【取货 食材名 数量】- 从餐厅仓库取出食材到背包"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await withdraw_cmd.finish("⛔ 用法: 取货 <食材名> <数量>\n例如: 取货 鲤鱼 10")

    # 解析参数
    parts = args_text.split()
    if len(parts) < 2:
        await withdraw_cmd.finish("⛔ 用法: 取货 <食材名> <数量>\n例如: 取货 鲤鱼 10")

    item_name = parts[0]
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            await withdraw_cmd.finish("⛔ 数量必须大于0")
    except ValueError:
        await withdraw_cmd.finish("⛔ 数量必须是数字")

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await withdraw_cmd.finish("⛔ 请先创建角色")

        # 根据物品名查找物品ID
        from ..config import config
        item_id = None
        for iid, item_cfg in config.items_config["by_id"].items():
            if item_cfg.name == item_name:
                item_id = iid
                break

        if not item_id:
            await withdraw_cmd.finish(f"⛔ 未找到食材: {item_name}")

        success, msg = await restaurant_service.withdraw_ingredient(uow, player.id, item_id, quantity)
        await withdraw_cmd.finish(build_markdown(msg + f"\n***\n{cmd('餐厅仓库')} | {cmd('补货 菜名 数量', '补货 ')} | {cmd('餐厅')}"))


storage_cmd = on_command("餐厅仓库", aliases={"仓库", "查看仓库"}, priority=5, block=True)


@storage_cmd.handle()
async def handle_storage(event: MessageEvent):
    """【餐厅仓库】- 查看餐厅仓库中的食材"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await storage_cmd.finish("⛔ 请先创建角色")

        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await storage_cmd.finish("⛔ 你还没有餐厅")

        # 获取仓库中的所有食材
        storage_items = await uow.restaurant_storage.get_by_restaurant(restaurant.id)

        if not storage_items:
            empty_msg = (
                f"# 📦 餐厅仓库 (0/{restaurant.storage_capacity})\n***\n"
                f"⚠️ 仓库空空如也\n"
                f"\n***\n{cmd('补货 菜名 数量', '补货 ')} | {cmd('餐厅')}"
            )
            await storage_cmd.finish(build_markdown(empty_msg))

        # 计算总量
        total_quantity = sum(item.quantity for item in storage_items)

        # 分类展示食材
        from ..config import config
        fish_items = []
        seasoning_items = []
        other_items = []

        for storage in storage_items:
            item_cfg = config.items_config["by_id"].get(storage.item_id)
            if item_cfg:
                item_info = f"  {item_cfg.name} × {storage.quantity}"
                if item_cfg.type.value == "FISH":
                    fish_items.append(item_info)
                elif item_cfg.type.value == "SEASONING":
                    seasoning_items.append(item_info)
                else:
                    other_items.append(item_info)

        msg = f"# 📦 餐厅仓库 ({total_quantity}/{restaurant.storage_capacity})\n***\n"

        if fish_items:
            msg += "**🐟 鱼类食材:**\n" + "\n".join(fish_items) + "\n\n"

        if seasoning_items:
            msg += "**🧂 调料:**\n" + "\n".join(seasoning_items) + "\n\n"

        if other_items:
            msg += "**📦 其他:**\n" + "\n".join(other_items) + "\n\n"

        msg += f"***\n{cmd('补货 菜名 数量', '补货 ')} | {cmd('餐厅仓库')} | {cmd('餐厅')}"

        await storage_cmd.finish(build_markdown(msg))


# ==================== 菜单管理 ====================

set_menu_cmd = on_command("设置菜单", aliases={"菜单设置", "更新菜单"}, priority=5, block=True)


@set_menu_cmd.handle()
async def handle_set_menu(event: MessageEvent, args: Message = CommandArg()):
    """【设置菜单 菜名1 菜名2 ...】- 设置餐厅营业菜单"""

    args_text = args.extract_plain_text().strip()

    if not args_text:
        await set_menu_cmd.finish(
            "⛔ 用法: 设置菜单 <菜名1> [菜名2] [菜名3] ...\n"
            "例如: 设置菜单 红烧鲤鱼 清蒸鲫鱼\n"
            "💡 使用【食谱】查看已学会的菜谱"
        )

    # 解析菜名
    dish_names = args_text.split()

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await set_menu_cmd.finish("⛔ 请先创建角色")

        # 根据菜名查找食谱ID
        from ..config import config
        recipe_ids = []
        for dish_name in dish_names:
            found = False
            for recipe_id, recipe in recipe_manager._recipes.items():
                if recipe.name == dish_name:
                    recipe_ids.append(recipe_id)
                    found = True
                    break
            if not found:
                await set_menu_cmd.finish(f"⛔ 未找到菜谱: {dish_name}")

        success, msg = await restaurant_service.set_menu(uow, player.id, recipe_ids)
        await set_menu_cmd.finish(build_markdown(msg + f"\n***\n{cmd('查菜单')} | {cmd('设置菜单 菜名', '设置菜单 ')} | {cmd('平衡菜单')} | {cmd('餐厅')}"))


view_menu_cmd = on_command("菜单", aliases={"查看菜单", "营业菜单"}, priority=5, block=True)


@view_menu_cmd.handle()
async def handle_view_menu(event: MessageEvent):
    """【菜单】- 查看当前营业菜单"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await view_menu_cmd.finish("⛔ 请先创建角色")

        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await view_menu_cmd.finish("⛔ 你还没有餐厅")

        # 获取菜单
        menu_items = await uow.restaurant_menus.get_active_menu(restaurant.id)

        if not menu_items:
            empty_menu_msg = (
                "# 📋 营业菜单\n***\n"
                "⚠️ 还未设置菜单\n"
                f"\n***\n{cmd('设置菜单 菜名', '设置菜单 ')} | {cmd('食谱')} | {cmd('餐厅')}"
            )
            await view_menu_cmd.finish(build_markdown(empty_menu_msg))

        msg = "# 📋 营业菜单\n***\n"

        from ..config import config

        for menu in menu_items:
            recipe = recipe_manager.get_recipe(menu.recipe_id)
            if recipe:
                # 显示食谱信息和所需食材
                ingredients_parts = []
                for item_id, qty in recipe.ingredients.items():
                    item_cfg = config.items_config["by_id"].get(item_id)
                    item_name = item_cfg.name if item_cfg else item_id
                    ingredients_parts.append(f"{item_name}×{qty}")
                ingredients_str = ", ".join(ingredients_parts)

                rarity_emoji = {
                    "white": "⚪",
                    "green": "🟢",
                    "blue": "🔵",
                    "purple": "🟣",
                    "orange": "🟠"
                }

                is_signature = getattr(restaurant, 'signature_recipe_id', None) == recipe.recipe_id
                sig_tag = " ⭐招牌" if is_signature else ""

                msg += (
                    f"{rarity_emoji.get(recipe.tier, '⚪')} **{recipe.name}**{sig_tag}\n"
                    f"  售价: **{recipe.base_price}**金{' (+30%)' if is_signature else ''}\n"
                    f"  食材: {ingredients_str}\n\n"
                )

        msg += f"***\n{cmd('查菜单')} | {cmd('设置菜单 菜名', '设置菜单 ')} | {cmd('平衡菜单')} | {cmd('餐厅')}"

        await view_menu_cmd.finish(build_markdown(msg))


# ==================== 仓库升级 ====================

upgrade_storage_cmd = on_command("升级仓库", aliases={"扩建仓库", "仓库升级"}, priority=5, block=True)


@upgrade_storage_cmd.handle()
async def handle_upgrade_storage(event: MessageEvent):
    """【升级仓库】- 升级仓库等级(Lv.1-5)"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await upgrade_storage_cmd.finish("⛔ 请先创建角色")

        # 先显示当前仓库信息和下级配置
        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await upgrade_storage_cmd.finish("⛔ 你还没有餐厅，请先创建")

        if restaurant.storage_level >= 5:
            await upgrade_storage_cmd.finish(
                f"⛔ 仓库已达最高等级(Lv.5，容量500)\n"
                f"📦 当前仓库: Lv.5 | 容量500"
            )

        # 显示升级信息供参考
        config = restaurant_service.STORAGE_UPGRADE_CONFIG
        next_level = restaurant.storage_level + 1
        new_capacity, req_restaurant_level, cost = config[next_level]

        info = (
            f"# 📦 仓库升级\n***\n"
            f"当前: Lv.**{restaurant.storage_level}** | 容量**{restaurant.storage_capacity}**\n"
            f"升级: Lv.**{next_level}** | 容量**{new_capacity}**\n"
            f"需要: 餐厅Lv.**{req_restaurant_level}** | **{cost}**金币\n"
            f"***\n"
        )

        success, msg = await restaurant_service.upgrade_storage(uow, player.id)
        await upgrade_storage_cmd.finish(build_markdown(info + msg + f"\n***\n{cmd('餐厅仓库')} | {cmd('补货 菜名 数量', '补货 ')} | {cmd('餐厅')}"))


# ==================== 招牌菜 ====================

signature_dish_cmd = on_command("设置招牌菜", aliases={"招牌菜设置"}, priority=5, block=True)


@signature_dish_cmd.handle()
async def handle_signature_dish(event: MessageEvent, args: Message = CommandArg()):
    """【设置招牌菜 菜名】- 设置餐厅招牌菜(售价+30%)"""

    dish_name = args.extract_plain_text().strip()

    if not dish_name:
        await signature_dish_cmd.finish(
            "⛔ 用法: 设置招牌菜 <菜名>\n"
            "例如: 设置招牌菜 红烧鲤鱼\n"
            "💡 招牌菜在营业时售价+30%，需为菜单中的菜品"
        )

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await signature_dish_cmd.finish("⛔ 请先创建角色")

        restaurant = await uow.restaurants.get_by_player_id(player.id)
        if not restaurant:
            await signature_dish_cmd.finish("⛔ 你还没有餐厅")

        # 查找食谱
        recipe = recipe_manager.get_recipe_by_name(dish_name)
        if not recipe:
            await signature_dish_cmd.finish(f"⛔ 未找到菜肴【{dish_name}】")

        # 检查是否在菜单中
        menu_items = await uow.restaurant_menus.get_active_menu(restaurant.id)
        menu_recipe_ids = [m.recipe_id for m in menu_items] if menu_items else []

        if recipe.recipe_id not in menu_recipe_ids:
            await signature_dish_cmd.finish(
                f"⛔ 【{dish_name}】不在当前菜单中\n"
                f"请先使用【设置菜单】将它加入菜单"
            )

        # 设置招牌菜
        restaurant.signature_recipe_id = recipe.recipe_id
        await uow.restaurants.update(restaurant)
        await uow.commit()

        await signature_dish_cmd.finish(
            f"⭐ 成功设置招牌菜: 【{dish_name}】\n"
            f"营业时该菜品售价+30%!"
        )


# ==================== 餐厅排行榜 ====================

restaurant_rank_cmd = on_command("餐厅排行", aliases={"餐厅排行榜", "餐厅榜"}, priority=5, block=True)


@restaurant_rank_cmd.handle()
async def handle_restaurant_rank(event: MessageEvent):
    """【餐厅排行】- 查看餐厅排行榜"""

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await restaurant_rank_cmd.finish("⛔ 请先创建角色")

        # 获取排行数据
        msg = await restaurant_service.get_restaurant_ranking(uow, player.id)
        await restaurant_rank_cmd.finish(msg)
