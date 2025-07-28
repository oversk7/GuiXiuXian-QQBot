from nonebot import on_message, logger
from nonebot.adapters.qq import MessageEvent
from .models.db import safe_session
from .models.player import Player

# 不阻拦也不回复，仅后台记录
log_uid_matcher = on_message(priority=1, block=False)

@log_uid_matcher.handle()
async def _(event: MessageEvent):
    """记录触发指令的玩家信息"""
    try:
        async with safe_session() as session:
            player = await session.get(Player, event.get_user_id())
        uid = player.uid if player else "未注册"
        nickname = player.nickname if player else "未注册"
        command = event.get_plaintext().strip() if event.get_plaintext().strip() else "未知指令"
        logger.info(f"UID:{uid} 昵称:{nickname} 指令:{command}")
    except Exception as e:
        logger.error(f"UID:未知 昵称:未知 指令:未知 状态:失败 错误:{str(e)}")