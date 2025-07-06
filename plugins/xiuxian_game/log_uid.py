from nonebot import on_message, logger
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select

from .models.db import safe_session
from .models.player import Player

# 不阻拦也不回复，仅后台记录
log_uid_matcher = on_message(priority=1, block=False)

@log_uid_matcher.handle()
async def _(event: MessageEvent):
    """后台日志：输出玩家 UID 与内容，便于调试"""
    async with safe_session() as session:
        player = await session.get(Player, event.get_user_id())
    uid = player.uid if player else "未注册"
    logger.info(f"[MSG] UID:{uid} 昵称:{player.nickname if player else '未注册'}\n") 