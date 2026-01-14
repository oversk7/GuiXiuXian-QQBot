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
  • 每两人之间需要5000好感度
  • 所有人必须在上京(0,0)
  • 建立后成为结义兄弟

📊 查询 - 查看当前结义状况
💡 帮助 - 显示此菜单

【好感度提示】
• 结义需要5000好感度
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
