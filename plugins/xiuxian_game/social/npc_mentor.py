"""
师徒使者NPC交互处理器（新版-拜师申请流程）

处理玩家与师徒使者的交互,提供拜师申请/收徒/出师等功能
"""
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta

from ..models.player import Player
from ..infrastructure.uow.unit_of_work import UnitOfWork
from .mentorship_system_service import MentorshipSystemService


async def handle_mentor_interaction(
    session: AsyncSession,
    player: Player,
    npc,
    event: MessageEvent,
    dialogue_content: str = ""
):
    """
    处理与师徒使者的交互（拜师申请流程）

    Args:
        session: 数据库会话
        player: 玩家对象
        npc: NPC对象
        event: 消息事件
        dialogue_content: 对话内容
    """
    dialogue_content = dialogue_content.strip().lower()

    # 创建UnitOfWork,使用传入的session
    uow = UnitOfWork(lambda: session)
    uow._session = session

    service = MentorshipSystemService(
        player_repo=uow.players,
        relationship_repo=uow.player_relationships,
        session=session
    )

    # 显示菜单
    if not dialogue_content or dialogue_content in ["菜单", "帮助"]:
        return get_mentor_menu(player)

    # 查询师徒状况
    elif dialogue_content in ["查询", "状况", "师徒状况", "师徒信息"]:
        return await service.get_mentorship_info(player.id)

    # ==================== 新：拜师申请流程 ====================

    # 拜师 - 徒弟发起申请
    elif dialogue_content.startswith("拜师 "):
        try:
            target_uid = int(dialogue_content.split()[1])
            success, message = await service.submit_mentorship_request(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：拜师 UID\n示例：拜师 123"

    # 拜师申请 / 拜师申请列表 - 查看收到的申请
    elif dialogue_content in ["拜师申请", "拜师申请列表", "申请列表"]:
        requests = await service.get_pending_requests(player.id)

        if not requests:
            return "你暂时没有收到拜师申请"

        lines = [
            "📋 拜师申请列表",
            "━━━━━━━━━━━━━"
        ]

        for i, (apprentice, rel) in enumerate(requests, 1):
            # 计算申请时间
            time_ago = ""
            if rel.mentorship_request_time:
                delta = datetime.now() - rel.mentorship_request_time
                if delta.days > 0:
                    time_ago = f"{delta.days}天前"
                elif delta.seconds >= 3600:
                    time_ago = f"{delta.seconds // 3600}小时前"
                else:
                    time_ago = f"{delta.seconds // 60}分钟前"

            lines.append(
                f"{i}. 【{apprentice.nickname}】(UID: {apprentice.uid})\n"
                f"   等级: Lv.{apprentice.level} | {time_ago}"
            )

        lines.extend([
            "━━━━━━━━━━━━━",
            "💡 使用【交互 师徒使者 同意拜师 UID】接受申请",
            "💡 使用【交互 师徒使者 拒绝拜师 UID】拒绝申请"
        ])

        return "\n".join(lines)

    # 同意拜师 - 师父同意申请
    elif dialogue_content.startswith("同意拜师 ") or dialogue_content.startswith("同意 "):
        try:
            # 支持两种格式：同意拜师 123 或 同意 123
            parts = dialogue_content.split()
            target_uid = int(parts[-1])  # 取最后一个参数作为UID

            success, message = await service.approve_mentorship_request(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：同意拜师 UID\n示例：同意拜师 123"

    # 拒绝拜师 - 师父拒绝申请
    elif dialogue_content.startswith("拒绝拜师 ") or dialogue_content.startswith("拒绝 "):
        try:
            # 支持两种格式：拒绝拜师 123 或 拒绝 123
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.reject_mentorship_request(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：拒绝拜师 UID\n示例：拒绝拜师 123"

    # 撤销拜师 - 徒弟撤销申请
    elif dialogue_content.startswith("撤销拜师 ") or dialogue_content.startswith("撤销 "):
        try:
            parts = dialogue_content.split()
            target_uid = int(parts[-1])

            success, message = await service.cancel_mentorship_request(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：撤销拜师 UID\n示例：撤销拜师 123"

    # ==================== 保留原有功能 ====================

    # 出师
    elif dialogue_content.startswith("出师 "):
        try:
            target_uid = int(dialogue_content.split()[1])
            success, message = await service.graduate_apprentice(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：出师 UID\n示例：出师 123"

    # 逐出
    elif dialogue_content.startswith("逐出 "):
        try:
            target_uid = int(dialogue_content.split()[1])
            success, message = await service.expel_apprentice(player.id, target_uid)

            if success:
                await uow.commit()

            return message
        except (ValueError, IndexError):
            return "格式错误，正确格式：逐出 UID\n示例：逐出 123"

    # 叛师
    elif dialogue_content in ["叛师", "脱离师门"]:
        success, message = await service.betray_master(player.id)

        if success:
            await uow.commit()

        return message

    # 购买徒弟位
    elif dialogue_content in ["购买徒弟位", "买徒弟位", "扩展徒弟位"]:
        success, message = await service.purchase_apprentice_slot(player.id)

        if success:
            await uow.commit()

        return message

    # 香火商店
    elif dialogue_content in ["香火商店", "商店"]:
        return get_incense_shop_menu(player)

    # 默认返回帮助
    else:
        return get_mentor_menu(player)


def get_mentor_menu(player: Player) -> str:
    """获取师徒使者菜单"""
    incense = player.incense or 0
    max_slots = player.max_apprentice_slots or 3

    return f"""师徒使者的传承之道
━━━━━━━━━━━━━
我是师徒使者，见证修仙者的传承之情。
师徒如父子，传道授业解惑，香火相传！

【你的香火】{incense} | 徒弟位：{max_slots}

【新：拜师申请流程】
拜师 UID - 向某玩家发起拜师申请
  • 徒弟主动发起，师父确认
  • 对方需境界高于你50级或转数更高

拜师申请 - 查看收到的拜师申请列表
  • 显示所有待处理的申请

同意拜师 UID - 同意某人的拜师申请
  • 建立师徒关系

拒绝拜师 UID - 拒绝某人的拜师申请
  • 对方24小时内不能再次申请

撤销拜师 UID - 撤销自己发出的申请

【师父功能】
出师 UID - 让徒弟正常出师
  • 师徒关系解除
  • 双方进入3天冷却期

逐出 UID - 将徒弟逐出师门
  • 师徒关系解除
  • 双方进入3天冷却期

【徒弟功能】
叛师 - 主动叛离师门
  • 损失10-20%属性
  • 师父损失你贡献香火的50%
  • 双方进入7天冷却期

【其他】
查询 - 查看师徒状况
香火商店 - 查看香火兑换
购买徒弟位 - 花费500香火扩展1个徒弟位
帮助 - 显示此菜单

【香火获取】
徒弟每次升级，师父获得香火奖励
香火 = 升级所需经验 / 5000（向上取整）
⚠️ 徒弟一转后升级不再贡献香火

【注意事项】
• 徒弟需注册满24小时才能拜师
• 每收一个徒弟，修炼效率-1%
• 徒弟一转后应考虑让其出师
• 拜师申请7天后自动过期
━━━━━━━━━━━━━
师恩如海，传承不息！"""


def get_incense_shop_menu(player: Player) -> str:
    """获取香火商店菜单"""
    incense = player.incense or 0

    return f"""香火商店
━━━━━━━━━━━━━
香火是师徒传承的见证，可兑换珍稀物品。

【你的香火】{incense}

【兑换列表】
购买徒弟位 - 500香火
  • 永久增加1个徒弟位

【更多兑换】
敬请期待...

━━━━━━━━━━━━━
积善成德，香火绵延！"""
