"""
跨平台工具模块
提供消息来源识别和统一的玩家数据访问接口
"""
from typing import Optional, Tuple
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession
from .models.player import Player
from .infrastructure.repositories.player_repository import PlayerRepository


class PlatformType:
    """平台类型常量"""
    GROUP = "group"      # 群聊
    GUILD = "guild"      # 频道
    FRIEND = "friend"    # 私聊


def get_platform_info(event: MessageEvent) -> Tuple[str, str]:
    """
    获取平台信息
    
    Args:
        event: 消息事件
        
    Returns:
        Tuple[平台类型, 用户ID]
    """
    session_id = event.get_session_id()
    user_id = event.get_user_id()
    
    if session_id.startswith("guild_"):
        return PlatformType.GUILD, user_id
    elif session_id.startswith("group_"):
        return PlatformType.GROUP, user_id
    elif session_id.startswith("friend_"):
        return PlatformType.FRIEND, user_id
    else:
        # 默认按群聊处理
        return PlatformType.GROUP, user_id


def is_guild_message(event: MessageEvent) -> bool:
    """判断是否为频道消息"""
    platform_type, _ = get_platform_info(event)
    return platform_type == PlatformType.GUILD


def is_group_message(event: MessageEvent) -> bool:
    """判断是否为群聊消息"""
    platform_type, _ = get_platform_info(event)
    return platform_type == PlatformType.GROUP


def is_private_message(event: MessageEvent) -> bool:
    """判断是否为私聊消息"""
    platform_type, _ = get_platform_info(event)
    return platform_type == PlatformType.FRIEND


async def get_unified_player(session: AsyncSession, event: MessageEvent) -> Optional[Player]:
    """
    获取统一的玩家数据

    支持账号切换功能：
    1. 优先查询当前激活的账号（通过 AccountOwnership.is_active）
    2. 如果未找到激活账号（无账号切换记录），回退到直接查询 Player

    Args:
        session: 数据库会话
        event: 消息事件

    Returns:
        Player对象或None
    """
    _, user_id = get_platform_info(event)

    # 使用 PlayerRepository 查询激活的账号
    player_repo = PlayerRepository(session)
    player = await player_repo.get_active_by_platform_id(user_id)

    # 如果没有激活账号记录（用户未使用账号切换系统），回退到直接查询
    if player is None:
        player = await session.get(Player, user_id)

    return player




def format_platform_message(content: str, event: MessageEvent) -> str:
    """
    根据平台类型格式化消息
    
    Args:
        content: 消息内容
        event: 消息事件
        
    Returns:
        格式化后的消息
    """
    platform_type, _ = get_platform_info(event)
    
    if platform_type == PlatformType.GUILD:
        # 频道消息添加特殊标识
        return f"🏛️ 频道模式\n{content}"
    elif platform_type == PlatformType.GROUP:
        # 群聊消息保持原样
        return content
    else:
        # 私聊消息添加标识
        return f"💬 私聊模式\n{content}"
