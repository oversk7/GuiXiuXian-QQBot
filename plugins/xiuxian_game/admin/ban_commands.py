"""
全局封禁管理命令
仅限管理员使用
"""
from datetime import datetime, timedelta
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..models.player_ban import PlayerBan
from ..models.account_ownership import AccountOwnership
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from ..ai_guide import is_admin


# 全局封禁管理命令
global_ban_cmd = on_command("封禁", block=True, priority=15)
global_unban_cmd = on_command("解封", block=True, priority=15)
ban_list_cmd = on_command("封禁列表", aliases={"查看封禁"}, block=True, priority=15)
ban_info_cmd = on_command("封禁信息", block=True, priority=15)


@global_ban_cmd.handle()
async def handle_global_ban(event: MessageEvent, args: Message = CommandArg()):
    """
    全局封禁命令：【封禁 UID [原因] [时长]】

    被封禁的玩家将无法执行任何游戏指令
    """
    if not is_admin(event.get_user_id()):
        await global_ban_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await global_ban_cmd.finish(
            "⛔ 用法：【封禁 UID】或【封禁 UID 原因】或【封禁 UID 原因 时长】\n"
            "时长格式：3d（3天）、24h（24小时）、永久\n"
            "⚠️ 警告：全局封禁将禁止玩家执行所有游戏指令！"
        )

    parts = raw_text.split(maxsplit=2)
    target_uid_text = parts[0]
    reason = parts[1] if len(parts) > 1 else "违反游戏规则"
    duration_text = parts[2] if len(parts) > 2 else "永久"

    try:
        target_uid = int(target_uid_text)
    except ValueError:
        await global_ban_cmd.finish("⛔ UID 格式错误，请输入数字")

    # 解析时长
    ban_type = "permanent"
    expires_at = None
    if duration_text != "永久":
        ban_type = "temporary"
        try:
            if duration_text.endswith('d'):
                days = int(duration_text[:-1])
                expires_at = datetime.now() + timedelta(days=days)
            elif duration_text.endswith('h'):
                hours = int(duration_text[:-1])
                expires_at = datetime.now() + timedelta(hours=hours)
            else:
                await global_ban_cmd.finish("⛔ 时长格式错误，请使用：3d（3天）、24h（24小时）或永久")
        except ValueError:
            await global_ban_cmd.finish("⛔ 时长格式错误，请输入有效的数字")

    async with safe_session() as session:
        # 获取管理员信息
        admin = await get_unified_player(session, event)
        if not admin:
            await global_ban_cmd.finish("⛔ 请先创建角色")

        # 获取目标玩家
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await global_ban_cmd.finish(f"⛔ 未找到 UID 为 {target_uid} 的玩家")

        # 防止封禁管理员账号（target.id 是角色 ID，新注册玩家为 UUID，
        # 需通过账号所有权还原其所属平台 ID 后再判断）
        owner_platform_id = (
            await session.execute(
                select(AccountOwnership.owner_platform_id).where(
                    AccountOwnership.player_id == target.id
                )
            )
        ).scalar_one_or_none()
        if owner_platform_id is None:
            # 老玩家没有 ownership 记录时，Player.id 即平台 ID
            owner_platform_id = target.id
        if is_admin(owner_platform_id):
            await global_ban_cmd.finish("⛔ 无法封禁管理员账号")

        # 检查是否已在封禁列表
        existing = (
            await session.execute(
                select(PlayerBan).where(
                    PlayerBan.player_id == target.id,
                    PlayerBan.is_active == True
                )
            )
        ).scalars().first()

        if existing:
            # 更新现有记录
            existing.reason = reason
            existing.ban_type = ban_type
            existing.expires_at = expires_at
            existing.admin_id = admin.id
            existing.created_at = datetime.now()
        else:
            # 创建新记录
            ban_record = PlayerBan(
                player_id=target.id,
                admin_id=admin.id,
                reason=reason,
                ban_type=ban_type,
                expires_at=expires_at,
                is_active=True
            )
            session.add(ban_record)

        await session.commit()

    duration_str = duration_text if duration_text == "永久" else duration_text
    msg = (
        f"✅ 已全局封禁玩家【{target.nickname}】(UID:{target_uid})\n"
        f"原因：{reason}\n"
        f"时长：{duration_str}\n"
        f"⚠️ 该玩家将无法执行任何游戏指令"
    )
    await global_ban_cmd.finish(message_add_head(msg, event))


@global_unban_cmd.handle()
async def handle_global_unban(event: MessageEvent, args: Message = CommandArg()):
    """解封命令：【解封 UID】"""
    if not is_admin(event.get_user_id()):
        await global_unban_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await global_unban_cmd.finish("⛔ 用法：【解封 UID】")

    try:
        target_uid = int(raw_text)
    except ValueError:
        await global_unban_cmd.finish("⛔ UID 格式错误，请输入数字")

    async with safe_session() as session:
        # 获取目标玩家
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await global_unban_cmd.finish(f"⛔ 未找到 UID 为 {target_uid} 的玩家")

        # 查找封禁记录
        record = (
            await session.execute(
                select(PlayerBan).where(
                    PlayerBan.player_id == target.id,
                    PlayerBan.is_active == True
                )
            )
        ).scalars().first()

        if not record:
            await global_unban_cmd.finish(f"⛔ 玩家【{target.nickname}】(UID:{target_uid}) 未被封禁")

        # 解封
        record.is_active = False
        await session.commit()

    msg = f"✅ 已解除玩家【{target.nickname}】(UID:{target_uid}) 的全局封禁"
    await global_unban_cmd.finish(message_add_head(msg, event))


@ban_list_cmd.handle()
async def handle_ban_list(event: MessageEvent):
    """查看封禁列表"""
    if not is_admin(event.get_user_id()):
        await ban_list_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    async with safe_session() as session:
        records = (
            await session.execute(
                select(PlayerBan)
                .where(PlayerBan.is_active == True)
                .order_by(PlayerBan.created_at.desc())
            )
        ).scalars().all()

        if not records:
            await ban_list_cmd.finish(message_add_head("📋 当前封禁列表为空", event))

        # 获取所有相关玩家信息
        player_ids = set()
        for rec in records:
            player_ids.add(rec.player_id)
            player_ids.add(rec.admin_id)

        players = {}
        for pid in player_ids:
            players[pid] = await session.get(Player, pid)

    lines = [f"📋 全局封禁列表（共{len(records)}人）", "━━━━━━━━━━"]
    for rec in records:
        target_player = players.get(rec.player_id)
        admin_player = players.get(rec.admin_id)

        if not target_player:
            continue

        time_str = rec.created_at.strftime("%m-%d %H:%M")
        remaining = rec.get_remaining_time()
        admin_name = admin_player.nickname if admin_player else "未知"
        ban_type_str = "🔴永久" if rec.ban_type == "permanent" else "🟠临时"

        lines.append(
            f">{ban_type_str} 【{target_player.nickname}】UID:{target_player.uid}\n"
            f" 原因：{rec.reason or '无'}\n"
            f" 剩余：{remaining} | 操作员：{admin_name}\n"
            f" 时间：{time_str}"
        )

    await ban_list_cmd.finish(message_add_head("\n".join(lines), event))


@ban_info_cmd.handle()
async def handle_ban_info(event: MessageEvent, args: Message = CommandArg()):
    """查看指定玩家的封禁信息：【封禁信息 UID】"""
    if not is_admin(event.get_user_id()):
        await ban_info_cmd.finish("⛔ 权限不足，该命令仅限管理员使用")

    raw_text = args.extract_plain_text().strip()
    if not raw_text:
        await ban_info_cmd.finish("⛔ 用法：【封禁信息 UID】")

    try:
        target_uid = int(raw_text)
    except ValueError:
        await ban_info_cmd.finish("⛔ UID 格式错误，请输入数字")

    async with safe_session() as session:
        # 获取目标玩家
        target = (
            await session.execute(select(Player).where(Player.uid == target_uid))
        ).scalars().first()
        if not target:
            await ban_info_cmd.finish(f"⛔ 未找到 UID 为 {target_uid} 的玩家")

        # 查找封禁记录
        record = (
            await session.execute(
                select(PlayerBan).where(
                    PlayerBan.player_id == target.id,
                    PlayerBan.is_active == True
                )
            )
        ).scalars().first()

        if not record:
            await ban_info_cmd.finish(f"✅ 玩家【{target.nickname}】(UID:{target_uid}) 未被封禁")

        admin = await session.get(Player, record.admin_id)
        admin_name = admin.nickname if admin else "未知"

    ban_type_str = "永久封禁" if record.ban_type == "permanent" else "临时封禁"
    time_str = record.created_at.strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        f"📋 封禁信息\n"
        f"━━━━━━━━━━\n"
        f"玩家：【{target.nickname}】UID:{target_uid}\n"
        f"类型：{ban_type_str}\n"
        f"原因：{record.reason or '无'}\n"
        f"剩余时间：{record.get_remaining_time()}\n"
        f"操作管理员：{admin_name}\n"
        f"封禁时间：{time_str}"
    )
    await ban_info_cmd.finish(message_add_head(msg, event))
