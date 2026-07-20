"""
账号切换命令处理器

玩家命令：
- 我的账号 - 查看拥有的所有游戏账号
- 切换账号 <账号ID> - 切换到指定的游戏账号
- 重命名账号 <账号ID> <新名称> - 重命名账号备注
- 转让历史 - 查看账号买入/卖出历史

账号转移只能通过赞助商店（【购买绑定小号】/借号权），转让密钥途径已移除。

管理员命令（仅SUPERUSER）：
- 临时切换 <UID> - 管理员临时切换到指定账号（不改变所有权）
- 退出临时切换 - 管理员退出临时切换状态
- 临时切换状态 - 查看当前临时切换状态
"""

from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from ..infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
from ..infrastructure.repositories.account_transfer_log_repository import AccountTransferLogRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from .account_switching_service import AccountSwitchingService
from ..platform_utils import (
    admin_temp_switch_to,
    admin_exit_temp_switch,
    is_admin_temp_switching,
    get_admin_temp_switch_target,
    get_event_server_id,
)


# ==================== 我的账号 ====================
my_accounts_cmd = on_command("我的账号", aliases={"账号列表"}, block=True, priority=11)

@my_accounts_cmd.handle()
async def handle_my_accounts(event: MessageEvent):
    """查看拥有的所有游戏账号"""
    platform_id = event.get_user_id()

    async with safe_session() as session:
        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=PlayerRepository(session)
        )

        accounts = await service.list_owned_accounts(platform_id)

        if not accounts:
            await my_accounts_cmd.finish("⛔ 你还没有游戏账号，请先创建角色")

        # 构建账号列表
        lines = ["👤 我的游戏账号", "━━━━━━━━━━"]
        for acc in accounts:
            if acc.get("lent_out"):
                status = "📤 已借出"
            elif acc.get("borrowed"):
                status = "🤝 借用中" + ("（✅ 激活）" if acc["is_active"] else "")
            else:
                status = "✅ 激活中" if acc["is_active"] else "⚪ 未激活"
            lines.append(
                f"{status} {acc['display_name']}\n"
                f"   角色名: {acc['player_name']} | UID: {acc['uid']}\n"
                f"   等级: Lv.{acc['level']}\n"
                f"   账号ID: {acc['player_id']}\n"
                f"   获得方式: {acc['acquired_type']}"
            )
            lines.append("━━━━━━━━━━")

        lines.append(f"共 {len(accounts)} 个账号")
        lines.append("\n💡 提示: 使用「切换账号 UID」切换账号")
        if any(acc.get("lent_out") for acc in accounts):
            lines.append("💡 提示: 使用「收回账号 UID」收回借出的账号")

        await my_accounts_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 切换账号 ====================
switch_account_cmd = on_command("切换账号", block=True, priority=11)

@switch_account_cmd.handle()
async def handle_switch_account(event: MessageEvent, args: Message = CommandArg()):
    """切换到指定的游戏账号"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await switch_account_cmd.finish("⛔ 请提供要切换的账号UID\n格式：切换账号 <UID>")

    platform_id = event.get_user_id()

    # 将UID转换为整数
    try:
        target_uid = int(args_text)
    except ValueError:
        await switch_account_cmd.finish("⛔ UID必须是数字")

    async with safe_session() as session:
        # 通过UID查询player_id
        player_repo = PlayerRepository(session)
        server_id = await get_event_server_id(session, event)
        target_player = await player_repo.get_by_uid(target_uid, server_id)
        if not target_player:
            await switch_account_cmd.finish(f"⛔ UID {target_uid} 不存在")

        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=player_repo
        )

        success, message = await service.switch_account(platform_id, target_player.id)

        if success:
            await session.commit()
            await switch_account_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await switch_account_cmd.finish(f"⛔ {message}")


# ==================== 重命名账号 ====================
rename_account_cmd = on_command("重命名账号", block=True, priority=11)

@rename_account_cmd.handle()
async def handle_rename_account(event: MessageEvent, args: Message = CommandArg()):
    """重命名账号备注"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await rename_account_cmd.finish("⛔ 请提供账号UID和新名称\n格式：重命名账号 <UID> <新名称>")

    parts = args_text.split(maxsplit=1)
    if len(parts) < 2:
        await rename_account_cmd.finish("⛔ 请提供账号UID和新名称\n格式：重命名账号 <UID> <新名称>")

    platform_id = event.get_user_id()

    # 将UID转换为整数
    try:
        target_uid = int(parts[0])
    except ValueError:
        await rename_account_cmd.finish("⛔ UID必须是数字")

    display_name = parts[1]

    async with safe_session() as session:
        # 通过UID查询player_id
        player_repo = PlayerRepository(session)
        server_id = await get_event_server_id(session, event)
        target_player = await player_repo.get_by_uid(target_uid, server_id)
        if not target_player:
            await rename_account_cmd.finish(f"⛔ UID {target_uid} 不存在")

        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=player_repo
        )

        success, message = await service.rename_account(platform_id, target_player.id, display_name)

        if success:
            await session.commit()
            await rename_account_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await rename_account_cmd.finish(f"⛔ {message}")


# ==================== 转让历史 ====================
transfer_history_cmd = on_command("转让历史", aliases={"账号交易历史"}, block=True, priority=11)

@transfer_history_cmd.handle()
async def handle_transfer_history(event: MessageEvent):
    """查看账号买入/卖出历史"""
    platform_id = event.get_user_id()

    async with safe_session() as session:
        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=PlayerRepository(session)
        )

        history = await service.get_transfer_history(platform_id, limit=10)

        bought = history["bought"]
        sold = history["sold"]

        if not bought and not sold:
            await transfer_history_cmd.finish("暂无转让历史")

        lines = ["📊 账号转让历史", "━━━━━━━━━━"]

        if bought:
            lines.append("🛒 买入/接收:")
            for log in bought:
                transfer_type_text = {
                    "sale": "买入",
                    "gift": "获赠",
                    "admin": "管理员转让",
                    "lend": "借入",
                    "lend_return": "收回/归还"
                }.get(log["transfer_type"], log["transfer_type"])
                lines.append(
                    f"  {transfer_type_text} 账号 {log['player_id']}\n"
                    f"  来自: {log['from_platform_id']}\n"
                    f"  时间: {log['transfer_time'].strftime('%Y-%m-%d %H:%M')}"
                )
            lines.append("━━━━━━━━━━")

        if sold:
            lines.append("💰 卖出/转让:")
            for log in sold:
                transfer_type_text = {
                    "sale": "卖出",
                    "gift": "赠送",
                    "admin": "管理员转让",
                    "lend": "借出",
                    "lend_return": "收回/归还"
                }.get(log["transfer_type"], log["transfer_type"])
                lines.append(
                    f"  {transfer_type_text} 账号 {log['player_id']}\n"
                    f"  给: {log['to_platform_id']}\n"
                    f"  时间: {log['transfer_time'].strftime('%Y-%m-%d %H:%M')}"
                )

        await transfer_history_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 临时切换（管理员调试功能） ====================
admin_temp_switch_cmd = on_command("临时切换", aliases={"临时切换账号"}, block=True, priority=11, permission=SUPERUSER)

@admin_temp_switch_cmd.handle()
async def handle_admin_temp_switch(event: MessageEvent, args: Message = CommandArg()):
    """管理员临时切换到指定账号进行调试"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await admin_temp_switch_cmd.finish("⛔ 请提供要临时切换的账号UID\n格式：临时切换 <UID>")

    admin_platform_id = event.get_user_id()

    # 将UID转换为整数
    try:
        target_uid = int(args_text)
    except ValueError:
        await admin_temp_switch_cmd.finish("⛔ UID必须是数字")

    async with safe_session() as session:
        # 通过UID查询player_id
        player_repo = PlayerRepository(session)
        server_id = await get_event_server_id(session, event)
        target_player = await player_repo.get_by_uid(target_uid, server_id)
        if not target_player:
            await admin_temp_switch_cmd.finish(f"⛔ UID {target_uid} 不存在")

        # 执行临时切换
        admin_temp_switch_to(admin_platform_id, target_player.id)

        lines = [
            "🔧 管理员临时切换成功",
            "━━━━━━━━━━",
            f"目标账号: {target_player.nickname}",
            f"UID: {target_player.uid}",
            f"等级: Lv.{target_player.level}",
            "━━━━━━━━━━",
            "⚠️ 你现在以该账号的身份操作游戏",
            "⚠️ 账号所有权未改变",
            "⚠️ 使用「退出临时切换」恢复自己的账号",
            "\n💡 提示: 所有游戏命令现在都作用于目标账号"
        ]
        await admin_temp_switch_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 退出临时切换 ====================
exit_temp_switch_cmd = on_command("退出临时切换", aliases={"取消临时切换"}, block=True, priority=11, permission=SUPERUSER)

@exit_temp_switch_cmd.handle()
async def handle_exit_temp_switch(event: MessageEvent):
    """管理员退出临时切换状态"""
    admin_platform_id = event.get_user_id()

    # 检查是否在临时切换状态
    if not is_admin_temp_switching(admin_platform_id):
        await exit_temp_switch_cmd.finish("⛔ 你当前没有在临时切换状态")

    # 获取临时切换的目标信息（用于显示）
    target_player_id = get_admin_temp_switch_target(admin_platform_id)

    async with safe_session() as session:
        target_player = None
        if target_player_id:
            target_player = await session.get(Player, target_player_id)

    # 退出临时切换
    admin_exit_temp_switch(admin_platform_id)

    lines = [
        "✅ 已退出临时切换",
        "━━━━━━━━━━"
    ]
    if target_player:
        lines.append(f"之前临时切换的账号: {target_player.nickname} (UID: {target_player.uid})")
        lines.append("━━━━━━━━━━")
    lines.append("💡 你已恢复为自己的账号")

    await exit_temp_switch_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 临时切换状态 ====================
temp_switch_status_cmd = on_command("临时切换状态", block=True, priority=11, permission=SUPERUSER)

@temp_switch_status_cmd.handle()
async def handle_temp_switch_status(event: MessageEvent):
    """查看当前临时切换状态"""
    admin_platform_id = event.get_user_id()

    if not is_admin_temp_switching(admin_platform_id):
        await temp_switch_status_cmd.finish("⛔ 你当前没有在临时切换状态")

    target_player_id = get_admin_temp_switch_target(admin_platform_id)

    async with safe_session() as session:
        target_player = None
        if target_player_id:
            target_player = await session.get(Player, target_player_id)

        if not target_player:
            await temp_switch_status_cmd.finish("⛔ 临时切换的目标账号不存在")

        lines = [
            "🔧 临时切换状态",
            "━━━━━━━━━━",
            f"当前切换到: {target_player.nickname}",
            f"UID: {target_player.uid}",
            f"等级: Lv.{target_player.level}",
            f"境界: {target_player.cultivation_level_name}",
            "━━━━━━━━━━",
            "💡 所有游戏命令都作用于此账号",
            "💡 使用「退出临时切换」恢复自己的账号"
        ]
        await temp_switch_status_cmd.finish(message_add_head("\n".join(lines), event))
