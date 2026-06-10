"""
公会设施命令（公会传送/丹房兑换/公会仓库）

从 guild.py 逐字拆分搬移，零行为变化。
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, func as _func

from ..models.db import safe_session
from ..models.guild import Guild, GuildWarehouseItem
from ..config import config
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from .guild_facility_service import GuildFacilityService
from .guild_daily_tasks import GuildDailyTasks
from ..platform_utils import get_unified_player

# ==================== 公会传送阵 ====================
guild_teleport_cmd = on_command("公会传送", aliases={"传送到公会"}, block=True, priority=11)

@guild_teleport_cmd.handle()
async def handle_guild_teleport(event: MessageEvent, args: Message = CommandArg()):
    """使用传送阵传送到公会基地或势力范围内的指定坐标"""
    args_text = args.extract_plain_text().strip()

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_teleport_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在现实世界
        if player.region != "大都会":
            await guild_teleport_cmd.finish("⛔ 只能在现实世界使用传送阵")

        guild = await session.get(Guild, player.guild_id)
        if not guild:
            await guild_teleport_cmd.finish("⛔ 公会数据异常")

        # 如果没有参数，传送到公会基地
        if not args_text:
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
            from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
            from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

            facility_service = GuildFacilityService(
                guild_repo=GuildRepository(session),
                building_repo=GuildBuildingRepository(session),
                player_repo=PlayerRepository(session),
                item_repo=ItemRepository(session),
                teleport_log_repo=GuildTeleportLogRepository(session),
                alchemy_production_repo=GuildAlchemyProductionRepository(session),
                warehouse_item_repo=GuildWarehouseItemRepository(session),
            )
            success, message = await facility_service.teleport_to_guild(player.id, player.guild_id)
            if success:
                await session.commit()
                await guild_teleport_cmd.finish(message_add_head(f"✨ {message}", event))
            else:
                await guild_teleport_cmd.finish(message_add_head(f"⛔ {message}", event))

        # 如果有参数，解析坐标并传送到势力范围内
        else:
            # 检查是否在公会基地
            current_x, current_y = player.get_current_coordinates()
            if guild.base_x is None or guild.base_y is None:
                await guild_teleport_cmd.finish("⛔ 公会尚未设置基地")

            if current_x != guild.base_x or current_y != guild.base_y:
                await guild_teleport_cmd.finish("⛔ 只有在公会基地才能传送到势力范围内的坐标")

            # 解析坐标参数
            coords = args_text.split()
            if len(coords) != 2:
                await guild_teleport_cmd.finish("⛔ 格式错误，正确格式：公会传送 x y")

            try:
                target_x = int(coords[0])
                target_y = int(coords[1])
            except ValueError:
                await guild_teleport_cmd.finish("⛔ 坐标必须是数字")

            # 检查目标坐标是否在势力范围内
            base_x, base_y = guild.base_x, guild.base_y
            territory_range = guild.territory_range

            # 势力范围是以基地为中心的正方形区域
            half_range = territory_range // 2
            min_x = base_x - half_range
            max_x = base_x + half_range
            min_y = base_y - half_range
            max_y = base_y + half_range

            if not (min_x <= target_x <= max_x and min_y <= target_y <= max_y):
                await guild_teleport_cmd.finish(
                    f"⛔ 目标坐标({target_x}, {target_y})超出公会势力范围\n"
                    f"势力范围：X({min_x}~{max_x}) Y({min_y}~{max_y})"
                )

            # 执行传送（不消耗传送次数）
            player.real_world_x = target_x
            player.real_world_y = target_y
            player.x = target_x
            player.y = target_y
            session.add(player)
            await session.commit()

            await guild_teleport_cmd.finish(message_add_head(
                f"✨ 传送成功！从公会基地({base_x}, {base_y})传送到({target_x}, {target_y})", event
            ))

# ==================== 公会丹房 ====================
guild_alchemy_cmd = on_command("公会丹房", aliases={"丹房", "丹药兑换"}, block=True, priority=11)

@guild_alchemy_cmd.handle()
async def handle_guild_alchemy(event: MessageEvent):
    """查看公会丹房产出"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_alchemy_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        # 触发丹房产出检查和生成
        refresh_result = await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        productions = await facility_service.get_alchemy_production_grouped(player.guild_id)
        # 提交丹房产出的更改
        await session.commit()

        lines = [
            f"# 🧪 {guild.name}·丹房",
            f"💰 你的积分：**{player.gold2}**",
        ]

        # 如果有新产出或存储已满，显示提示
        if refresh_result["alchemy_generated"] > 0:
            lines.append(f"✨ {refresh_result['message']}")
        elif refresh_result["alchemy_generated"] == -1:
            lines.append(f"{refresh_result['message']}")

        lines.append("***")

        if not productions:
            lines.append("暂无可兑换的丹药")
        else:
            for idx, prod in enumerate(productions, 1):
                pname = prod['item_name']
                lines.append(
                    f"💊 **{pname}**×{prod['total_quantity']}　"
                    f"💎{prod['points_cost']}积分/个　"
                    f"{cmd('🔄兑换', f'兑换丹药 {pname} 1')}"
                )

        lines.append("***")
        lines.append(cmd("公会") + " | " + cmd("公会丹房") + " | " + cmd("帮助"))

        await guild_alchemy_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 兑换丹药 ====================
exchange_pill_cmd = on_command("兑换丹药", block=True, priority=11)

@exchange_pill_cmd.handle()
async def handle_exchange_pill(event: MessageEvent, args: Message = CommandArg()):
    """兑换丹房产出的丹药"""
    params = args.extract_plain_text().strip().split()
    if not params:
        await exchange_pill_cmd.finish("⛔ 格式错误，正确格式：兑换丹药 [丹药名称] [数量]")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await exchange_pill_cmd.finish("⛔ 你未加入任何公会")

        # 触发丹房产出检查和生成
        await GuildDailyTasks.trigger_guild_daily_refresh(session, player.guild_id)

        # 创建facility_service实例（新旧两个版本都可能需要）
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )

        # 模式1：纯数字序号 "兑换丹药 1"
        if len(params) == 1 and params[0].isdigit():
            try:
                index = int(params[0])

                productions = await facility_service.get_alchemy_production(player.guild_id)

                if not productions or index < 1 or index > len(productions):
                    await exchange_pill_cmd.finish("⛔ 无效的序号")

                selected_prod = productions[index - 1]

                # 计算积分成本
                item_config = config.items_config["by_id"].get(selected_prod["item_id"])
                if not item_config:
                    await exchange_pill_cmd.finish("⛔ 物品配置错误")

                points_cost = max(1, item_config.price // 100)

                success, message = await facility_service.claim_alchemy_item(
                    player.id, player.guild_id, selected_prod["id"], points_cost
                )
            except ValueError:
                await exchange_pill_cmd.finish("⛔ 序号必须是数字")
            if success:
                await session.commit()
                await exchange_pill_cmd.finish(message_add_head(f"✅ {message}", event))
            else:
                await exchange_pill_cmd.finish(message_add_head(f"⛔ {message}", event))

        # 模式2：名称+数量 "兑换丹药 仿制还魂丹 5"
        elif len(params) >= 2:
            try:
                quantity = int(params[-1])  # 最后一个参数是数量
                item_name = " ".join(params[:-1])  # 前面的都是名称

                success, message = await facility_service.claim_alchemy_item_by_name(
                    player.id, player.guild_id, item_name, quantity
                )

                if success:
                    await session.commit()
                    await exchange_pill_cmd.finish(message_add_head(f"✅ {message}", event))
                else:
                    await exchange_pill_cmd.finish(message_add_head(f"⛔ {message}", event))
            except ValueError:
                await exchange_pill_cmd.finish("⛔ 数量必须是数字")

        # 模式3：参数格式不符合两种模式
        else:
            await exchange_pill_cmd.finish("⛔ 格式错误，支持两种方式：\n"
                "方式1：兑换丹药 [序号]\n"
                "方式2：兑换丹药 [丹药名称] [数量]")

# ==================== 公会仓库 ====================
guild_warehouse_cmd = on_command("公会仓库", aliases={"仓库"}, block=True, priority=11)

@guild_warehouse_cmd.handle()
async def handle_guild_warehouse(event: MessageEvent):
    """查看公会仓库"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await guild_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await guild_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await guild_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
        )
        capacity = await facility_service.get_warehouse_capacity(player.guild_id)
        if capacity == 0:
            await guild_warehouse_cmd.finish("⛔ 公会尚未建造仓库")
        items = await facility_service.get_warehouse_items(player.guild_id)
        # 获取实际占用的格子数（数据库中的记录数，每个记录代表一个堆叠）
        stmt = select(_func.count(GuildWarehouseItem.id)).where(GuildWarehouseItem.guild_id == player.guild_id)
        current_slots_used = (await session.execute(stmt)).scalar_one() or 0

        lines = [
            f"# 📦 {guild.name}·仓库",
            f"格子：**{current_slots_used}**/{capacity}",
            "***",
        ]

        if not items:
            lines.append("暂无物品")
        else:
            for idx, item in enumerate(items, 1):
                iname = item['item_name']
                lines.append(
                    f"📦 **{iname}**×{item['quantity']}　"
                    f"👤存入者:{item['deposited_by']}　"
                    f"{cmd('⬆️取出', f'取出仓库 {iname} 1')}"
                )

        lines.append("***")
        lines.append(cmd("仓库记录") + " | " + cmd("公会") + " | " + cmd("帮助"))

        await guild_warehouse_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 存入仓库 ====================
deposit_warehouse_cmd = on_command("存入仓库", block=True, priority=11)

@deposit_warehouse_cmd.handle()
async def handle_deposit_warehouse(event: MessageEvent, args: Message = CommandArg()):
    """存入物品到公会仓库"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await deposit_warehouse_cmd.finish("⛔ 格式错误，正确格式：存入仓库 [物品名] [数量]")

    parts = args_text.split()
    if len(parts) < 2:
        await deposit_warehouse_cmd.finish("⛔ 格式错误，正确格式：存入仓库 [物品名] [数量]")

    item_name = parts[0]
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await deposit_warehouse_cmd.finish("⛔ 数量必须是正整数")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await deposit_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await deposit_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await deposit_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        # 查找物品ID
        item_config = config.items_config["by_name"].get(item_name)
        if not item_config:
            await deposit_warehouse_cmd.finish("⛔ 未找到该物品")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )
        success, message = await facility_service.deposit_to_warehouse(
            player.id, player.guild_id, item_config.item_id, quantity
        )
        if success:
            await session.commit()
            await deposit_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await deposit_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 取出仓库 ====================
withdraw_warehouse_cmd = on_command("取出仓库", block=True, priority=11)

@withdraw_warehouse_cmd.handle()
async def handle_withdraw_warehouse(event: MessageEvent, args: Message = CommandArg()):
    """从公会仓库取出物品，支持物品名或序号"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [物品名] [数量] 或 取出仓库 [序号] [数量]")

    parts = args_text.rsplit(maxsplit=1)
    if len(parts) < 2:
        await withdraw_warehouse_cmd.finish("⛔ 格式错误，正确格式：取出仓库 [物品名] [数量] 或 取出仓库 [序号] [数量]")

    # 解析数量（最后一个参数）
    try:
        quantity = int(parts[1])
        if quantity <= 0:
            raise ValueError
    except ValueError:
        await withdraw_warehouse_cmd.finish("⛔ 数量必须是正整数")

    # 判断第一个参数是序号还是物品名
    item_name = None
    index = None
    try:
        index = int(parts[0])
        if index <= 0:
            raise ValueError
    except ValueError:
        # 不是数字，当作物品名处理
        item_name = parts[0]

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await withdraw_warehouse_cmd.finish("⛔ 你未加入任何公会")

        # 检查是否在公会基地
        guild = await session.get(Guild, player.guild_id)
        if guild.base_x is None or guild.base_y is None:
            await withdraw_warehouse_cmd.finish("⛔ 公会尚未设置基地")

        if player.x != guild.base_x or player.y != guild.base_y:
            await withdraw_warehouse_cmd.finish("⛔ 只有在公会基地才能访问仓库")

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )

        if item_name:
            # 按物品名取出
            success, message = await facility_service.withdraw_from_warehouse_by_name(
                player.id, player.guild_id, item_name, quantity
            )
        else:
            # 按序号取出
            success, message = await facility_service.withdraw_from_warehouse(
                player.id, player.guild_id, index, quantity
            )
        if success:
            await session.commit()
            await withdraw_warehouse_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await withdraw_warehouse_cmd.finish(message_add_head(f"⛔ {message}", event))

# ==================== 仓库记录 ====================
warehouse_log_cmd = on_command("仓库记录", block=True, priority=11)

@warehouse_log_cmd.handle()
async def handle_warehouse_log(event: MessageEvent, args: Message = CommandArg()):
    """查看公会仓库的存取操作记录"""
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or not player.guild_id:
            await warehouse_log_cmd.finish("⛔ 你未加入任何公会")

        guild = await session.get(Guild, player.guild_id)

        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.item_repository import ItemRepository
        from ..infrastructure.repositories.guild_teleport_log_repository import GuildTeleportLogRepository
        from ..infrastructure.repositories.guild_alchemy_production_repository import GuildAlchemyProductionRepository
        from ..infrastructure.repositories.guild_warehouse_item_repository import GuildWarehouseItemRepository
        from ..infrastructure.repositories.guild_warehouse_log_repository import GuildWarehouseLogRepository

        facility_service = GuildFacilityService(
            guild_repo=GuildRepository(session),
            building_repo=GuildBuildingRepository(session),
            player_repo=PlayerRepository(session),
            item_repo=ItemRepository(session),
            teleport_log_repo=GuildTeleportLogRepository(session),
            alchemy_production_repo=GuildAlchemyProductionRepository(session),
            warehouse_item_repo=GuildWarehouseItemRepository(session),
            warehouse_log_repo=GuildWarehouseLogRepository(session),
        )

        logs = await facility_service.get_warehouse_logs(player.guild_id, limit=20)

        if not logs:
            await warehouse_log_cmd.finish(message_add_head(
                f"📋 公会『{guild.name}』仓库记录\n━━━━━━━━━━\n暂无操作记录", event
            ))

        lines = [f"📋 公会『{guild.name}』仓库记录", "━━━━━━━━━━"]
        for log in logs:
            time_str = log["operated_at"].strftime("%m-%d %H:%M")
            op_icon = "📥" if log["operation"] == "存入" else "📤"
            lines.append(
                f"{op_icon} {time_str} {log['player_name']} "
                f"{log['operation']} {log['item_name']}×{log['quantity']}"
            )
        lines.append("━━━━━━━━━━")
        lines.append("💡 显示最近20条记录")

        await warehouse_log_cmd.finish(message_add_head("\n".join(lines), event))
