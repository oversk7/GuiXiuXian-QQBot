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
                        rel_desc = "💒 夫妻"
                    elif rel.relationship_type == RelationshipType.SWORN.value:
                        rel_desc = "🤝 结义"
                    elif rel.relationship_type == RelationshipType.MENTORSHIP.value:
                        rel_desc = "🎓 师徒"
                    else:
                        rel_desc = f"{favorability} 好感"

                    lines.append(f"{other.nickname}[UID:{other.uid}] - {rel_desc}")

            lines.append("", "💡 使用【好感度 UID】查看详细信息")
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


# ==================== 离婚 ====================
divorce_cmd = on_command("离婚", priority=5, block=True)

@divorce_cmd.handle()
async def handle_divorce(event: MessageEvent):
    """离婚命令 - 单方面离婚,需要支付10万金币"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await divorce_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        service = RelationshipService(
            player_repo=uow.players,
            relationship_repo=uow.player_relationships,
            item_repo=uow.items,
            uow=uow
        )

        success, message = await service.divorce(player.id, cost=100000)

        if success:
            await uow.commit()

        await divorce_cmd.finish(message_add_head(message, event))


# ==================== 断义 ====================
break_sworn_cmd = on_command("断义", aliases={"脱离结义"}, priority=5, block=True)

@break_sworn_cmd.handle()
async def handle_break_sworn(event: MessageEvent):
    """断义命令 - 解除所有结义关系"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await break_sworn_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        service = RelationshipService(
            player_repo=uow.players,
            relationship_repo=uow.player_relationships,
            item_repo=uow.items,
            uow=uow
        )

        success, message = await service.break_sworn(player.id)

        if success:
            await uow.commit()

        await break_sworn_cmd.finish(message_add_head(message, event))


# ==================== 脱离师门/逐出师门 ====================
end_mentorship_cmd = on_command("脱离师门", aliases={"逐出师门"}, priority=5, block=True)

@end_mentorship_cmd.handle()
async def handle_end_mentorship(event: MessageEvent):
    """结束师徒关系命令"""
    async with UnitOfWork(AsyncSessionLocal) as uow:
        player = await get_unified_player(uow.session, event)
        if not player:
            await end_mentorship_cmd.finish(message_add_head("⛔ 请先创建角色", event))

        service = RelationshipService(
            player_repo=uow.players,
            relationship_repo=uow.player_relationships,
            item_repo=uow.items,
            uow=uow
        )

        success, message = await service.end_mentorship(player.id)

        if success:
            await uow.commit()

        await end_mentorship_cmd.finish(message_add_head(message, event))
