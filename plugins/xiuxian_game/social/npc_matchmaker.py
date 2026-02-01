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

    # 结婚
    elif dialogue_content.startswith("结婚 "):
        try:
            target_uid = int(dialogue_content.split()[1])
            success, message = await service.establish_marriage(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "⛔ 格式错误，正确格式：结婚 UID\n示例：结婚 123"

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
我是月老，掌管天下姻缘。有情人终成眷属，只需你们心意相通。

【功能列表】
💕 结婚 UID - 与心爱的人结为夫妻
  • 需要双方好感度达到5000
  • 双方必须在上京(0,0)
  • 建立后成为夫妻关系

📊 查询 - 查看当前婚姻状况
💡 帮助 - 显示此菜单

【好感度提示】
• 结婚需要5000好感度
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
💡 你可以使用【结婚 UID】与心爱的人结为夫妻
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
