from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .marriage_service import MarriageService
from ..platform_utils import get_unified_player

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的MarriageService，False使用旧版本
USE_NEW_MARRIAGE_SERVICE = True
# =====================================================


# ==================== 求婚 ====================
propose_cmd = on_command("求婚", block=True, priority=5)

@propose_cmd.handle()
async def handle_propose(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await propose_cmd.finish("格式：求婚 UID")
    
    try:
        target_uid = int(uid_str)
    except ValueError:
        await propose_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        # 获取申请人
        proposer = await get_unified_player(session, event)
        if not proposer:
            await propose_cmd.finish("⛔ 请先创建角色")
        
        # 获取目标玩家
        target = (await session.execute(select(Player).where(Player.uid == target_uid))).scalars().first()
        if not target:
            await propose_cmd.finish("⛔ 未找到该 UID 的玩家")

        # 检查是否可以求婚
        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            can_propose, reason = await service.can_propose(proposer.id, target.id)
        else:
            can_propose, reason = await MarriageService.can_propose(session, proposer.id, target.id)
        if not can_propose:
            await propose_cmd.finish(f"⛔ {reason}")

        # 创建求婚申请
        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            await service.create_proposal(proposer.id, target.id)
        else:
            await MarriageService.create_proposal(session, proposer.id, target.id)

        await propose_cmd.finish(message_add_head(
            f"💕 已向 {target.nickname}[UID:{target.uid}] 发送求婚申请，等待对方回复",
            event
        ))


# ==================== 查看求婚申请 ====================
marriage_applications_cmd = on_command("求婚申请", aliases={"婚姻申请"}, block=True, priority=5)

@marriage_applications_cmd.handle()
async def handle_marriage_applications(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await marriage_applications_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            proposals = await service.get_pending_proposals(player.id)
        else:
            proposals = await MarriageService.get_pending_proposals(session, player.id)
        if not proposals:
            await marriage_applications_cmd.finish("暂无待处理的求婚申请")
        
        lines = ["💌 待处理求婚申请", "━━━━━━━━━━"]
        for proposal in proposals:
            proposer = await session.get(Player, proposal.applicant_id)
            lines.append(f"{proposer.nickname}[UID:{proposer.uid}] Lv.{proposer.level}")
        
        lines.append("\n使用「同意求婚 UID」或「拒绝求婚 UID」来处理")
        await marriage_applications_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 同意求婚 ====================
accept_proposal_cmd = on_command("同意求婚", block=True, priority=5)

@accept_proposal_cmd.handle()
async def handle_accept_proposal(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await accept_proposal_cmd.finish("格式：同意求婚 UID")
    
    try:
        proposer_uid = int(uid_str)
    except ValueError:
        await accept_proposal_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await accept_proposal_cmd.finish("⛔ 请先创建角色")
        
        # 根据UID查找申请人
        proposer = (await session.execute(select(Player).where(Player.uid == proposer_uid))).scalars().first()
        if not proposer:
            await accept_proposal_cmd.finish("⛔ 未找到该 UID 的玩家")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            success, message = await service.accept_proposal_by_uid(proposer.id, player.id)
        else:
            success, message = await MarriageService.accept_proposal_by_uid(session, proposer.id, player.id)
        if success:
            await accept_proposal_cmd.finish(message_add_head(f"💒 {message}", event))
        else:
            await accept_proposal_cmd.finish(f"⛔ {message}")


# ==================== 拒绝求婚 ====================
reject_proposal_cmd = on_command("拒绝求婚", block=True, priority=5)

@reject_proposal_cmd.handle()
async def handle_reject_proposal(event: MessageEvent, args: Message = CommandArg()):
    uid_str = args.extract_plain_text().strip()
    if not uid_str:
        await reject_proposal_cmd.finish("格式：拒绝求婚 UID")
    
    try:
        proposer_uid = int(uid_str)
    except ValueError:
        await reject_proposal_cmd.finish("UID 必须为数字")
    
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await reject_proposal_cmd.finish("⛔ 请先创建角色")
        
        # 根据UID查找申请人
        proposer = (await session.execute(select(Player).where(Player.uid == proposer_uid))).scalars().first()
        if not proposer:
            await reject_proposal_cmd.finish("⛔ 未找到该 UID 的玩家")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            success, message = await service.reject_proposal_by_uid(proposer.id, player.id)
        else:
            success, message = await MarriageService.reject_proposal_by_uid(session, proposer.id, player.id)
        if success:
            await reject_proposal_cmd.finish(message_add_head(f"💔 {message}", event))
        else:
            await reject_proposal_cmd.finish(f"⛔ {message}")


# ==================== 查看配偶 ====================
spouse_cmd = on_command("配偶", aliases={"老婆", "老公", "夫妻"}, block=True, priority=5)

@spouse_cmd.handle()
async def handle_spouse(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await spouse_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            spouse = await service.get_spouse(player.id)
        else:
            spouse = await MarriageService.get_spouse(session, player.id)
        if not spouse:
            await spouse_cmd.finish("💔 你还没有结婚")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            marriage = await service.get_marriage(player.id)
        else:
            marriage = await MarriageService.get_marriage(session, player.id)
        
        # 导入境界映射函数
        from ..player.info import realm_by_level

        lines = [
            "💕 配偶信息",
            "━━━━━━━━━━",
            f"👤 姓名：{spouse.nickname}[UID:{spouse.uid}]",
            f"⚡ 等级：Lv.{spouse.level}",
            f"🏆 境界：{realm_by_level(spouse.level)}",
            f"🎁 恩爱值：{marriage.total_gift_value}",
            f"💒 结婚时间：{marriage.married_at.strftime('%Y-%m-%d %H:%M')}"
        ]
        
        await spouse_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 离婚 ====================
divorce_cmd = on_command("离婚", block=True, priority=5)

@divorce_cmd.handle()
async def handle_divorce(event: MessageEvent):
    async with safe_session() as session:
        player = await get_unified_player(session, event)
        if not player:
            await divorce_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_MARRIAGE_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from .marriage_service_new import MarriageService as MarriageServiceNew

            service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            success, message = await service.divorce(player.id)
        else:
            success, message = await MarriageService.divorce(session, player.id)
        if success:
            await divorce_cmd.finish(message_add_head(f"💔 {message}", event))
        else:
            await divorce_cmd.finish(f"⛔ {message}")
