"""
跨平台工具模块
提供消息来源识别和统一的玩家数据访问接口
"""
from typing import Optional, Tuple
from nonebot.adapters.qq import MessageEvent
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .models.player import Player
from .models.platform_binding import PlatformBinding


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
    获取统一的玩家数据（支持跨平台绑定）
    
    Args:
        session: 数据库会话
        event: 消息事件
        
    Returns:
        Player对象或None
    """
    platform_type, user_id = get_platform_info(event)
    
    # 首先尝试直接查找玩家
    player = await session.get(Player, user_id)
    if player:
        return player
    
    # 如果是频道消息且没有找到玩家，尝试查找绑定关系
    if platform_type == PlatformType.GUILD:
        # 查找以当前频道用户ID为次平台ID的绑定关系
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.secondary_platform_id == user_id,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if binding:
            # 通过绑定关系找到主平台玩家
            player = await session.get(Player, binding.primary_platform_id)
            return player
    
    # 如果是群聊消息且没有找到玩家，尝试查找绑定关系
    elif platform_type == PlatformType.GROUP:
        # 查找以当前群聊用户ID为主平台ID的绑定关系
        binding_stmt = select(PlatformBinding).where(
            PlatformBinding.primary_platform_id == user_id,
            PlatformBinding.is_active == True
        )
        binding_result = await session.execute(binding_stmt)
        binding = binding_result.scalars().first()
        
        if binding:
            # 如果有绑定关系，返回主平台玩家（就是当前玩家）
            player = await session.get(Player, binding.primary_platform_id)
            return player
    
    return None


async def get_player_platform_display(session: AsyncSession, player: Player) -> str:
    """
    获取玩家的平台显示信息
    
    Args:
        session: 数据库会话
        player: 玩家对象
        
    Returns:
        平台显示字符串
    """
    # 查找是否有绑定关系
    binding_stmt = select(PlatformBinding).where(
        PlatformBinding.primary_platform_id == player.id,
        PlatformBinding.is_active == True
    )
    binding_result = await session.execute(binding_stmt)
    binding = binding_result.scalars().first()
    
    if binding:
        return "🔗 已绑定频道账号"
    else:
        return "📱 仅群聊账号"


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
