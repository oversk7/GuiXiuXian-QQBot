"""
账号切换命令处理器

玩家命令：
- 我的账号 - 查看拥有的所有游戏账号
- 切换账号 <账号ID> - 切换到指定的游戏账号
- 重命名账号 <账号ID> <新名称> - 重命名账号备注
- 转让历史 - 查看账号买入/卖出历史

管理员命令（仅SUPERUSER）：
- 生成转让密钥 <账号ID> - 为玩家生成账号转让密钥（账号买卖）
- 接收账号 <转让密钥> - 使用转让密钥接收账号
- 取消转让 <账号ID> - 取消账号的转让密钥
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


# ==================== 我的账号 ====================
my_accounts_cmd = on_command("我的账号", aliases={"账号列表"}, block=True, priority=5)

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

        await my_accounts_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 切换账号 ====================
switch_account_cmd = on_command("切换账号", block=True, priority=5)

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
        target_player = await player_repo.get_by_uid(target_uid)
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
rename_account_cmd = on_command("重命名账号", block=True, priority=5)

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
        target_player = await player_repo.get_by_uid(target_uid)
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


# ==================== 生成转让密钥 ====================
generate_transfer_key_cmd = on_command("生成转让密钥", aliases={"转让账号"}, block=True, priority=5, permission=SUPERUSER)

@generate_transfer_key_cmd.handle()
async def handle_generate_transfer_key(event: MessageEvent, args: Message = CommandArg()):
    """生成账号转让密钥"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await generate_transfer_key_cmd.finish("⛔ 请提供要转让的账号UID\n格式：生成转让密钥 <UID>")

    platform_id = event.get_user_id()

    # 将UID转换为整数
    try:
        target_uid = int(args_text)
    except ValueError:
        await generate_transfer_key_cmd.finish("⛔ UID必须是数字")

    async with safe_session() as session:
        # 通过UID查询player_id
        player_repo = PlayerRepository(session)
        target_player = await player_repo.get_by_uid(target_uid)
        if not target_player:
            await generate_transfer_key_cmd.finish(f"⛔ UID {target_uid} 不存在")

        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=player_repo
        )

        success, result = await service.generate_transfer_key(platform_id, target_player.id)

        if success:
            await session.commit()
            transfer_key = result
            lines = [
                "🔑 转让密钥生成成功",
                "━━━━━━━━━━",
                f"账号UID: {target_player.uid}",
                f"转让密钥: {transfer_key}",
                "━━━━━━━━━━",
                "⚠️ 请妥善保管此密钥",
                "⚠️ 任何获得密钥的人都可以接收此账号",
                "⚠️ 转让后无法撤回",
                "\n💡 提示: 使用「取消转让 UID」取消转让"
            ]
            await generate_transfer_key_cmd.finish(message_add_head("\n".join(lines), event))
        else:
            await generate_transfer_key_cmd.finish(f"⛔ {result}")


# ==================== 接收账号 ====================
accept_transfer_cmd = on_command("接收账号", aliases={"使用转让密钥"}, block=True, priority=5, permission=SUPERUSER)

@accept_transfer_cmd.handle()
async def handle_accept_transfer(event: MessageEvent, args: Message = CommandArg()):
    """使用转让密钥接收账号"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await accept_transfer_cmd.finish("⛔ 请提供转让密钥\n格式：接收账号 <转让密钥>")

    platform_id = event.get_user_id()
    transfer_key = args_text

    async with safe_session() as session:
        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=PlayerRepository(session)
        )

        success, message = await service.accept_transfer(platform_id, transfer_key)

        if success:
            await session.commit()
            lines = [
                "🎉 账号接收成功",
                "━━━━━━━━━━",
                message,
                "━━━━━━━━━━",
                "💡 提示: 使用「我的账号」查看所有账号",
                "💡 提示: 使用「切换账号 UID」激活新账号"
            ]
            await accept_transfer_cmd.finish(message_add_head("\n".join(lines), event))
        else:
            await accept_transfer_cmd.finish(f"⛔ {message}")


# ==================== 取消转让 ====================
cancel_transfer_cmd = on_command("取消转让", block=True, priority=5, permission=SUPERUSER)

@cancel_transfer_cmd.handle()
async def handle_cancel_transfer(event: MessageEvent, args: Message = CommandArg()):
    """取消账号的转让密钥"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await cancel_transfer_cmd.finish("⛔ 请提供账号UID\n格式：取消转让 <UID>")

    platform_id = event.get_user_id()

    # 将UID转换为整数
    try:
        target_uid = int(args_text)
    except ValueError:
        await cancel_transfer_cmd.finish("⛔ UID必须是数字")

    async with safe_session() as session:
        # 通过UID查询player_id
        player_repo = PlayerRepository(session)
        target_player = await player_repo.get_by_uid(target_uid)
        if not target_player:
            await cancel_transfer_cmd.finish(f"⛔ UID {target_uid} 不存在")

        # 创建Service
        service = AccountSwitchingService(
            ownership_repo=AccountOwnershipRepository(session),
            transfer_log_repo=AccountTransferLogRepository(session),
            player_repo=player_repo
        )

        success, message = await service.cancel_transfer_key(platform_id, target_player.id)

        if success:
            await session.commit()
            await cancel_transfer_cmd.finish(message_add_head(f"✅ {message}", event))
        else:
            await cancel_transfer_cmd.finish(f"⛔ {message}")


# ==================== 转让历史 ====================
transfer_history_cmd = on_command("转让历史", aliases={"账号交易历史"}, block=True, priority=5)

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
                    "admin": "管理员转让"
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
                    "admin": "管理员转让"
                }.get(log["transfer_type"], log["transfer_type"])
                lines.append(
                    f"  {transfer_type_text} 账号 {log['player_id']}\n"
                    f"  给: {log['to_platform_id']}\n"
                    f"  时间: {log['transfer_time'].strftime('%Y-%m-%d %H:%M')}"
                )

        await transfer_history_cmd.finish(message_add_head("\n".join(lines), event))
