"""
全局封禁拦截器
在所有命令处理之前检查玩家是否被封禁
"""
from datetime import datetime
from nonebot import on_message
from nonebot.message import event_preprocessor
from nonebot.adapters.qq import MessageEvent
from nonebot.exception import IgnoredException
from sqlalchemy import select

from .models.db import safe_session
from .models.player_ban import PlayerBan
from .ai_guide import is_admin


async def check_player_ban(user_id: str) -> tuple[bool, str | None]:
    """
    检查玩家是否被全局封禁

    Returns:
        (is_banned, ban_info): 是否被封禁，封禁信息
    """
    async with safe_session() as session:
        stmt = select(PlayerBan).where(
            PlayerBan.player_id == user_id,
            PlayerBan.is_active == True
        )
        record = (await session.execute(stmt)).scalars().first()

        if not record:
            return False, None

        # 检查是否过期
        if record.is_expired():
            # 自动解封
            record.is_active = False
            await session.commit()
            return False, None

        # 在 session context 内部提取所有需要的信息，避免在 context 外部访问数据库对象
        ban_info = record.get_ban_info()

    # 在 session context 外部返回结果，确保连接已正确关闭
    return True, ban_info


@event_preprocessor
async def ban_checker(event: MessageEvent):
    """
    全局封禁检查器 - 在所有命令处理之前执行

    如果玩家被封禁，则阻止所有游戏命令的执行
    """
    user_id = event.get_user_id()

    # 管理员不受封禁限制
    if is_admin(user_id):
        return

    # 检查是否被封禁
    # 注意：这里必须确保 check_player_ban 完全执行完毕（包括关闭数据库连接）
    # 然后再抛出异常，避免连接泄漏
    try:
        is_banned, ban_info = await check_player_ban(user_id)
    except Exception as e:
        # 如果检查过程出错，记录日志但不阻止用户操作
        from nonebot import logger
        logger.error(f"[BanChecker] 检查封禁状态失败: {e}")
        return

    if is_banned:
        # 如果被封禁，阻止事件继续传播
        # 这里不发送提示消息，避免被封禁玩家刷屏
        # 管理员可以通过【封禁列表】查看所有被封禁的玩家
        raise IgnoredException("用户已被封禁")
