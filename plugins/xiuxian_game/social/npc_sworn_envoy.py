"""
结义使者NPC交互处理器

处理玩家与结义使者的交互,提供结义功能
"""
from nonebot.adapters.qq import MessageEvent

from ..infrastructure.uow.unit_of_work import UnitOfWork
from ..models.db import AsyncSessionLocal
from ..utils import message_add_head
from ..platform_utils import get_unified_player
from .relationship_service import RelationshipService
from ..models.player_relationship import RelationshipType


async def handle_sworn_envoy_interaction(event: MessageEvent, dialogue_content: str = ""):
    """
    处理与结义使者的交互

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
            return get_sworn_menu()

        # 查询结义状况
        elif dialogue_content in ["查询", "状况", "结义状况"]:
            return await check_sworn_status(player, uow)

        # 结义
        elif dialogue_content.startswith("结义 "):
            try:
                # 解析UID列表
                uid_strs = dialogue_content.split()[1:]
                target_uids = [int(uid) for uid in uid_strs]

                success, message = await service.establish_sworn(player.id, target_uids)

                if success:
                    await uow.commit()

                return message
            except ValueError:
                return "⛔ 格式错误，正确格式：结义 UID1 UID2...\n示例：结义 123 456"

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
🤝 结义 UID1 UID2... - 与兄弟结为异姓兄弟
  • 支持2-4人结义
  • 每两人之间需要60好感度
  • 所有人必须在上京(0,0)
  • 建立后成为结义兄弟

📊 查询 - 查看当前结义状况
💡 帮助 - 显示此菜单

【好感度提示】
• 师徒需要40好感度
• 结义需要60好感度
• 结婚需要80好感度
• 使用【赠礼 UID 礼物名】赠送礼物增加好感度

【解除关系】
💔 断义 - 解除所有结义关系
━━━━━━━━━━━━━
桃李春风一杯酒，江湖夜雨十年灯！
愿你们的兄弟情义天长地久！"""


async def check_sworn_status(player, uow: UnitOfWork) -> str:
    """查询结义状况"""
    from sqlalchemy import select, and_, or_

    # 查询所有结义关系
    stmt = select(uow.player_relationships.model).where(
        and_(
            or_(
                uow.player_relationships.model.player_id == player.id,
                uow.player_relationships.model.target_id == player.id
            ),
            uow.player_relationships.model.relationship_type == RelationshipType.SWORN.value
        )
    )
    result = await uow.session.execute(stmt)
    relationships = result.scalars().all()

    if not relationships:
        return """🤝 你的结义状况
━━━━━━━━━━━━━
当前状态: 无结义关系
💡 你可以使用【结义 UID1 UID2...】与兄弟结义
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
💔 如需解除关系,请使用【断义】命令
"""
