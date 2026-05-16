"""
主动 C2C 私信通知工具

用法: await notify_player(player_id, "消息内容", session)
所有错误静默处理，不影响调用方主流程。
"""
from nonebot import get_bot, logger
from nonebot.adapters.qq import Bot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models.account_ownership import AccountOwnership


async def notify_player(player_id: str, message: str, session: AsyncSession | None = None) -> bool:
    """向指定玩家发送 C2C 主动私信。

    Args:
        player_id: 游戏玩家 ID
        message: 通知内容（纯文本）
        session: 可选数据库会话；为 None 时自行创建

    Returns:
        发送是否成功
    """
    try:
        platform_id = await _get_platform_id(player_id, session)
        bot: Bot = get_bot()
        await bot.send_to_c2c(openid=platform_id, message=message)
        return True
    except Exception as e:
        logger.warning(f"[Notify] C2C 通知失败 player={player_id}: {e}")
        return False


async def _get_platform_id(player_id: str, session: AsyncSession | None) -> str:
    """查 AccountOwnership 获取 owner_platform_id，兜底用 player_id。"""
    if session is None:
        from .models.db import AsyncSessionLocal
        async with AsyncSessionLocal() as s:
            return await _get_platform_id(player_id, s)

    result = await session.execute(
        select(AccountOwnership.owner_platform_id)
        .where(
            AccountOwnership.player_id == player_id,
            AccountOwnership.is_active.is_(True),
        )
        .limit(1)
    )
    return result.scalar() or player_id
