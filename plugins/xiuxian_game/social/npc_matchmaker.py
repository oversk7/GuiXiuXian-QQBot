"""
月老NPC交互处理器

处理玩家与月老的交互,提供结婚功能
"""
from nonebot.adapters.qq import MessageEvent

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .relationship_service import RelationshipService
from ..models.player_relationship import RelationshipType


async def handle_matchmaker_interaction(event: MessageEvent, dialogue_content: str = ""):
    """
    处理与月老的交互

    Args:
        event: 消息事件
        dialogue_content: 对话内容
    """
    player = await get_unified_player(event)
    if not player:
        return "⛔ 请先创建角色"

    dialogue_content = dialogue_content.strip().lower()

    async with UnitOfWork(AsyncSessionLocal) as uow:
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
  • 需要双方好感度达到80
  • 双方必须在上京(0,0)
  • 建立后成为夫妻关系

📊 查询 - 查看当前婚姻状况
💡 帮助 - 显示此菜单

【好感度提示】
• 师徒需要40好感度
• 结义需要60好感度
• 结婚需要80好感度
• 使用【赠礼 UID 礼物名】赠送礼物增加好感度

【解除关系】
💔 离婚 - 单方面离婚(需支付10万金币)
━━━━━━━━━━━━━
今世良缘，月老牵线，祝天下有情人终成眷属！"""


async def check_marriage_status(player, uow: UnitOfWork) -> str:
    """查询婚姻状况"""
    from sqlalchemy import select, and_, or_

    # 查询婚姻关系
    stmt = select(uow.player_relationships.model).where(
        and_(
            or_(
                uow.player_relationships.model.player_id == player.id,
                uow.player_relationships.model.target_id == player.id
            ),
            uow.player_relationships.model.relationship_type == RelationshipType.MARRIAGE.value
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
结婚时间: {marriage.established_at.strftime('%Y-%m-%d') if marriage.established_at else '未知'}
━━━━━━━━━━━━━
愿你们白头偕老,永结同心！
💔 如需解除关系,请使用【离婚】命令(需支付10万金币)
"""
