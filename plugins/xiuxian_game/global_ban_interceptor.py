"""
全局封禁拦截器
在所有命令处理之前检查玩家是否被封禁
"""
from nonebot import logger
from nonebot.adapters.qq import Event, MessageEvent
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from .ai_guide import is_admin
from .infrastructure.repositories.player_repository import PlayerRepository
from .models.db import safe_session
from .models.player import Player
from .models.player_ban import PlayerBan

# 被封禁用户仍可查看的指令（只看不能说）
_VIEW_ONLY_COMMANDS = {"消息", "留言板"}


def _extract_command_token(event: MessageEvent) -> str:
    """提取消息中的第一个命令词，用于判断是否为查看类指令。"""
    text = event.get_plaintext().strip()
    if text.startswith("/"):
        text = text[1:].lstrip()
    if not text:
        return ""
    return text.split(maxsplit=1)[0].strip()


async def _resolve_active_player_id(session, user_id: str) -> str | None:
    """将平台用户 ID 解析为当前激活角色的 player_id。

    PlayerBan 记录的是 Player.id（新注册玩家为 UUID，与 event.get_user_id()
    不同），所以这里必须走一遍账号所有权/老玩家回退解析。
    """
    player = await PlayerRepository(session).get_active_by_platform_id(user_id)
    if player is not None:
        return player.id

    # 兼容没有 account_ownership 记录的老玩家（Player.id 即平台 ID）
    legacy_player = await session.get(Player, user_id)
    return legacy_player.id if legacy_player is not None else None


async def check_player_ban(user_id: str) -> tuple[bool, str | None]:
    """
    检查玩家当前激活角色是否被全局封禁

    Returns:
        (is_banned, ban_info): 是否被封禁，封禁信息
    """
    async with safe_session() as session:
        player_id = await _resolve_active_player_id(session, user_id)
        if player_id is None:
            return False, None

        stmt = select(PlayerBan).where(
            PlayerBan.player_id == player_id,
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
async def ban_checker(event: Event):
    """
    全局封禁检查器 - 在所有命令处理之前执行

    如果玩家被封禁，则阻止所有游戏命令的执行
    """
    # 只处理 QQ 消息事件；其他事件（如通知、元事件）没有封禁检查必要
    if not isinstance(event, MessageEvent):
        return

    user_id = event.get_user_id()

    # 管理员不受封禁限制
    if is_admin(user_id):
        return

    # 检查是否被封禁
    # 注意：这里必须确保 check_player_ban 完全执行完毕（包括关闭数据库连接）
    # 然后再抛出异常，避免连接泄漏
    try:
        is_banned, _ = await check_player_ban(user_id)
    except SQLAlchemyError as e:
        # 如果检查过程出错，记录日志但不阻止用户操作
        logger.error(f"[BanChecker] 检查封禁状态失败: {e}")
        return

    if is_banned:
        # 放行查看消息类指令：被封禁用户只能看，不能发言
        command_token = _extract_command_token(event)
        if command_token in _VIEW_ONLY_COMMANDS:
            logger.debug(f"[BanChecker] 放行被封禁用户的查看指令: {command_token}")
            return

        # 其余指令全部阻止，避免被封禁玩家继续操作或发言
        # 这里不发送提示消息，避免被封禁玩家刷屏
        # 管理员可以通过【封禁列表】查看所有被封禁的玩家
        raise IgnoredException("用户已被封禁")
