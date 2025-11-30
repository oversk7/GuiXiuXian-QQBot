from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg

from ..models.db import safe_session
from ..models.player import Player
from ..utils import message_add_head
from .gift_service import GiftService

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的GiftService，False使用旧版本
USE_NEW_GIFT_SERVICE = True
# 设置为True使用新版DI架构的MarriageService，False使用旧版本
USE_NEW_MARRIAGE_SERVICE = True
# 设置为True使用新版DI架构的MentorshipService，False使用旧版本
USE_NEW_MENTORSHIP_SERVICE = True
# =====================================================


# ==================== 送礼 ====================
send_gift_cmd = on_command("送礼", block=True, priority=5)

@send_gift_cmd.handle()
async def handle_send_gift(event: MessageEvent, args: Message = CommandArg()):
    args_text = args.extract_plain_text().strip()
    if not args_text:
        await send_gift_cmd.finish("格式：送礼 UID 物品名称 数量")
    
    parts = args_text.split()
    if len(parts) < 2:
        await send_gift_cmd.finish("格式：送礼 UID 物品名称 数量")
    
    try:
        receiver_uid = int(parts[0])
        item_name = parts[1]
        quantity = int(parts[2]) if len(parts) > 2 else 1
    except ValueError:
        await send_gift_cmd.finish("UID和数量必须为数字")
    
    if quantity <= 0:
        await send_gift_cmd.finish("数量必须大于0")
    
    async with safe_session() as session:
        sender = await session.get(Player, event.get_user_id())
        if not sender:
            await send_gift_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_GIFT_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.gift_record_repository import GiftRecordRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from .gift_service_new import GiftService as GiftServiceNew
            from .marriage_service_new import MarriageService as MarriageServiceNew
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            # 创建依赖的Service实例
            marriage_service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            mentorship_service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )

            # 创建GiftService实例
            service = GiftServiceNew(
                player_repo=PlayerRepository(session),
                marriage_service=marriage_service,
                mentorship_service=mentorship_service,
                gift_record_repo=GiftRecordRepository(session),
                item_repo=ItemRepository(session),
            )
            success, message = await service.send_gift(sender.id, receiver_uid, item_name, quantity)
        else:
            success, message = await GiftService.send_gift(session, sender.id, receiver_uid, item_name, quantity)

        if success:
            await send_gift_cmd.finish(message_add_head(f"🎁 {message}", event))
        else:
            await send_gift_cmd.finish(f"⛔ {message}")


# ==================== 送礼记录 ====================
gift_history_cmd = on_command("送礼记录", aliases={"我的送礼"}, block=True, priority=5)

@gift_history_cmd.handle()
async def handle_gift_history(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await gift_history_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_GIFT_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.gift_record_repository import GiftRecordRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from .gift_service_new import GiftService as GiftServiceNew
            from .marriage_service_new import MarriageService as MarriageServiceNew
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            # 创建依赖的Service实例
            marriage_service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            mentorship_service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )

            # 创建GiftService实例
            service = GiftServiceNew(
                player_repo=PlayerRepository(session),
                marriage_service=marriage_service,
                mentorship_service=mentorship_service,
                gift_record_repo=GiftRecordRepository(session),
                item_repo=ItemRepository(session),
            )
            gifts = await service.get_gift_history(player.id)
        else:
            gifts = await GiftService.get_gift_history(session, player.id)

        if not gifts:
            await gift_history_cmd.finish("暂无送礼记录")
        
        lines = ["🎁 送礼记录", "━━━━━━━━━━"]
        for gift in gifts:
            receiver = await session.get(Player, gift.receiver_id)
            gift_type_emoji = "💕" if gift.gift_type == "marriage" else "🎓"
            lines.append(
                f"{gift_type_emoji} 向 {receiver.nickname}[UID:{receiver.uid}] "
                f"送出 {gift.quantity}个「{gift.item_name}」(价值{gift.total_value})"
            )
            lines.append(f"   时间：{gift.sent_at.strftime('%m-%d %H:%M')}")
        
        await gift_history_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 收礼记录 ====================
received_gifts_cmd = on_command("收礼记录", aliases={"收到的礼物"}, block=True, priority=5)

@received_gifts_cmd.handle()
async def handle_received_gifts(event: MessageEvent):
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
        if not player:
            await received_gifts_cmd.finish("⛔ 请先创建角色")

        if USE_NEW_GIFT_SERVICE:
            from ..infrastructure.repositories.player_repository import PlayerRepository
            from ..infrastructure.repositories.gift_record_repository import GiftRecordRepository
            from ..infrastructure.repositories.item_repository import ItemRepository
            from ..infrastructure.repositories.marriage_repository import MarriageRepository
            from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
            from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
            from .gift_service_new import GiftService as GiftServiceNew
            from .marriage_service_new import MarriageService as MarriageServiceNew
            from .mentorship_service_new import MentorshipService as MentorshipServiceNew

            # 创建依赖的Service实例
            marriage_service = MarriageServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                marriage_repo=MarriageRepository(session),
            )
            mentorship_service = MentorshipServiceNew(
                player_repo=PlayerRepository(session),
                social_app_repo=SocialApplicationRepository(session),
                mentorship_repo=MentorshipRepository(session),
            )

            # 创建GiftService实例
            service = GiftServiceNew(
                player_repo=PlayerRepository(session),
                marriage_service=marriage_service,
                mentorship_service=mentorship_service,
                gift_record_repo=GiftRecordRepository(session),
                item_repo=ItemRepository(session),
            )
            gifts = await service.get_received_gifts(player.id)
        else:
            gifts = await GiftService.get_received_gifts(session, player.id)

        if not gifts:
            await received_gifts_cmd.finish("暂无收礼记录")
        
        lines = ["🎁 收礼记录", "━━━━━━━━━━"]
        for gift in gifts:
            sender = await session.get(Player, gift.sender_id)
            gift_type_emoji = "💕" if gift.gift_type == "marriage" else "🎓"
            lines.append(
                f"{gift_type_emoji} {sender.nickname}[UID:{sender.uid}] "
                f"送来 {gift.quantity}个「{gift.item_name}」(价值{gift.total_value})"
            )
            lines.append(f"   时间：{gift.sent_at.strftime('%m-%d %H:%M')}")
        
        await received_gifts_cmd.finish(message_add_head("\n".join(lines), event))
