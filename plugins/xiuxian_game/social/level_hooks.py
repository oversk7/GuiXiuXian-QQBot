"""
升级钩子系统 - 在玩家升级时触发社交系统相关更新
"""
from sqlalchemy.ext.asyncio import AsyncSession
from .mentorship_service import MentorshipService
from ..player.invite_reward_service import InviteRewardService
from ..player.feature_unlock import get_breakthrough_unlock_message

# ==================== Feature Flag ====================
# 设置为True使用新版DI架构的InviteRewardService，False使用旧版本
# 设置为True使用新版DI架构的MentorshipService，False使用旧版本
# =====================================================


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
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
        from ..infrastructure.repositories.mentorship_repository import MentorshipRepository
        from .mentorship_service_new import MentorshipService as MentorshipServiceNew

        service = MentorshipServiceNew(
            player_repo=PlayerRepository(session),
            social_app_repo=SocialApplicationRepository(session),
            mentorship_repo=MentorshipRepository(session),
        )
        await service.update_mentor_points(player_id, level_increase)
        # 检查并发放邀请奖励
        # 新版本: 使用DI架构（使用传入的session，因为调用方已管理事务）
        from ..player.invite_reward_service_new import InviteRewardService as InviteRewardServiceNew
        from ..infrastructure.repositories.player_repository import PlayerRepository
        from ..infrastructure.repositories.invite_reward_repository import InviteRewardRepository

        # 使用传入的session创建Repository（不创建新的UoW，保持事务一致性）
        invite_reward_service = InviteRewardServiceNew(
            invite_reward_repo=InviteRewardRepository(session),
            player_repo=PlayerRepository(session)
        )

        # 使用新版本
        reward_messages = await invite_reward_service.check_and_grant_level_rewards(player_id, new_level)

        # 检查是否有功能解锁提示
        unlock_message = get_breakthrough_unlock_message(new_level, old_level)
        if unlock_message:
            reward_messages.append(unlock_message)

        # 返回奖励消息，供调用方使用
        return reward_messages

    return []
