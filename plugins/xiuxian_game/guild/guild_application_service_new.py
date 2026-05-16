"""
公会申请系统服务 - DI架构版本

将GuildApplicationService改造为依赖注入架构，移除内部commit，通过Repository抽象数据访问
"""

from typing import Optional, Tuple, List
from datetime import datetime

from ..models.player import Player
from ..models.guild import Guild
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.guild_repository import GuildRepository
from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository


class GuildApplicationService:
    """公会申请系统服务类 - DI架构版本"""

    def __init__(
        self,
        player_repo: PlayerRepository,
        guild_repo: GuildRepository,
        application_repo: SocialApplicationRepository,
    ):
        """
        初始化公会申请服务

        Args:
            player_repo: 玩家仓储
            guild_repo: 公会仓储
            application_repo: 社交申请仓储
        """
        self._player_repo = player_repo
        self._guild_repo = guild_repo
        self._application_repo = application_repo

    @staticmethod
    def _get_guild_capacity(level: int) -> int:
        """
        获取公会容量

        Args:
            level: 公会等级

        Returns:
            公会容量

        对应原代码:
            guild_application_service.py Line 45-46
        """
        return 10 + (level - 1) * 5

    async def can_apply_guild(
        self, player_id: str, guild_id: int
    ) -> Tuple[bool, str]:
        """
        检查是否可以申请加入公会

        Args:
            player_id: 玩家ID
            guild_id: 公会ID

        Returns:
            (是否可以申请, 错误信息)

        对应原代码:
            guild_application_service.py Line 14-55
        """
        # 获取玩家信息
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在"

        # 检查玩家是否已加入公会
        if player.guild_id is not None:
            return False, "你已经加入公会，无法再次加入"

        # 检查公会是否存在
        guild = await self._guild_repo.get_by_id(guild_id)
        if not guild:
            return False, "未找到该公会"
        if guild.server_id != player.server_id:
            return False, "不能申请其他区服的公会"

        # 检查是否已有待处理的申请
        existing_app = await self._application_repo.get_pending_application_by_player_and_guild(
            player_id, guild_id
        )
        if existing_app:
            return False, "你已提交申请，请等待会长审核"

        # 检查公会容量
        member_count = await self._guild_repo.get_member_count(guild_id)
        capacity = self._get_guild_capacity(guild.level)

        if member_count >= capacity:
            return False, "该公会人数已满，无法申请"

        return True, ""

    async def create_guild_application(
        self, player_id: str, guild_id: int
    ) -> SocialApplication:
        """
        创建公会申请

        Args:
            player_id: 玩家ID
            guild_id: 公会ID

        Returns:
            创建的申请记录

        对应原代码:
            guild_application_service.py Line 57-68

        Note:
            ⚠️ 原代码有P0问题：Line 67有内部commit
            新版本移除了内部commit，由调用方控制事务边界
        """
        application = SocialApplication(
            applicant_id=player_id,
            target_id="",  # 公会申请不需要 target_id
            guild_id=guild_id,
            application_type=ApplicationType.GUILD_JOIN
        )
        await self._application_repo.add(application)
        # ❌ 移除内部commit，由调用方控制事务边界
        return application

    async def get_pending_applications(
        self, guild_id: int
    ) -> List[SocialApplication]:
        """
        获取公会的待处理申请列表

        Args:
            guild_id: 公会ID

        Returns:
            待处理申请列表（按申请时间升序）

        对应原代码:
            guild_application_service.py Line 70-82
        """
        return await self._application_repo.get_pending_guild_applications(guild_id)

    async def get_application_by_player_and_guild(
        self, player_id: str, guild_id: int
    ) -> Optional[SocialApplication]:
        """
        根据玩家ID和公会ID获取待处理申请

        Args:
            player_id: 玩家ID
            guild_id: 公会ID

        Returns:
            待处理的申请记录，不存在返回None

        对应原代码:
            guild_application_service.py Line 84-100
        """
        return await self._application_repo.get_pending_application_by_player_and_guild(
            player_id, guild_id
        )

    async def approve_application(
        self, application: SocialApplication, guild: Guild
    ) -> Tuple[bool, str]:
        """
        批准公会申请

        Args:
            application: 申请记录
            guild: 公会实例

        Returns:
            (是否成功, 消息)

        对应原代码:
            guild_application_service.py Line 102-154

        Note:
            ⚠️ 原代码有P0问题：Line 130和153有内部commit
            新版本移除了内部commit，由调用方控制事务边界
        """
        # 获取申请人
        applicant = await self._player_repo.get_by_id(application.applicant_id)
        if not applicant:
            return False, "申请人不存在"
        if applicant.server_id != guild.server_id:
            await self._application_repo.reject_application(application)
            return False, "申请人与公会不在同一区服"

        # 检查申请人是否已经加入当前公会（可能在调用此方法前已通过join_guild加入）
        already_joined_current_guild = (applicant.guild_id == guild.id)

        # 如果申请人还未加入当前公会，需要检查容量
        if not already_joined_current_guild:
            # 再次检查公会容量（防止并发问题）
            member_count = await self._guild_repo.get_member_count(guild.id)
            capacity = self._get_guild_capacity(guild.level)

            if member_count >= capacity:
                return False, "公会人数已满，无法同意"

            # 检查申请人是否已加入其他公会
            if applicant.guild_id is not None and applicant.guild_id != guild.id:
                await self._application_repo.reject_application(application)
                # ❌ 移除内部commit，由调用方控制事务边界
                return False, "该玩家已加入其他公会，无法同意"

            # 批准申请：设置公会ID
            applicant.guild_id = guild.id
            await self._player_repo.update(applicant)

        # 更新申请状态（无论申请人是否已加入，都要更新状态）
        await self._application_repo.approve_application(application)

        # 将该玩家其他待处理的公会申请全部标记为拒绝
        await self._application_repo.reject_other_pending_applications(
            applicant.id, application.id
        )

        # ❌ 移除内部commit，由调用方控制事务边界
        return True, "申请已批准"

    async def reject_application(
        self, application: SocialApplication
    ) -> None:
        """
        拒绝公会申请

        Args:
            application: 申请记录

        对应原代码:
            guild_application_service.py Line 156-162

        Note:
            ⚠️ 原代码有P0问题：Line 162有内部commit
            新版本移除了内部commit，由调用方控制事务边界
        """
        await self._application_repo.reject_application(application)
        # ❌ 移除内部commit，由调用方控制事务边界

    async def get_player_applications(
        self, player_id: str
    ) -> List[SocialApplication]:
        """
        获取玩家的公会申请历史

        Args:
            player_id: 玩家ID

        Returns:
            申请记录列表（按申请时间降序）

        对应原代码:
            guild_application_service.py Line 164-175
        """
        return await self._application_repo.get_player_applications(
            player_id, ApplicationType.GUILD_JOIN
        )
