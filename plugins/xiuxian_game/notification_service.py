"""主动通知工具，支持私聊优先、失败后回退群聊。

用法: await notify_player(player_id, "消息内容", session)
所有错误静默处理，不影响调用方主流程。
"""
from __future__ import annotations

from typing import Union

from nonebot import get_bot, logger
from nonebot.adapters.qq import Bot, Message, MessageSegment
from nonebot.adapters.qq.exception import ActionFailed, AuditException, NetworkError
from sqlalchemy.ext.asyncio import AsyncSession

from .models.player import Player


async def notify_player(
    player_id: str,
    message: str,
    session: AsyncSession | None = None,
    actual_mention: bool = False,
    *,
    markdown: bool = False,
    private_first: bool = False,
) -> bool:
    """向玩家发送提醒，可优先私聊并在失败后回退最近活跃群。

    Args:
        player_id: 游戏玩家 ID
        message: 通知内容
        session: 可选数据库会话；为 None 时自行创建
        actual_mention: 是否使用 QQ 真 @ 消息段
        markdown: 是否使用 QQ 原生 Markdown 渲染内容
        private_first: 是否优先发送私聊，失败后回退最近活跃群

    Returns:
        发送是否成功
    """
    try:
        from .utils_markdown import build_markdown

        render = build_markdown if markdown else MessageSegment.text
        if private_first:
            if session is None:
                from .models.db import safe_session
                async with safe_session() as s:
                    return await notify_player(
                        player_id, message, s, actual_mention,
                        markdown=markdown, private_first=True,
                    )
            player = await session.get(Player, player_id)
            openid = getattr(player, "last_group_member_id", None) or player_id
            if await _send_private_text(openid, render(message)):
                return True

        group_openid, nickname, mention_id = await _get_notification_target(player_id, session)
        if actual_mention and mention_id:
            msg = MessageSegment.mention_user(mention_id) + render(f" {message}")
        else:
            msg = render(f"@{nickname} {message}")
        return await _send_group_text(group_openid, msg)
    except Exception as e:
        logger.warning(f"[Notify] 群提醒失败 player={player_id}: {e}")
        return False


async def _send_private_text(
    openid: str, message: Union[str, Message, MessageSegment]
) -> bool:
    """发送 QQ 主动私信，不携带被动回复凭据。"""
    try:
        bot: Bot = get_bot()
        await bot.send_to_c2c(openid=openid, message=message)
        return True
    except (ValueError, ActionFailed, AuditException, NetworkError) as e:
        logger.warning(f"[Notify] 私聊提醒发送失败 user={openid}: {e}")
        return False


async def _send_group_text(
    group_openid: str, message: Union[str, Message, MessageSegment]
) -> bool:
    """向指定 QQ 群发送消息。"""
    try:
        bot: Bot = get_bot()
        await bot.send_to_group(group_openid=group_openid, message=message)
        return True
    except Exception as e:
        logger.warning(f"[Notify] 群提醒发送失败 group={group_openid}: {e}")
        return False


async def _get_notification_target(
    player_id: str, session: AsyncSession | None
) -> tuple[str, str, str | None]:
    """返回玩家最近活跃的 group_openid、昵称和群成员 ID。"""
    if session is None:
        from .models.db import safe_session
        async with safe_session() as s:
            return await _get_notification_target(player_id, s)

    player = await session.get(Player, player_id)
    group_openid = getattr(player, "last_group_openid", None) if player else None
    if not group_openid:
        raise ValueError("玩家暂无可用的最近群记录")
    mention_id = getattr(player, "last_group_member_id", None) or player_id
    nickname = (
        getattr(player, "last_group_username", None)
        or getattr(player, "nickname", None)
        or "道友"
    )
    return group_openid, nickname, mention_id
