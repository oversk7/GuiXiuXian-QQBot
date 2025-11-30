"""
师徒系统服务模块 (DI架构版本)
"""
from typing import Optional, Tuple, List
from datetime import datetime

from ..models.player import Player
from ..models.mentorship import Mentorship
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
from ..infrastructure.repositories.mentorship_repository import MentorshipRepository


class MentorshipService:
    """师徒系统服务类 (DI架构版本)"""

    def __init__(
        self,
        player_repo: PlayerRepository,
        social_app_repo: SocialApplicationRepository,
        mentorship_repo: MentorshipRepository
    ):
        """
        初始化师徒系统服务

        Args:
            player_repo: 玩家仓储
            social_app_repo: 社交申请仓储
            mentorship_repo: 师徒关系仓储
        """
        self._player_repo = player_repo
        self._social_app_repo = social_app_repo
        self._mentorship_repo = mentorship_repo

    async def get_master(self, disciple_id: str) -> Optional[Player]:
        """获取徒弟的师父"""
        mentorship = await self._mentorship_repo.get_by_disciple_id(disciple_id)
        if not mentorship:
            return None
        return await self._player_repo.get_by_id(mentorship.master_id)

    async def get_disciples(self, master_id: str) -> List[Player]:
        """获取师父的所有徒弟"""
        # 使用优化后的方法，避免N+1查询
        mentorship_player_pairs = await self._mentorship_repo.get_disciples_with_players(master_id)
        return [player for _, player in mentorship_player_pairs]

    async def get_disciples_count(self, master_id: str) -> int:
        """获取师父的徒弟数量"""
        return await self._mentorship_repo.get_disciples_count(master_id)

    async def get_mentorship(self, master_id: str, disciple_id: str) -> Optional[Mentorship]:
        """获取师徒关系"""
        return await self._mentorship_repo.get_by_master_and_disciple(master_id, disciple_id)

    async def has_master(self, player_id: str) -> bool:
        """检查玩家是否有师父"""
        master = await self.get_master(player_id)
        return master is not None

    async def can_become_disciple(self, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """检查是否可以拜师"""
        if applicant_id == master_id:
            return False, "不能拜自己为师"

        # 检查申请人是否已有师父
        if await self.has_master(applicant_id):
            return False, "你已经有师父了"

        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await self.get_mentorship(applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"

        # 检查是否已有待处理的拜师申请
        existing_app = await self._social_app_repo.get_pending_mentorship_application_by_applicant_and_target(
            applicant_id, master_id
        )
        if existing_app:
            return False, "你已经向对方发送过拜师申请了，请等待回复"

        return True, ""

    async def create_mentorship_application(self, applicant_id: str, master_id: str) -> SocialApplication:
        """创建拜师申请"""
        application = SocialApplication(
            applicant_id=applicant_id,
            target_id=master_id,
            application_type=ApplicationType.MENTORSHIP
        )
        await self._social_app_repo.add(application)
        # NO commit - 由调用方控制事务
        return application

    async def get_pending_mentorship_applications(self, master_id: str) -> List[SocialApplication]:
        """获取师父收到的待处理拜师申请"""
        return await self._social_app_repo.get_pending_mentorship_applications_by_target(master_id)

    async def accept_mentorship_application(self, application_id: int, master_id: str) -> Tuple[bool, str]:
        """接受拜师申请（通过申请ID）"""
        # 获取申请
        application = await self._social_app_repo.get_by_id(application_id)
        if not application or application.target_id != master_id:
            return False, "申请不存在或无权限"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == master_id:
            return False, "不能拜自己为师"

        # 检查申请人是否已有师父
        if await self.has_master(application.applicant_id):
            return False, "该玩家已经有师父了"

        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await self.get_mentorship(application.applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"

        # 检查师父的徒弟数量限制
        disciples_count = await self.get_disciples_count(master_id)
        if disciples_count >= 5:
            return False, "你的徒弟已达上限（5人），请先让一名徒弟出师"

        # 获取徒弟当前等级
        disciple = await self._player_repo.get_by_id(application.applicant_id)
        if not disciple:
            return False, "徒弟不存在"

        # 创建师徒关系
        mentorship = Mentorship(
            master_id=master_id,
            disciple_id=application.applicant_id,
            disciple_start_level=disciple.level
        )
        await self._mentorship_repo.add(mentorship)

        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()

        # 拒绝该徒弟的其他拜师申请
        await self._reject_other_mentorship_applications(application.applicant_id)

        # NO commit - 由调用方控制事务
        return True, "师徒关系建立成功！"

    async def accept_mentorship_application_by_uid(self, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """通过UID接受拜师申请"""
        # 查找对应的申请
        application = await self._social_app_repo.get_pending_mentorship_application_by_applicant_and_target(
            applicant_id, master_id
        )

        if not application:
            return False, "未找到该玩家的拜师申请"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == master_id:
            return False, "不能拜自己为师"

        # 检查申请人是否已有师父
        if await self.has_master(application.applicant_id):
            return False, "该玩家已经有师父了"

        # 检查目标是否已经是申请人的徒弟（防止循环师徒关系）
        existing_mentorship = await self.get_mentorship(application.applicant_id, master_id)
        if existing_mentorship:
            return False, "不能拜自己的徒弟为师"

        # 检查师父的徒弟数量限制
        disciples_count = await self.get_disciples_count(master_id)
        if disciples_count >= 5:
            return False, "你的徒弟已达上限（5人），请先让一名徒弟出师"

        # 获取徒弟当前等级
        disciple = await self._player_repo.get_by_id(application.applicant_id)
        if not disciple:
            return False, "徒弟不存在"

        # 创建师徒关系
        mentorship = Mentorship(
            master_id=master_id,
            disciple_id=application.applicant_id,
            disciple_start_level=disciple.level
        )
        await self._mentorship_repo.add(mentorship)

        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()

        # 拒绝该徒弟的其他拜师申请
        await self._reject_other_mentorship_applications(application.applicant_id)

        # NO commit - 由调用方控制事务
        return True, "师徒关系建立成功！"

    async def reject_mentorship_application(self, application_id: int, master_id: str) -> Tuple[bool, str]:
        """拒绝拜师申请（通过申请ID）"""
        application = await self._social_app_repo.get_by_id(application_id)
        if not application or application.target_id != master_id:
            return False, "申请不存在或无权限"

        if not application.is_pending():
            return False, "申请已被处理"

        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        # NO commit - 由调用方控制事务
        return True, "已拒绝拜师申请"

    async def reject_mentorship_application_by_uid(self, applicant_id: str, master_id: str) -> Tuple[bool, str]:
        """通过UID拒绝拜师申请"""
        # 查找对应的申请
        application = await self._social_app_repo.get_pending_mentorship_application_by_applicant_and_target(
            applicant_id, master_id
        )

        if not application:
            return False, "未找到该玩家的拜师申请"

        if not application.is_pending():
            return False, "申请已被处理"

        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        # NO commit - 由调用方控制事务
        return True, "已拒绝拜师申请"

    async def dismiss_disciple(self, master_id: str, disciple_uid: int, is_graduation: bool = False) -> Tuple[bool, str]:
        """逐出徒弟或让徒弟出师"""
        # 根据UID查找徒弟
        disciple = await self._player_repo.get_by_uid(disciple_uid)
        if not disciple:
            return False, "未找到该UID的玩家"

        # 检查师徒关系
        mentorship = await self.get_mentorship(master_id, disciple.id)
        if not mentorship:
            return False, "该玩家不是你的徒弟"

        await self._mentorship_repo.delete(mentorship.id)
        # NO commit - 由调用方控制事务

        if is_graduation:
            return True, f"恭喜 {disciple.nickname} 出师！愿你前程似锦，修行路上勇猛精进！"
        else:
            return True, f"已将 {disciple.nickname} 逐出师门"

    async def leave_master(self, disciple_id: str) -> Tuple[bool, str]:
        """脱离师父"""
        mentorship = await self._mentorship_repo.get_by_disciple_id(disciple_id)
        if not mentorship:
            return False, "你还没有师父"

        await self._mentorship_repo.delete(mentorship.id)
        # NO commit - 由调用方控制事务
        return True, "已脱离师门"

    async def update_mentor_points(self, disciple_id: str, level_increase: int):
        """更新恩师点数（当徒弟升级时调用）"""
        await self._mentorship_repo.update_mentor_points(disciple_id, level_increase)
        # NO commit - 由调用方控制事务

    async def get_mentor_points_ranking(self, limit: int = 10) -> List[Tuple[Player, int]]:
        """获取恩师点数排行榜"""
        # 获取排名数据（master_id和总点数）
        ranking_data = await self._mentorship_repo.get_mentor_points_ranking(limit)

        # 批量查询Player对象，避免N+1
        rankings = []
        for master_id, total_points in ranking_data:
            master = await self._player_repo.get_by_id(master_id)
            if master:
                rankings.append((master, total_points))

        return rankings

    async def _reject_other_mentorship_applications(self, disciple_id: str):
        """拒绝该徒弟的其他拜师申请（私有方法）"""
        applications = await self._social_app_repo.get_all_pending_mentorship_applications_by_applicant(disciple_id)
        for app in applications:
            app.status = ApplicationStatus.REJECTED
            app.processed_at = datetime.now()
