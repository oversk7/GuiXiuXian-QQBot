"""
关系管理命令处理器

提供好感度查询、关系解除等功能
"""
from nonebot import on_command
from nonebot.adapters.qq import MessageEvent, Message
from nonebot.params import CommandArg
from sqlalchemy import select, and_, or_

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..models.player_relationship import PlayerRelationship, RelationshipType
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .relationship_service import RelationshipService


# ==================== 好感度查询 ====================
favorability_cmd = on_command("好感度", aliases={"查看好感度"}, priority=5, block=True)

@favorability_cmd.handle()
async def handle_favorability(event: MessageEvent, args: Message = CommandArg()):
    """查询与指定玩家的好感度"""
    args_text = args.extract_plain_text().strip()

    # 获取玩家
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await favorability_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        if not args_text:
            # 没有参数,显示当前所有关系
            service = RelationshipService(
                player_repo=uow.players,
                relationship_repo=uow.player_relationships,
                item_repo=uow.items,
                uow=uow
            )

            # 查询所有有关系的好友
            stmt = select(PlayerRelationship).where(
                and_(
                    or_(
                        PlayerRelationship.player_id == player.id,
                        PlayerRelationship.target_id == player.id
                    ),
                    PlayerRelationship.favorability > 0
                )
            )
            result = await uow.session.execute(stmt)
            relationships = result.scalars().all()

            if not relationships:
                await favorability_cmd.finish(message_add_head("💕 你还没有任何好感度记录\n\n💡 使用【赠礼 UID 礼物名】向其他玩家赠送礼物", event))
                return

            lines = ["💕 你的好感度记录", "━━━━━━━━━━━━━"]

            for rel in relationships:
                # 获取对方ID
                other_id = rel.target_id if rel.player_id == player.id else rel.player_id
                other = await uow.players.get_by_id(other_id)

                if other:
                    favorability = rel.favorability
                    # 获取关系描述
                    if rel.relationship_type == RelationshipType.MARRIAGE.value:
                        rel_desc = f"💒 夫妻 (好感度: {favorability})"
                    elif rel.relationship_type == RelationshipType.SWORN.value:
                        rel_desc = f"🤝 结义 (好感度: {favorability})"
                    elif rel.relationship_type == RelationshipType.MENTORSHIP.value:
                        rel_desc = f"🎓 师徒 (好感度: {favorability})"
                    else:
                        # 美化好感度显示 - 使用颜色符号,不划分等级
                        if favorability > 0:
                            rel_desc = f"💖 +{favorability}"
                        elif favorability < 0:
                            rel_desc = f"💔 {favorability}"
                        else:
                            rel_desc = "➖ 0"

                    lines.append(f"{other.nickname}[UID:{other.uid}] - {rel_desc}")

            lines.append("")
            lines.append("💡 使用【好感度 UID】查看详细信息")
            await favorability_cmd.finish(message_add_head("\n".join(lines), event))
        else:
            # 有参数,查询指定玩家的好感度
            try:
                target_uid = int(args_text.strip())
            except ValueError:
                await favorability_cmd.finish(message_add_head("⛔ UID格式错误,请输入数字", event))
                return

            service = RelationshipService(
                player_repo=uow.players,
                relationship_repo=uow.player_relationships,
                item_repo=uow.items,
                uow=uow
            )

            favorability, relation_desc = await service.get_favorability(player.id, target_uid)

            # 获取目标玩家
            target = await uow.players.get_by_uid(target_uid)
            if not target:
                await favorability_cmd.finish(message_add_head(f"⛔ 未找到UID为{target_uid}的玩家", event))
                return

            lines = [
                f"💕 好感度查询",
                "━━━━━━━━━━━━━",
                f"对象: {target.nickname}[UID:{target_uid}]",
                f"好感度: {favorability}",
                f"关系: {relation_desc}",
                "",
                "💡 提示:",
                "• 师徒需要40好感度",
                "• 结义需要60好感度",
                "• 结婚需要80好感度",
                "• 使用【赠礼 UID 礼物名】赠送礼物增加好感度"
            ]

            await favorability_cmd.finish(message_add_head("\n".join(lines), event))


# ==================== 脱离师门（徒弟叛师，有惩罚） ====================
betray_cmd = on_command("脱离师门", priority=5, block=True)

@betray_cmd.handle()
async def handle_betray_master(event: MessageEvent):
    """徒弟主动脱离师门（扣属性+7天冷却）"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await betray_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        from .mentorship_system_service import MentorshipSystemService
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository

        service = MentorshipSystemService(
            player_repo=PlayerRepository(uow.session),
            relationship_repo=PlayerRelationshipRepository(uow.session),
            session=uow.session
        )

        success, message = await service.betray_master(player.id)

        if success:
            await uow.commit()

        await betray_cmd.finish(message_add_head(message, event))


# ==================== 逐出师门（师父驱逐徒弟，有冷却） ====================
expel_cmd = on_command("逐出师门", priority=5, block=True)

@expel_cmd.handle()
async def handle_expel_apprentice(event: MessageEvent, args: Message = CommandArg()):
    """师父逐出指定徒弟（3天冷却）"""
    uid_text = args.extract_plain_text().strip()
    if not uid_text:
        await expel_cmd.finish(message_add_head("⛔ 用法：逐出师门 <徒弟UID>", event))

    try:
        target_uid = int(uid_text)
    except ValueError:
        await expel_cmd.finish(message_add_head("⛔ UID必须是数字", event))

    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await expel_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        from .mentorship_system_service import MentorshipSystemService
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository

        service = MentorshipSystemService(
            player_repo=PlayerRepository(uow.session),
            relationship_repo=PlayerRelationshipRepository(uow.session),
            session=uow.session
        )

        success, message = await service.expel_apprentice(player.id, target_uid)

        if success:
            await uow.commit()

        await expel_cmd.finish(message_add_head(message, event))


# ==================== 师徒信息查询 ====================
mentorship_info_cmd = on_command("师徒信息", aliases={"师徒状况", "查看师徒"}, priority=5, block=True)

@mentorship_info_cmd.handle()
async def handle_mentorship_info(event: MessageEvent):
    """查看师徒信息"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await mentorship_info_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        from .mentorship_system_service import MentorshipSystemService
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.player_relationship_repository import PlayerRelationshipRepository

        player_repo = PlayerRepository(uow.session)
        relationship_repo = PlayerRelationshipRepository(uow.session)
        service = MentorshipSystemService(player_repo, relationship_repo, uow.session)

        info_msg = await service.get_mentorship_info(player.id)
        await mentorship_info_cmd.finish(message_add_head(info_msg, event))


# ==================== 婚姻信息查询 ====================
marriage_info_cmd = on_command("婚姻信息", aliases={"婚姻状况", "查看婚姻"}, priority=5, block=True)

@marriage_info_cmd.handle()
async def handle_marriage_info(event: MessageEvent):
    """查看婚姻信息"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await marriage_info_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        # 查询婚姻关系
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player.id,
                    PlayerRelationship.target_id == player.id
                ),
                PlayerRelationship.relationship_type == RelationshipType.MARRIAGE.value
            )
        )
        result = await uow.session.execute(stmt)
        marriage = result.scalar_one_or_none()

        if not marriage:
            msg = """💕 你的婚姻状况
━━━━━━━━━━━━━
当前状态: 单身
💡 前往上京(0,0)找月老，使用【交互 月老 结婚 UID】与心爱的人结为夫妻"""
        else:
            # 获取配偶信息
            spouse_id = marriage.target_id if marriage.player_id == player.id else marriage.player_id
            spouse = await uow.players.get_by_id(spouse_id)
            spouse_name = spouse.nickname if spouse else "未知"

            msg = f"""💕 你的婚姻状况
━━━━━━━━━━━━━
当前状态: 已婚
配偶: {spouse_name}
💡 愿你们白头偕老,永结同心！
💔 如需解除关系,请前往上京(0,0)找月老使用【交互 月老 离婚】(需支付10万金币)"""

        await marriage_info_cmd.finish(message_add_head(msg, event))


# ==================== 结义信息查询 ====================
sworn_info_cmd = on_command("结义信息", aliases={"结义状况", "查看结义"}, priority=5, block=True)

@sworn_info_cmd.handle()
async def handle_sworn_info(event: MessageEvent):
    """查看结义信息"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await sworn_info_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        # 查询所有结义关系
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player.id,
                    PlayerRelationship.target_id == player.id
                ),
                PlayerRelationship.relationship_type == RelationshipType.SWORN.value
            )
        )
        result = await uow.session.execute(stmt)
        relationships = result.scalars().all()

        if not relationships:
            msg = """🤝 你的结义状况
━━━━━━━━━━━━━
当前状态: 无结义关系
💡 前往上京(0,0)找结义使者，使用【交互 结义使者 结义 UID1 UID2...】与兄弟结义"""
        else:
            # 获取所有结义兄弟
            brothers = []
            for rel in relationships:
                brother_id = rel.target_id if rel.player_id == player.id else rel.player_id
                brother = await uow.players.get_by_id(brother_id)
                if brother:
                    brothers.append(brother.nickname)

            brothers_list = "、".join(brothers)

            msg = f"""🤝 你的结义状况
━━━━━━━━━━━━━
当前状态: 已结义
结义兄弟: {brothers_list}
兄弟人数: {len(brothers)}人
━━━━━━━━━━━━━
江湖义气，生死与共！
💔 如需解除关系,请前往上京(0,0)找结义使者使用【交互 结义使者 断义】"""

        await sworn_info_cmd.finish(message_add_head(msg, event))
