from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .mentorship_service import MentorshipService
from ..player.realm_utils import realm_by_level_and_reincarnation

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的MentorshipService，False使用旧版本
USE_NEW_MENTORSHIP_SERVICE = True
# =====================================================


# ==================== 拜师 ====================
worship_cmd = on_command("拜师", block=True, priority=5)

@worship_cmd.handle()
async def handle_worship(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await worship_cmd.finish("格式：拜师 UID")
    
    try:
        master_uid = int(uid_str)
    except ValueError:
        await worship_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        # 获取申请人
        applicant = await get_unified_player(session, event)
        if not applicant:
            await worship_cmd.finish("⛔ 请先创建角色")
        
        # 获取目标师父
        master = (await session.execute(select(Player).where(Player.uid == master_uid))).scalars().first()
        if not master:
            await worship_cmd.finish("⛔ 未找到该 UID 的玩家")
        
        # 检查是否可以拜师
        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            can_worship, reason = await service.can_become_disciple(applicant.id, master.id)
        else:
            can_worship, reason = await MentorshipService.can_become_disciple(session, applicant.id, master.id)
        if not can_worship:
            await worship_cmd.finish(f"⛔ {reason}")
        
        # 创建拜师申请
        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            await service.create_mentorship_application(applicant.id, master.id)
        else:
            await MentorshipService.create_mentorship_application(session, applicant.id, master.id)

        await worship_cmd.finish(message_add_head(
            f"🙏 已向 {master.nickname}[UID:{master.uid}] 发送拜师申请，等待对方回复", 
            event
        ))


# ==================== 查看拜师申请 ====================
mentorship_applications_cmd = on_command("拜师申请", aliases={"师徒申请"}, block=True, priority=5)

@mentorship_applications_cmd.handle()
async def handle_mentorship_applications(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await mentorship_applications_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            applications = await service.get_pending_mentorship_applications(player.id)
        else:
            applications = await MentorshipService.get_pending_mentorship_applications(session, player.id)
        if not applications:
            await mentorship_applications_cmd.finish("暂无待处理的拜师申请")

        # 导入境界映射函数
        from ..player.info import realm_by_level

        lines = ["📜 待处理拜师申请", "━━━━━━━━━━"]
        for app in applications:
            applicant = await session.get(Player, app.applicant_id)
            lines.append(f"{applicant.nickname}[UID:{applicant.uid}] Lv.{applicant.level} {realm_by_level(applicant.level)}")

        lines.append("\n使用「收徒 UID」或「拒绝收徒 UID」来处理")
        await mentorship_applications_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 收徒 ====================
accept_disciple_cmd = on_command("收徒", block=True, priority=5)

@accept_disciple_cmd.handle()
async def handle_accept_disciple(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await accept_disciple_cmd.finish("格式：收徒 UID")
    
    try:
        applicant_uid = int(uid_str)
    except ValueError:
        await accept_disciple_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await accept_disciple_cmd.finish("⛔ 请先创建角色")
        
        # 根据UID查找申请人
        applicant = (await session.execute(select(Player).where(Player.uid == applicant_uid))).scalars().first()
        if not applicant:
            await accept_disciple_cmd.finish("⛔ 未找到该 UID 的玩家")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            success, message = await service.accept_mentorship_application_by_uid(applicant.id, player.id)
        else:
            success, message = await MentorshipService.accept_mentorship_application_by_uid(session, applicant.id, player.id)
        if success:
            await accept_disciple_cmd.finish(message_add_head(f"🎓 {message}", event))
        else:
            await accept_disciple_cmd.finish(f"⛔ {message}")


# ==================== 拒绝收徒 ====================
reject_disciple_cmd = on_command("拒绝收徒", block=True, priority=5)

@reject_disciple_cmd.handle()
async def handle_reject_disciple(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await reject_disciple_cmd.finish("格式：拒绝收徒 UID")
    
    try:
        applicant_uid = int(uid_str)
    except ValueError:
        await reject_disciple_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await reject_disciple_cmd.finish("⛔ 请先创建角色")
        
        # 根据UID查找申请人
        applicant = (await session.execute(select(Player).where(Player.uid == applicant_uid))).scalars().first()
        if not applicant:
            await reject_disciple_cmd.finish("⛔ 未找到该 UID 的玩家")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            success, message = await service.reject_mentorship_application_by_uid(applicant.id, player.id)
        else:
            success, message = await MentorshipService.reject_mentorship_application_by_uid(session, applicant.id, player.id)
        if success:
            await reject_disciple_cmd.finish(message_add_head(f"❌ {message}", event))
        else:
            await reject_disciple_cmd.finish(f"⛔ {message}")


# ==================== 查看师父 ====================
master_cmd = on_command("师父", aliases={"师傅"}, block=True, priority=5)

@master_cmd.handle()
async def handle_master(event: MessageEvent):
    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await master_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await master_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            master = await service.get_master(player.id)
        else:
            master = await MentorshipService.get_master(session, player.id)
        if not master:
            await master_cmd.finish("🚫 你还没有师父")

        # 导入境界映射函数
        from ..player.info import realm_by_level

        lines = [
            "👨‍🏫 师父信息",
            "━━━━━━━━━━",
            f"👤 姓名：{master.nickname}[UID:{master.uid}]",
            f"⚡ 等级：Lv.{master.level}",
            f"🏆 境界：{realm_by_level(master.level)}"
        ]

        await master_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 查看徒弟 ====================
disciples_cmd = on_command("徒弟", aliases={"弟子"}, block=True, priority=5)

@disciples_cmd.handle()
async def handle_disciples(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await disciples_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            disciples = await service.get_disciples(player.id)
        else:
            disciples = await MentorshipService.get_disciples(session, player.id)
        if not disciples:
            await disciples_cmd.finish("🚫 你还没有徒弟")

        # 使用境界映射函数

        lines = [f"👥 徒弟列表 ({len(disciples)}/5)", "━━━━━━━━━━"]
        for disciple in disciples:
            realm_name = realm_by_level_and_reincarnation(disciple.level, disciple.reincarnation_level)
            lines.append(f"👤 {disciple.nickname}[UID:{disciple.uid}] Lv.{disciple.level} {realm_name}")

        lines.append("\n使用「逐出徒弟 UID」可以逐出徒弟")
        lines.append("使用「出师 UID」可以让徒弟出师")
        await disciples_cmd.finish(message_add_head("\n".join(lines), event))


graduation_cmd = on_command("出师", block=True, priority=5)
@graduation_cmd.handle()
async def handle_graduation(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await graduation_cmd.finish("格式：出师 UID")

    try:
        disciple_uid = int(uid_str)
    except ValueError:
        await graduation_cmd.finish("UID 必须为数字")

    async with safe_session() as session:
        # 使用跨平台工具获取玩家数据
        from ..platform_utils import get_unified_player, is_guild_message
        player = await get_unified_player(session, event)
        if not player:
            if is_guild_message(event):
                await graduation_cmd.finish("⛔ 你还没有创建角色或绑定账号\n💡 请先在群聊注册角色，然后使用绑定功能")
            else:
                await graduation_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            success, message = await service.dismiss_disciple(player.id, disciple_uid, is_graduation=True)
        else:
            success, message = await MentorshipService.dismiss_disciple(session, player.id, disciple_uid, is_graduation=True)
        if success:
            await graduation_cmd.finish(message_add_head(f"🎓 {message}", event))
        else:
            await graduation_cmd.finish(f"⛔ {message}")


leave_master_cmd = on_command("脱离师门", aliases={"叛师"}, block=True, priority=5)

@leave_master_cmd.handle()
async def handle_leave_master(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await leave_master_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MENTORSHIP_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )
            success, message = await service.leave_master(player.id)
        else:
            success, message = await MentorshipService.leave_master(session, player.id)
        if success:
            await leave_master_cmd.finish(message_add_head(f"🚪 {message}", event))
        else:
            await leave_master_cmd.finish(f"⛔ {message}")
