"""
升级钩子系统 - 在玩家升级时触发社交系统相关更新
"""
from sqlalchemy.ext.asyncio import AsyncSession
from .mentorship_service import MentorshipService


async def on_player_level_up(session: AsyncSession, player_id: str, old_level: int, new_level: int):
    """
    玩家升级时的钩子函数
    
    Args:
        session: 数据库会话
        player_id: 玩家ID
        old_level: 升级前等级
        new_level: 升级后等级
    """
    level_increase = new_level - old_level
    if level_increase > 0:
        # 更新师父的恩师点
        await MentorshipService.update_mentor_points(session, player_id, level_increase)
