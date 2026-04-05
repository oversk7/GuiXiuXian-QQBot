"""
跨平台工具模块
提供消息来源识别和统一的玩家数据访问接口
"""
from typing import Optional, Tuple, Dict
from datetime import datetime
from nonebot.adapters.qq import MessageEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models.player import Player
from .models.account_ownership import AccountOwnership
from .infrastructure.repositories.player_repository import PlayerRepository
from .infrastructure.cache import player_identity_cache


# ==================== last_active_at 节流 ====================
# 60秒内不重复更新，减少不必要的 UPDATE
_ACTIVE_THROTTLE_SECONDS = 60


def _touch_last_active(player: Player) -> None:
    """更新 last_active_at，60秒内跳过以减少 DB 写入。"""
    now = datetime.now()
    if (player.last_active_at is None
            or (now - player.last_active_at).total_seconds() > _ACTIVE_THROTTLE_SECONDS):
        player.last_active_at = now


# ==================== 管理员临时切换功能 ====================
# 内存中维护管理员临时切换状态，格式: {admin_platform_id: player_id}
_admin_temp_switch: Dict[str, str] = {}


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



def is_private_message(event: MessageEvent) -> bool:
    """判断是否为私聊消息"""
    platform_type, _ = get_platform_info(event)
    return platform_type == PlatformType.FRIEND


async def get_unified_player(session: AsyncSession, event: MessageEvent) -> Optional[Player]:
    """
    获取统一的玩家数据

    支持账号切换功能：
    1. **优先检查管理员临时切换**：如果管理员正在临时切换到某个账号，返回该账号
    2. 查询当前激活的账号（通过 AccountOwnership.is_active）
    3. 如果未找到激活账号（无账号切换记录），回退到直接查询 Player

    Args:
        session: 数据库会话
        event: 消息事件

    Returns:
        Player对象或None
    """
    _, user_id = get_platform_info(event)

    # 1. 优先检查管理员临时切换（绕过缓存）
    if user_id in _admin_temp_switch:
        temp_player_id = _admin_temp_switch[user_id]
        temp_player = await session.get(Player, temp_player_id)
        if temp_player:
            await session.refresh(temp_player)
            return temp_player

    # 2. 查缓存：platform_id → player_id
    if player_identity_cache.has(user_id):
        cached_player_id = player_identity_cache.get(user_id)
        if cached_player_id is None:
            return None  # 缓存记录该用户无角色

        # 用 player_id 直接查 DB
        player = await session.get(Player, cached_player_id)
        if player is not None:
            _touch_last_active(player)
            return player
        # player 被删除了，缓存失效，走下面的完整查询
        player_identity_cache.invalidate(user_id)

    # 3. 缓存未命中：完整查询并回填缓存
    player_repo = PlayerRepository(session)
    player = await player_repo.get_active_by_platform_id(user_id)

    if player is None:
        # 回退：直接用 platform_id 查 Player（无 ownership 记录的老玩家）
        player = await session.get(Player, user_id)
        if player is not None:
            stmt = select(AccountOwnership).where(
                AccountOwnership.player_id == player.id
            )
            result = await session.execute(stmt)
            ownership = result.scalars().first()
            if ownership and ownership.owner_platform_id != user_id:
                player = None

    # 回填身份缓存
    player_identity_cache.put(user_id, player.id if player else None)
    if player is not None:
        _touch_last_active(player)

    return player




def admin_temp_switch_to(admin_platform_id: str, target_player_id: str) -> None:
    """
    管理员临时切换到指定账号

    Args:
        admin_platform_id: 管理员平台ID
        target_player_id: 目标玩家ID
    """
    _admin_temp_switch[admin_platform_id] = target_player_id


def admin_exit_temp_switch(admin_platform_id: str) -> bool:
    """
    管理员退出临时切换

    Args:
        admin_platform_id: 管理员平台ID

    Returns:
        是否成功退出（如果不在临时切换状态返回False）
    """
    if admin_platform_id in _admin_temp_switch:
        del _admin_temp_switch[admin_platform_id]
        return True
    return False


def is_admin_temp_switching(admin_platform_id: str) -> bool:
    """
    检查管理员是否正在临时切换状态

    Args:
        admin_platform_id: 管理员平台ID

    Returns:
        是否在临时切换状态
    """
    return admin_platform_id in _admin_temp_switch


def get_admin_temp_switch_target(admin_platform_id: str) -> Optional[str]:
    """
    获取管理员当前临时切换的目标玩家ID

    Args:
        admin_platform_id: 管理员平台ID

    Returns:
        目标玩家ID，如果未在临时切换状态返回None
    """
    return _admin_temp_switch.get(admin_platform_id)


