"""主动群提醒工具。

用法: await notify_player(player_id, "消息内容", session)
所有错误静默处理，不影响调用方主流程。
"""
from nonebot import get_bot, logger
from nonebot.adapters.qq import Bot, MessageSegment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models.account_ownership import AccountOwnership
from .models.player import Player


async def notify_player(player_id: str, message: str, session: AsyncSession | None = None) -> bool:
    """向指定玩家最近活跃的 QQ 群发送 @ 提醒。

    Args:
        player_id: 游戏玩家 ID
        message: 通知内容（纯文本）
        session: 可选数据库会话；为 None 时自行创建

    Returns:
        发送是否成功
    """
    try:
        group_openid, member_openid, mention_user_id = await _get_group_notify_target(
            player_id, session
        )
        return await notify_group_member(
            group_openid, member_openid, message, mention_user_id=mention_user_id
        )
    except Exception as e:
        logger.warning(f"[Notify] 群提醒失败 player={player_id}: {e}")
        return False


async def notify_group_member(
    group_openid: str,
    member_openid: str,
    message: str,
    mention_user_id: str | None = None,
) -> bool:
    """向指定 QQ 群发送 @ 成员提醒（纯文本，不用 markdown）。"""
    try:
        bot: Bot = get_bot()
        notify_message = (
            MessageSegment.mention_user(mention_user_id or member_openid)
            + MessageSegment.text(f"\n{message}")
        )
        await bot.send_to_group(group_openid=group_openid, message=notify_message)
        return True
    except Exception as e:
        logger.warning(f"[Notify] 群提醒发送失败 group={group_openid} member={member_openid}: {e}")
        return False


async def _get_group_notify_target(
    player_id: str, session: AsyncSession | None
) -> tuple[str, str, str | None]:
    """查玩家最近群和 AccountOwnership，兜底用 player_id 作为 member_openid。"""
    if session is None:
        from .models.db import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await _get_group_notify_target(player_id, s)

    player = await session.get(Player, player_id)
    group_openid = getattr(player, "last_group_openid", None) if player else None
    mention_user_id = getattr(player, "last_group_member_id", None) if player else None
    if not group_openid:
        raise ValueError("玩家暂无可用的最近群记录")

    ownership_result = await session.execute(
        select(AccountOwnership.owner_platform_id)
        .where(
            AccountOwnership.player_id == player_id,
            AccountOwnership.is_active.is_(True),
        )
        .limit(1)
    )
    member_openid = ownership_result.scalar() or player_id
    return group_openid, member_openid, mention_user_id
