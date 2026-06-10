"""
公会成员管理命令（成员列表/转让会长/入会申请审批/设置职位/踢出公会）

从 guild.py 逐字拆分搬移，零行为变化。
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select
from datetime import date

from ..models.db import safe_session
from ..models.player import Player
from ..models.guild import Guild, GuildMember, GuildPosition
from ..utils import message_add_head
from ..utils_markdown import cmd, build_markdown
from .guild_application_service import GuildApplicationService  # DI版本
from .guild_permission import GuildPermission
from .guild_economy_service import GuildEconomyService
from ..platform_utils import get_unified_player

# ==================== 公会成员列表 ====================
member_list_cmd = on_command("公会成员", aliases={"成员列表"}, block=True, priority=11)

@member_list_cmd.handle()
async def handle_member_list(event: MessageEvent, args: Message = CommandArg()):
    page_size = 20
    arg = args.extract_plain_text().strip()
    try:
        page = int(arg) if arg else 1
    except ValueError:
        page = 1
    page = max(1, page)

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service import GuildService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await member_list_cmd.finish("⛔ 你未加入任何公会")
        guild_obj = await uow.session.get(Guild, player.guild_id)
        if not guild_obj:
            await member_list_cmd.finish("⚠️ 公会数据异常")

        # 创建GuildService实例
        guild_service = GuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本获取成员列表
        all_members = await guild_service.get_guild_members(guild_obj.id)
    # 计算分页 (两个版本共享)
    total_members = len(all_members)
    if total_members == 0:
        await member_list_cmd.finish("⛔ 公会暂无成员")

    total_pages = (total_members - 1) // page_size + 1
    page = min(page, total_pages)

    # 获取当前页的成员
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    members = all_members[start_idx:end_idx]

    # 职位图标
    position_icons = {
        GuildPosition.PRESIDENT: "👑",
        GuildPosition.VICE_PRESIDENT: "⭐",
        GuildPosition.CORE_MEMBER: "🔸",
        GuildPosition.MEMBER: ""
    }

    lines = [
        f"# 👥 {guild_obj.name}",
        f"共**{total_members}**人　第**{page}**/{total_pages}页",
        "***",
    ]
    today = date.today()
    for idx, member in enumerate(members, start_idx + 1):
        icon = position_icons.get(member["position"], "")
        sign_mark = "✅" if (member.get("last_sign") and member["last_sign"].date() == today) else "⬜"
        nick_display = cmd(member['nickname'], f"面板 {member['uid']}")
        lines.append(
            f"{idx}. {sign_mark}{icon}{nick_display} Lv.{member['level']}　"
            f"{member['position_name']}　"
            f"贡献:{GuildEconomyService.format_large_number(member['contribution'])}"
        )

    lines.append("***")

    # 分页导航
    nav_parts = []
    if page > 1:
        nav_parts.append(cmd("上一页", f"公会成员 {page - 1}"))
    if page < total_pages:
        nav_parts.append(cmd("下一页", f"公会成员 {page + 1}"))
    if nav_parts:
        lines.append(" | ".join(nav_parts))

    lines.append(cmd("公会") + " | " + cmd("公会成员") + " | " + cmd("帮助"))

    await member_list_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 转让会长 ====================
transfer_cmd = on_command("转让会长", block=True, priority=11)

@transfer_cmd.handle()
async def handle_transfer(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await transfer_cmd.finish("⛔ 格式错误，示例：转让会长 123")
    try:
        target_uid = int(uid_str)
    except ValueError:
        await transfer_cmd.finish("⛔ UID 必须是数字")

    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or player.guild_id is None:
            await transfer_cmd.finish("⛔ 你未加入公会")
        guild_obj = await session.get(Guild, player.guild_id)
        if not guild_obj:
            await transfer_cmd.finish("⛔ 公会数据异常")

        # 通过 GuildMember 表检查职位（权威来源），同时兼容 president_id 直接比较
        member_position = await GuildPermission.get_member_position(session, player.id, guild_obj.id)
        is_president = (member_position == GuildPosition.PRESIDENT) or (guild_obj.president_id == player.id)
        if not is_president:
            await transfer_cmd.finish("⛔ 只有会长才能转让职位")

        target_player_stmt = select(Player).where(Player.uid == target_uid, Player.guild_id == guild_obj.id)
        target_player = (await session.execute(target_player_stmt)).scalars().first()
        if not target_player:
            await transfer_cmd.finish("⛔ 未找到目标成员或对方不在本公会")

        # 更新公会会长ID
        guild_obj.president_id = target_player.id
        session.add(guild_obj)

        # 同步更新 GuildMember 职位（保持两表一致）
        from sqlalchemy import update as sql_update
        await session.execute(
            sql_update(GuildMember)
            .where(GuildMember.guild_id == guild_obj.id, GuildMember.player_id == player.id)
            .values(position=GuildPosition.VICE_PRESIDENT)
        )
        await session.execute(
            sql_update(GuildMember)
            .where(GuildMember.guild_id == guild_obj.id, GuildMember.player_id == target_player.id)
            .values(position=GuildPosition.PRESIDENT)
        )

        await session.commit()
        msg = f"👑 会长职位已转让给 {target_player.nickname}[UID:{target_player.uid}]"
        await transfer_cmd.finish(message_add_head(msg, event))

# ==================== 申请列表 ====================
application_list_cmd = on_command("申请列表", block=True, priority=11)

@application_list_cmd.handle()
async def handle_app_list(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player or player.guild_id is None:
            await application_list_cmd.finish("⛔ 你未加入公会")

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(session, player.id, player.guild_id)
        if not can_manage:
            await application_list_cmd.finish(f"⛔ {reason}")

        # 新版：使用DI架构Service
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.guild_repository import GuildRepository
        from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
        service = GuildApplicationService(
            player_repo=PlayerRepository(session),
            guild_repo=GuildRepository(session),
            application_repo=SocialApplicationRepository(session)
        )
        apps = await service.get_pending_applications(player.guild_id)
        if not apps:
            await application_list_cmd.finish("暂无待处理申请")

        lines = [
            "# 📑 待处理入会申请",
            f"共**{len(apps)}**条",
            "***",
        ]
        for a in apps:
            applicant = await session.get(Player, a.applicant_id)
            lines.append(
                f"👤 {cmd(applicant.nickname, f'面板 {applicant.uid}')} Lv.{applicant.level}　"
                f"{cmd('✅同意', f'同意入会 {applicant.uid}')} | "
                f"{cmd('❌拒绝', f'拒绝入会 {applicant.uid}')}"
            )

        lines.append("***")
        lines.append(cmd("申请列表") + " | " + cmd("公会") + " | " + cmd("帮助"))
        await application_list_cmd.finish(build_markdown("\n".join(lines)))

# ==================== 同意/拒绝申请 ====================
approve_cmd = on_command("同意入会", block=True, priority=11)
reject_cmd = on_command("拒绝入会", block=True, priority=11)

async def _process_application(event: MessageEvent, args: Message, approve: bool):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await (approve_cmd if approve else reject_cmd).finish("格式：同意入会 UID 或 拒绝入会 UID")
    try:
        target_uid = int(uid_str)
    except ValueError:
        await (approve_cmd if approve else reject_cmd).finish("UID 必须为数字")

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service import GuildService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or player.guild_id is None:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 你未加入公会")

        # 检查是否有管理权限（会长和副会长）
        from .guild_permission import GuildPermission
        can_manage, reason = await GuildPermission.can_manage_guild(uow.session, player.id, player.guild_id)
        if not can_manage:
            await (approve_cmd if approve else reject_cmd).finish(f"⛔ {reason}")

        guild_obj = await uow.session.get(Guild, player.guild_id)
        applicant = (
            await uow.session.execute(
                select(Player).where(
                    Player.uid == target_uid,
                    Player.server_id == player.server_id,
                )
            )
        ).scalars().first()
        if not applicant:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 未找到该 UID")

        # 使用DI架构GuildApplicationService
        app_service = GuildApplicationService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            application_repo=uow.social_applications
        )
        app = await app_service.get_application_by_player_and_guild(applicant.id, guild_obj.id)

        if not app:
            await (approve_cmd if approve else reject_cmd).finish("⛔ 无待处理申请")

        if approve:
            # 创建GuildService实例
            guild_service = GuildService(
                player_repo=uow.players,
                guild_repo=uow.guilds,
                uow=uow
            )

            # 使用新版本加入公会
            success, reason = await guild_service.join_guild(applicant.id, guild_obj.id)
            if not success:
                await (approve_cmd if approve else reject_cmd).finish(message_add_head(f"⛔ {reason}", event))

            # 使用DI架构Service批准申请（检查返回值）
            approve_success, approve_reason = await app_service.approve_application(app, guild_obj)
            if not approve_success:
                # 批准申请失败，但玩家已经加入公会了，这是一个不一致的状态
                # 记录警告并继续（因为玩家实际上已经加入了）
                from nonebot import logger
                logger.warning(f"⚠️ [公会] 玩家 {applicant.nickname}[{target_uid}] 已加入公会，但批准申请失败: {approve_reason}")
                # 仍然显示成功消息，因为玩家已经实际加入了公会
                result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会（申请状态更新异常）"
            else:
                result_msg = f"✅ 已同意 {applicant.nickname}[UID:{target_uid}] 加入公会"
        else:
            # 使用DI架构Service拒绝申请
            await app_service.reject_application(app)
            result_msg = f"🚫 已拒绝 {applicant.nickname}[UID:{target_uid}] 的申请"

        # 显式提交事务（确保数据库更新）
        await uow.commit()

        await (approve_cmd if approve else reject_cmd).finish(message_add_head(result_msg, event))
@approve_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, True)

@reject_cmd.handle()
async def _(event: MessageEvent, args: Message = CommandArg()):
    await _process_application(event, args, False)

# ==================== 公会职位管理 ====================
set_position_cmd = on_command("设置职位", block=True, priority=11)

@set_position_cmd.handle()
async def handle_set_position(event: MessageEvent, args: Message = CommandArg()):
    """设置成员职位：设置职位 UID 职位名"""
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await set_position_cmd.finish("⛔ 格式错误，正确格式：设置职位 [UID] [职位名]\n可用职位：副会长、核心成员、普通成员")

    parts = args_text.split()
    if len(parts) != 2:
        await set_position_cmd.finish("⛔ 格式错误，正确格式：设置职位 [UID] [职位名]")

    target_uid, position_name = parts

    # 职位名映射
    position_map = {
        "副会长": GuildPosition.VICE_PRESIDENT,
        "核心成员": GuildPosition.CORE_MEMBER,
        "普通成员": GuildPosition.MEMBER
    }

    if position_name not in position_map:
        await set_position_cmd.finish("⛔ 无效的职位名，可用职位：副会长、核心成员、普通成员")

    new_position = position_map[position_name]

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service import GuildService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or not player.guild_id:
            await set_position_cmd.finish("⛔ 你未加入任何公会")

        # 查找目标玩家
        target_stmt = select(Player).where(
            Player.uid == int(target_uid),
            Player.server_id == player.server_id,
        )
        target_player = (await uow.session.execute(target_stmt)).scalars().first()
        if not target_player:
            await set_position_cmd.finish("⛔ 未找到该UID的玩家")

        if target_player.guild_id != player.guild_id:
            await set_position_cmd.finish("⛔ 该玩家不在你的公会中")

        # 创建GuildService实例
        guild_service = GuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本设置职位
        success, message = await guild_service.set_member_position(
            player.id, player.guild_id, target_player.id, new_position
        )

        if not success:
            await set_position_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit
        await set_position_cmd.finish(message_add_head(f"✅ {message}", event))
# ==================== 踢出公会成员 ====================
kick_member_cmd = on_command("踢出公会", aliases={"踢出成员"}, block=True, priority=11)

@kick_member_cmd.handle()
async def handle_kick_member(event: MessageEvent, args: Message = CommandArg()):
    """踢出公会成员：踢出公会 UID"""
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await kick_member_cmd.finish("⛔ 格式错误，正确格式：踢出公会 [UID]")

    try:
        target_uid = int(uid_str)
    except ValueError:
        await kick_member_cmd.finish("⛔ UID 必须是数字")

    # 新版本: 使用DI架构
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    from ..models.db import AsyncSessionLocal
    from .guild_service import GuildService

    def session_factory():
        return AsyncSessionLocal()

    async with UnitOfWork(session_factory) as uow:
        player = await get_unified_player(uow.session, event)
        if not player or not player.guild_id:
            await kick_member_cmd.finish("⛔ 你未加入任何公会")

        # 创建GuildService实例
        guild_service = GuildService(
            player_repo=uow.players,
            guild_repo=uow.guilds,
            uow=uow
        )

        # 使用新版本踢出成员
        success, message = await guild_service.kick_member(
            player.id, player.guild_id, target_uid
        )

        if not success:
            await kick_member_cmd.finish(f"⛔ {message}")

        # UoW会在__aexit__中自动commit
        await kick_member_cmd.finish(message_add_head(f"🚪 {message}", event))
