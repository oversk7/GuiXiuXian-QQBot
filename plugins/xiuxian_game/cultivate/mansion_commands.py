"""
阴宅系统命令处理器
处理阴宅相关的游戏指令
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from ..utils import message_add_head
from ..models.db import safe_session
from ..models.player import Player
from .mansion import MansionService


# 阴宅相关命令
mansion_status_cmd = on_command("阴宅", aliases={"阴宅状态", "查看阴宅"}, priority=4, block=True)
purchase_mansion_cmd = on_command("购买阴宅", aliases={"买阴宅"}, priority=4, block=True)
upgrade_mansion_cmd = on_command("升级阴宅", aliases={"阴宅升级"}, priority=4, block=True)
set_mansion_fee_cmd = on_command("设置阴宅费用", aliases={"阴宅费用"}, priority=4, block=True)
toggle_mansion_access_cmd = on_command("切换阴宅权限", aliases={"阴宅权限"}, priority=4, block=True)
toggle_mansion_payment_cmd = on_command("切换阴宅付费意愿", aliases={"阴宅付费意愿", "阴宅付费"}, priority=4, block=True)
migrate_mansion_cmd = on_command("迁移阴宅", aliases={"阴宅迁移"}, priority=4, block=True)


@mansion_status_cmd.handle()
async def handle_mansion_status(event: MessageEvent):
    """查看阴宅状态"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await mansion_status_cmd.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 格式化阴宅状态信息
        status_msg = MansionService.format_mansion_status(player)
        
        await mansion_status_cmd.finish(message_add_head(status_msg, event))


@purchase_mansion_cmd.handle()
async def handle_purchase_mansion(event: MessageEvent):
    """购买阴宅"""
    from ..platform_utils import get_unified_player, is_guild_message

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await purchase_mansion_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await purchase_mansion_cmd.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 尝试购买阴宅
        success, result_msg = await MansionService.purchase_mansion(session, player)
        
        if success:
            # 保存数据
            session.add(player)
            await session.commit()
            
            await purchase_mansion_cmd.finish(message_add_head(result_msg, event))
        else:
            await purchase_mansion_cmd.finish(message_add_head(f"⛔ {result_msg}", event))


@upgrade_mansion_cmd.handle()
async def handle_upgrade_mansion(event: MessageEvent):
    """升级阴宅"""
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await upgrade_mansion_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await upgrade_mansion_cmd.finish("⛔ 请先使用【注册】命令创建角色")
        
        # 检查是否拥有阴宅
        if player.mansion_level <= 0:
            await upgrade_mansion_cmd.finish(message_add_head(
                "⛔ 你还没有阴宅，请先使用【购买阴宅】命令",
                event
            ))
        
        # 尝试升级阴宅
        success, result_msg = await MansionService.upgrade_mansion(session, player)
        
        if success:
            # 保存数据
            session.add(player)
            await session.commit()
            
            await upgrade_mansion_cmd.finish(message_add_head(result_msg, event))
        else:
            await upgrade_mansion_cmd.finish(message_add_head(f"⛔ {result_msg}", event))


@set_mansion_fee_cmd.handle()
async def handle_set_mansion_fee(event: MessageEvent, args: Message = CommandArg()):
    """设置阴宅使用费用"""
    user_id = event.get_user_id()

    # 解析参数
    arg_text = args.extract_plain_text().strip()
    if not arg_text:
        # 获取玩家数据以显示当前阴宅等级的最低费用要求
        async with safe_session() as temp_session:
            temp_player = await temp_session.get(Player, user_id)
            if temp_player and temp_player.mansion_level > 0:
                min_fee = MansionService.get_min_usage_fee(temp_player.mansion_level)
                fee_range_text = f"{min_fee:,}-{MansionService.MAX_USAGE_FEE:,}金币"
                level_text = f"（{temp_player.mansion_level}级阴宅）"
            else:
                fee_range_text = f"{MansionService.BASE_MIN_USAGE_FEE:,}-{MansionService.MAX_USAGE_FEE:,}金币"
                level_text = ""

        await set_mansion_fee_cmd.finish(message_add_head(
            "⛔ 请输入费用金额\n"
            "━━━━━━━━━━━━━\n"
            "用法：【设置阴宅费用 <金币数>】\n"
            "例如：【设置阴宅费用 5000】\n"
            f"费用范围：{fee_range_text}{level_text}\n"
            "💡 阴宅等级越高，最低费用要求越高",
            event
        ))

    try:
        fee = int(arg_text)
    except ValueError:
        await set_mansion_fee_cmd.finish(message_add_head(
            "⛔ 请输入有效的数字",
            event
        ))

    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await set_mansion_fee_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        # 设置阴宅使用费用
        success, result_msg = await MansionService.set_mansion_usage_fee(session, player, fee)

        if success:
            # 保存数据
            await session.commit()
            await set_mansion_fee_cmd.finish(message_add_head(result_msg, event))
        else:
            await set_mansion_fee_cmd.finish(message_add_head(f"⛔ {result_msg}", event))


@toggle_mansion_access_cmd.handle()
async def handle_toggle_mansion_access(event: MessageEvent):
    """切换阴宅访问权限"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await toggle_mansion_access_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        # 切换阴宅访问权限
        success, result_msg = await MansionService.toggle_mansion_access(session, player)

        if success:
            # 保存数据
            await session.commit()
            await toggle_mansion_access_cmd.finish(message_add_head(result_msg, event))
        else:
            await toggle_mansion_access_cmd.finish(message_add_head(f"⛔ {result_msg}", event))


@toggle_mansion_payment_cmd.handle()
async def handle_toggle_mansion_payment(event: MessageEvent):
    """切换阴宅付费使用意愿"""
    user_id = event.get_user_id()
    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await toggle_mansion_payment_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        # 切换阴宅付费使用意愿
        success, result_msg = await MansionService.toggle_mansion_payment_willingness(session, player)

        if success:
            # 保存数据
            await session.commit()
            await toggle_mansion_payment_cmd.finish(message_add_head(result_msg, event))
        else:
            await toggle_mansion_payment_cmd.finish(message_add_head(f"⛔ {result_msg}", event))


@migrate_mansion_cmd.handle()
async def handle_migrate_mansion(event: MessageEvent, args: Message = CommandArg()):
    """迁移阴宅"""
    user_id = event.get_user_id()

    # 解析参数
    arg_text = args.extract_plain_text().strip()

    async with safe_session() as session:
        # 获取玩家数据
        player = await session.get(Player, user_id)
        if not player:
            await migrate_mansion_cmd.finish("⛔ 请先使用【注册】命令创建角色")

        # 如果没有参数，显示迁移帮助和确认信息
        if not arg_text:
            # 检查是否拥有阴宅
            if not MansionService.has_mansion(player):
                await migrate_mansion_cmd.finish(message_add_head(
                    "⛔ 你还没有阴宅，无法进行迁移\n"
                    "💡 请先使用【购买阴宅】命令购买阴宅",
                    event
                ))

            # 获取目标位置（玩家当前位置）
            target_x, target_y = player.get_current_coordinates()

            # 检查是否可以迁移
            can_migrate, error_msg = await MansionService.can_migrate_mansion(session, player, target_x, target_y)
            if not can_migrate:
                await migrate_mansion_cmd.finish(message_add_head(f"⛔ {error_msg}", event))

            # 显示迁移确认信息
            migration_cost = MansionService.calculate_migration_cost(player.mansion_level)
            old_x, old_y = player.mansion_x, player.mansion_y

            confirm_msg = (
                f"🏚️ 确认迁移阴宅\n"
                f"━━━━━━━━━━━━━\n"
                f"✧ 阴宅等级：{player.mansion_level}级\n"
                f"✧ 原位置：({old_x}, {old_y})\n"
                f"✧ 新位置：({target_x}, {target_y})\n"
                f"✧ 迁移费用：{migration_cost:,}金币\n"
                f"✧ 当前金币：{player.gold:,}金币\n"
                f"✧ 迁移后金币：{player.gold - migration_cost:,}金币\n"
                f"━━━━━━━━━━━━━\n"
                f"💡 迁移后阴宅等级、使用费用、权限设置等属性保持不变\n"
                f"⚠️ 请发送【迁移阴宅 确认】来执行迁移"
            )

            await migrate_mansion_cmd.finish(message_add_head(confirm_msg, event))

        # 如果参数是"确认"，执行迁移
        elif arg_text == "确认":
            # 获取目标位置（玩家当前位置）
            target_x, target_y = player.get_current_coordinates()

            # 执行迁移
            success, result_msg = await MansionService.migrate_mansion(session, player, target_x, target_y)

            if success:
                # 保存数据
                await session.commit()
                await migrate_mansion_cmd.finish(message_add_head(result_msg, event))
            else:
                await migrate_mansion_cmd.finish(message_add_head(f"⛔ {result_msg}", event))

        # 其他参数，显示帮助信息
        else:
            migration_cost = 0
            current_pos = "无阴宅"
            if MansionService.has_mansion(player):
                migration_cost = MansionService.calculate_migration_cost(player.mansion_level)
                current_pos = f"({player.mansion_x}, {player.mansion_y})"

            await migrate_mansion_cmd.finish(message_add_head(
                "🏚️ 阴宅迁移帮助\n"
                "━━━━━━━━━━━━━\n"
                "用法：【迁移阴宅】（查看迁移信息）\n"
                "用法：【迁移阴宅 确认】（执行迁移）\n"
                f"当前阴宅位置：{current_pos}\n"
                f"迁移费用：{migration_cost:,}金币（当前等级升级费用的50%）\n"
                "━━━━━━━━━━━━━\n"
                "⚠️ 迁移限制：\n"
                "• 只有阴宅主人可以迁移\n"
                "• 不能迁移到原点(0,0)\n"
                "• 不能距离城镇市集20格范围内\n"
                "• 新位置不能已有其他玩家的阴宅\n"
                "• 需要足够的金币支付迁移费用\n"
                "━━━━━━━━━━━━━\n"
                "💡 迁移后保持阴宅等级、使用费用、权限设置等所有属性不变",
                event
            ))



