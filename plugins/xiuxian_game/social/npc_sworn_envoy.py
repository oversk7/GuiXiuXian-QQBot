"""
结义使者NPC交互处理器

处理玩家与结义使者的交互,提供结义功能
"""
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..utils import message_add_head
from .relationship_service import RelationshipService
from ..models.player_relationship import RelationshipType


async def handle_sworn_envoy_interaction(
    session: AsyncSession,
    player: Player,
    npc,
    event: MessageEvent,
    dialogue_content: str = ""
):
    """
    处理与结义使者的交互

    Args:
        session: 数据库会话
        player: 玩家对象
        npc: NPC对象
        event: 消息事件
        dialogue_content: 对话内容
    """
    dialogue_content = dialogue_content.strip().lower()

    # 创建UnitOfWork,使用传入的session
    from ..infrastructure.uow.unit_of_work import UnitOfWork
    uow = UnitOfWork(lambda: session)
    uow._session = session

    service = RelationshipService(
        player_repo=uow.players,
        relationship_repo=uow.player_relationships,
        item_repo=uow.items,
        uow=uow
    )

    # 显示菜单
    if not dialogue_content or dialogue_content in ["菜单", "帮助"]:
        return get_sworn_menu()

    # 查询结义状况
    elif dialogue_content in ["查询", "状况", "结义状况"]:
        return await check_sworn_status(player, uow)

    # ==================== 结义申请流程(2人) ====================

    # 结义(判断2人或多人)
    elif dialogue_content.startswith("结义 "):
        try:
            # 解析UID列表
            uid_strs = dialogue_content.split()[1:]
            target_uids = [int(uid) for uid in uid_strs]

            # 2人结义: 发起申请,需要对方同意
            if len(target_uids) == 1:
                success, message = await service.submit_sworn_proposal(player.id, target_uids[0])
            # 3-4人结义: 直接建立(保持原逻辑,所有人必须在场)
            else:
                success, message = await service.establish_sworn(player.id, target_uids)

            if success:
                await uow.commit()

            return message
        except ValueError:
            return "⛔ 格式错误，正确格式：\n• 2人结义: 结义 UID\n• 多人结义: 结义 UID1 UID2...\n示例：结义 123 或 结义 123 456"

    # 结义申请 - 查看收到的结义申请
    elif dialogue_content in ["结义申请", "申请列表"]:
        proposals = await service.get_sworn_proposals(player.id)

        if not proposals:
            return "🤝 当前没有收到结义申请"

        lines = ["🤝 收到的结义申请", "━━━━━━━━━━━━━"]
        for i, prop in enumerate(proposals, 1):
            time_str = prop["request_time"].strftime("%m月%d日 %H:%M")
            lines.append(f"{i}. 【{prop['proposer_name']}】(UID: {prop['proposer_uid']})")
            lines.append(f"   申请时间: {time_str}")
            lines.append(f"   ❤️ 同意结义 {prop['proposer_uid']}")
            lines.append(f"   💔 拒绝结义 {prop['proposer_uid']}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【同意结义 UID】或【拒绝结义 UID】处理申请")

        return "\n".join(lines)

    # 同意结义
    elif dialogue_content.startswith("同意结义 ") or dialogue_content.startswith("同意 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])  # 取最后一个参数作为UID

            success, message = await service.approve_sworn_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：同意结义 UID\n示例：同意结义 123"

    # 拒绝结义
    elif dialogue_content.startswith("拒绝结义 ") or dialogue_content.startswith("拒绝 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.reject_sworn_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：拒绝结义 UID\n示例：拒绝结义 123"

    # 撤销结义
    elif dialogue_content.startswith("撤销结义 ") or dialogue_content.startswith("撤销 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.cancel_sworn_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：撤销结义 UID\n示例：撤销结义 123"

    # 断义
    elif dialogue_content in ["断义", "解除结义", "脱离结义"]:
        success, message = await service.break_sworn(player.id)

        if success:
            await uow.commit()

        return message

    # 默认返回帮助
    else:
        return get_sworn_menu()


def get_sworn_menu() -> str:
    """获取结义使者菜单"""
    return """🤝 结义使者的义气见证
━━━━━━━━━━━━━
我是结义使者，见证江湖英雄豪杰的结义之情。
有福同享，有难同当，这才是真正的兄弟情义！

【功能列表】
🤝 结义 UID - 向兄弟发起2人结义申请(需对方同意)
  • 需要双方好感度达到5000
  • 双方必须在同一地点
  • 对方同意后才能成为结义兄弟

🤝 结义 UID1 UID2... - 3-4人结义(所有人必须在场)
  • 支持3-4人同时结义
  • 每两人之间需要5000好感度
  • 所有人必须在同一地点
  • 立即建立结义关系

🤝 结义申请 - 查看收到的结义申请列表
❤️ 同意结义 UID - 同意对方的结义申请
💔 拒绝结义 UID - 拒绝对方的结义申请
🔄 撤销结义 UID - 撤销自己发起的结义申请

📊 查询 - 查看当前结义状况
💡 帮助 - 显示此菜单

【注意事项】
• 2人结义申请7天未处理将自动过期
• 被拒绝后需等待24小时才能再次申请
• 使用【赠礼 UID 礼物名】赠送礼物增加好感度

【解除关系】
💔 断义 - 解除所有结义关系
━━━━━━━━━━━━━
桃李春风一杯酒，江湖夜雨十年灯！
愿你们的兄弟情义天长地久！"""


async def check_sworn_status(player, uow: UnitOfWork) -> str:
    """查询结义状况"""
    from sqlalchemy import select, and_, or_
    from ..models.player_relationship import PlayerRelationship

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
        return """🤝 你的结义状况
━━━━━━━━━━━━━
当前状态: 无结义关系
💡 2人结义: 【结义 UID】发起申请,对方同意后成立
💡 多人结义: 【结义 UID1 UID2...】所有人在场立即成立
🤝 使用【结义申请】查看收到的申请
"""

    # 获取所有结义兄弟
    brothers = []
    for rel in relationships:
        brother_id = rel.target_id if rel.player_id == player.id else rel.player_id
        brother = await uow.players.get_by_id(brother_id)
        if brother:
            brothers.append(brother.nickname)

    brothers_list = "、".join(brothers)

    return f"""🤝 你的结义状况
━━━━━━━━━━━━━
当前状态: 已结义
结义兄弟: {brothers_list}
兄弟人数: {len(brothers)}人
━━━━━━━━━━━━━
江湖义气，生死与共！
💔 如需解除关系,请使用【交互 结义使者 断义】
"""
