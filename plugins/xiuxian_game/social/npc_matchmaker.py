"""
月老NPC交互处理器

处理玩家与月老的交互,提供结婚功能
"""
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..utils import message_add_head
from .relationship_service import RelationshipService
from ..models.player_relationship import RelationshipType


async def handle_matchmaker_interaction(
    session: AsyncSession,
    player: Player,
    npc,
    event: MessageEvent,
    dialogue_content: str = ""
):
    """
    处理与月老的交互

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
        return get_matchmaker_menu()

    # 查询婚姻状况
    elif dialogue_content in ["查询", "状况", "婚姻状况"]:
        return await check_marriage_status(player, uow)

    # ==================== 新：求婚申请流程 ====================

    # 求婚 - 发起求婚申请
    elif dialogue_content.startswith("求婚 "):
        try:
            target_uid = int(dialogue_content.split()[1])
            success, message = await service.submit_marriage_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：求婚 UID\n示例：求婚 123"

    # 求婚申请 - 查看收到的求婚申请
    elif dialogue_content in ["求婚申请", "申请列表"]:
        proposals = await service.get_marriage_proposals(player.id)

        if not proposals:
            return "💌 当前没有收到求婚申请"

        lines = ["💌 收到的求婚申请", "━━━━━━━━━━━━━"]
        for i, prop in enumerate(proposals, 1):
            time_str = prop["request_time"].strftime("%m月%d日 %H:%M")
            lines.append(f"{i}. 【{prop['proposer_name']}】(UID: {prop['proposer_uid']})")
            lines.append(f"   申请时间: {time_str}")
            lines.append(f"   ❤️ 同意求婚 {prop['proposer_uid']}")
            lines.append(f"   💔 拒绝求婚 {prop['proposer_uid']}")
            lines.append("")

        lines.append("━━━━━━━━━━━━━")
        lines.append("💡 使用【同意求婚 UID】或【拒绝求婚 UID】处理申请")

        return "\n".join(lines)

    # 同意求婚
    elif dialogue_content.startswith("同意求婚 ") or dialogue_content.startswith("同意 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])  # 取最后一个参数作为UID

            success, message = await service.approve_marriage_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：同意求婚 UID\n示例：同意求婚 123"

    # 拒绝求婚
    elif dialogue_content.startswith("拒绝求婚 ") or dialogue_content.startswith("拒绝 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.reject_marriage_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：拒绝求婚 UID\n示例：拒绝求婚 123"

    # 撤销求婚
    elif dialogue_content.startswith("撤销求婚 ") or dialogue_content.startswith("撤销 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.cancel_marriage_proposal(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：撤销求婚 UID\n示例：撤销求婚 123"

    # ==================== 旧：直接结婚(已弃用,保留兼容性) ====================

    # 结婚 - 直接建立婚姻(已改为需要双向确认)
    elif dialogue_content.startswith("结婚 "):
        return "💡 现已改为求婚申请机制！\n请使用【求婚 UID】向对方发起求婚申请\n对方同意后即可结为夫妻"

    # 离婚
    elif dialogue_content in ["离婚", "解除婚姻"]:
        success, message = await service.divorce(player.id, cost=100000)

        if success:
            await uow.commit()

        return message

    # 默认返回帮助
    else:
        return get_matchmaker_menu()


def get_matchmaker_menu() -> str:
    """获取月老菜单"""
    return """💒 月老的红线姻缘
━━━━━━━━━━━━━
我是月老，掌管天下姻缘。有情人终成眷属，需双方同意方可成婚。

【功能列表】
💕 求婚 UID - 向心爱的人发起求婚申请
  • 需要双方好感度达到5000
  • 双方必须在同一地点
  • 对方同意后才能成为夫妻

💌 求婚申请 - 查看收到的求婚申请列表
❤️ 同意求婚 UID - 同意对方的求婚申请
💔 拒绝求婚 UID - 拒绝对方的求婚申请
🔄 撤销求婚 UID - 撤销自己发起的求婚申请

📊 查询 - 查看当前婚姻状况
💡 帮助 - 显示此菜单

【注意事项】
• 求婚申请7天未处理将自动过期
• 被拒绝后需等待24小时才能再次申请
• 使用【赠礼 UID 礼物名】赠送礼物增加好感度

【解除关系】
💔 离婚 - 单方面离婚(需支付10万金币)
━━━━━━━━━━━━━
今世良缘，月老牵线，祝天下有情人终成眷属！"""


async def check_marriage_status(player: Player, uow: UnitOfWork) -> str:
    """查询婚姻状况"""
    from sqlalchemy import select, and_, or_
    from ..models.player_relationship import PlayerRelationship

    # 查询婚姻关系 - 查找player参与的任一婚姻关系
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
        return """💕 你的婚姻状况
━━━━━━━━━━━━━
当前状态: 单身
💡 你可以使用【求婚 UID】向心爱的人发起求婚申请
💌 使用【求婚申请】查看收到的申请
"""

    # 获取配偶信息
    spouse_id = marriage.target_id if marriage.player_id == player.id else marriage.player_id
    spouse = await uow.players.get_by_id(spouse_id)

    spouse_name = spouse.nickname if spouse else "未知"

    return f"""💕 你的婚姻状况
━━━━━━━━━━━━━
当前状态: 已婚
配偶: {spouse_name}
💡 愿你们白头偕老,永结同心！
💔 如需解除关系,请使用【交互 月老 离婚】(需支付10万金币)
"""
