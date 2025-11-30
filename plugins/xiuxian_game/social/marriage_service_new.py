"""
婚姻系统服务模块 (DI架构版本)

改造说明:
- 从静态方法改为实例方法
- 通过构造函数注入3个Repository依赖
- 移除所有session参数，通过self._xxx_repo访问数据
- 移除所有内部commit()调用(7处)，由调用方控制事务边界
- 保持业务逻辑完全一致
"""
from typing import Optional, Tuple, List
from datetime import datetime

from ..models.player import Player
from ..models.marriage import Marriage
from ..models.social_application import SocialApplication, ApplicationType, ApplicationStatus
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.social_application_repository import SocialApplicationRepository
from ..infrastructure.repositories.marriage_repository import MarriageRepository


class MarriageService:
    """
    婚姻系统服务类 (DI版本)

    依赖注入:
        - player_repo: PlayerRepository
        - social_app_repo: SocialApplicationRepository
        - marriage_repo: MarriageRepository
    """

    def __init__(
        self,
        player_repo: PlayerRepository,
        social_app_repo: SocialApplicationRepository,
        marriage_repo: MarriageRepository
    ):
        """
        初始化婚姻服务

        Args:
            player_repo: 玩家仓储
            social_app_repo: 社交申请仓储
            marriage_repo: 婚姻关系仓储
        """
        self._player_repo = player_repo
        self._social_app_repo = social_app_repo
        self._marriage_repo = marriage_repo

    async def get_marriage(self, player_id: str) -> Optional[Marriage]:
        """
        获取玩家的婚姻关系

        Args:
            player_id: 玩家ID

        Returns:
            婚姻关系对象，如果未结婚则返回None

        对应原代码:
            marriage_service.py Line 16-22
        """
        return await self._marriage_repo.get_by_player_id(player_id)

    async def get_spouse(self, player_id: str) -> Optional[Player]:
        """
        获取玩家的配偶

        Args:
            player_id: 玩家ID

        Returns:
            配偶对象，如果未结婚则返回None

        对应原代码:
            marriage_service.py Line 24-35
        """
        marriage = await self.get_marriage(player_id)
        if not marriage:
            return None

        spouse_id = marriage.get_spouse_id(player_id)
        if not spouse_id:
            return None

        return await self._player_repo.get_by_id(spouse_id)

    async def is_married(self, player_id: str) -> bool:
        """
        检查玩家是否已婚

        Args:
            player_id: 玩家ID

        Returns:
            是否已婚

        对应原代码:
            marriage_service.py Line 38-41
        """
        return await self._marriage_repo.is_married(player_id)

    async def can_propose(self, proposer_id: str, target_id: str) -> Tuple[bool, str]:
        """
        检查是否可以求婚

        Args:
            proposer_id: 求婚者ID
            target_id: 目标玩家ID

        Returns:
            (是否可以求婚, 提示信息)

        对应原代码:
            marriage_service.py Line 44-69
        """
        if proposer_id == target_id:
            return False, "不能向自己求婚"

        # 检查双方是否已婚
        if await self.is_married(proposer_id):
            return False, "你已经结婚了"

        if await self.is_married(target_id):
            return False, "对方已经结婚了"

        # 检查是否已有待处理的求婚申请
        existing_app = await self._social_app_repo.get_pending_marriage_proposal_by_applicant_and_target(
            proposer_id, target_id
        )
        if existing_app:
            return False, "你已经向对方求过婚了，请等待回复"

        return True, ""

    async def create_proposal(self, proposer_id: str, target_id: str) -> SocialApplication:
        """
        创建求婚申请

        Args:
            proposer_id: 求婚者ID
            target_id: 目标玩家ID

        Returns:
            创建的申请记录

        对应原代码:
            marriage_service.py Line 72-81

        P0修复:
            移除Line 80的commit()
        """
        application = SocialApplication(
            applicant_id=proposer_id,
            target_id=target_id,
            application_type=ApplicationType.MARRIAGE
        )
        await self._social_app_repo.add(application)
        # P0修复: 移除commit() - 由调用方控制事务
        return application

    async def get_pending_proposals(self, player_id: str) -> List[SocialApplication]:
        """
        获取玩家收到的待处理求婚申请

        Args:
            player_id: 玩家ID

        Returns:
            待处理求婚申请列表

        对应原代码:
            marriage_service.py Line 84-94
        """
        return await self._social_app_repo.get_pending_marriage_proposals_by_target(player_id)

    async def accept_proposal(self, application_id: int, target_id: str) -> Tuple[bool, str]:
        """
        接受求婚申请（通过申请ID）

        Args:
            application_id: 申请ID
            target_id: 目标玩家ID（接受者）

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            marriage_service.py Line 97-133

        P0修复:
            移除Line 132的commit()
        """
        # 获取申请
        application = await self._social_app_repo.get_by_id(application_id)
        if not application or application.target_id != target_id:
            return False, "申请不存在或无权限"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == target_id:
            return False, "不能向自己求婚"

        # 检查双方是否已婚
        if await self.is_married(application.applicant_id):
            return False, "对方已经结婚了"

        if await self.is_married(target_id):
            return False, "你已经结婚了"

        # 创建婚姻关系
        marriage = Marriage(
            player1_id=application.applicant_id,
            player2_id=target_id
        )
        await self._marriage_repo.add(marriage)

        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        await self._social_app_repo.update(application)

        # 拒绝其他相关的求婚申请
        await self._reject_other_proposals(application.applicant_id, target_id)

        # P0修复: 移除commit() - 由调用方控制事务
        return True, "恭喜你们结为夫妻！"

    async def accept_proposal_by_uid(self, proposer_id: str, target_id: str) -> Tuple[bool, str]:
        """
        通过UID接受求婚申请

        Args:
            proposer_id: 求婚者ID
            target_id: 目标玩家ID（接受者）

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            marriage_service.py Line 136-181

        P0修复:
            移除Line 180的commit()
        """
        # 查找对应的申请
        application = await self._social_app_repo.get_pending_marriage_proposal_by_applicant_and_target(
            proposer_id, target_id
        )

        if not application:
            return False, "未找到该玩家的求婚申请"

        if not application.is_pending():
            return False, "申请已被处理"

        # 简化检查：只检查基本条件，不检查重复申请
        if application.applicant_id == target_id:
            return False, "不能向自己求婚"

        # 检查双方是否已婚
        if await self.is_married(application.applicant_id):
            return False, "对方已经结婚了"

        if await self.is_married(target_id):
            return False, "你已经结婚了"

        # 创建婚姻关系
        marriage = Marriage(
            player1_id=application.applicant_id,
            player2_id=target_id
        )
        await self._marriage_repo.add(marriage)

        # 更新申请状态
        application.status = ApplicationStatus.APPROVED
        application.processed_at = datetime.now()
        await self._social_app_repo.update(application)

        # 拒绝其他相关的求婚申请
        await self._reject_other_proposals(application.applicant_id, target_id)

        # P0修复: 移除commit() - 由调用方控制事务
        return True, "恭喜你们结为夫妻！"

    async def reject_proposal(self, application_id: int, target_id: str) -> Tuple[bool, str]:
        """
        拒绝求婚申请（通过申请ID）

        Args:
            application_id: 申请ID
            target_id: 目标玩家ID（拒绝者）

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            marriage_service.py Line 184-196

        P0修复:
            移除Line 195的commit()
        """
        application = await self._social_app_repo.get_by_id(application_id)
        if not application or application.target_id != target_id:
            return False, "申请不存在或无权限"

        if not application.is_pending():
            return False, "申请已被处理"

        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        await self._social_app_repo.update(application)

        # P0修复: 移除commit() - 由调用方控制事务
        return True, "已拒绝求婚申请"

    async def reject_proposal_by_uid(self, proposer_id: str, target_id: str) -> Tuple[bool, str]:
        """
        通过UID拒绝求婚申请

        Args:
            proposer_id: 求婚者ID
            target_id: 目标玩家ID（拒绝者）

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            marriage_service.py Line 199-221

        P0修复:
            移除Line 220的commit()
        """
        # 查找对应的申请
        application = await self._social_app_repo.get_pending_marriage_proposal_by_applicant_and_target(
            proposer_id, target_id
        )

        if not application:
            return False, "未找到该玩家的求婚申请"

        if not application.is_pending():
            return False, "申请已被处理"

        application.status = ApplicationStatus.REJECTED
        application.processed_at = datetime.now()
        await self._social_app_repo.update(application)

        # P0修复: 移除commit() - 由调用方控制事务
        return True, "已拒绝求婚申请"

    async def divorce(self, player_id: str) -> Tuple[bool, str]:
        """
        离婚

        Args:
            player_id: 玩家ID

        Returns:
            (是否成功, 提示信息)

        对应原代码:
            marriage_service.py Line 224-232

        P0修复:
            移除Line 231的commit()
        """
        marriage = await self.get_marriage(player_id)
        if not marriage:
            return False, "你还没有结婚"

        await self._marriage_repo.delete_by_player_id(player_id)

        # P0修复: 移除commit() - 由调用方控制事务
        return True, "离婚成功"

    async def _reject_other_proposals(self, player1_id: str, player2_id: str):
        """
        拒绝其他相关的求婚申请（私有方法）

        Args:
            player1_id: 玩家1 ID
            player2_id: 玩家2 ID

        Note:
            当两个玩家结婚后，需要拒绝他们向其他人或收到的所有其他求婚申请

        对应原代码:
            marriage_service.py Line 235-253
        """
        # 获取所有相关的待处理求婚申请
        applications = await self._social_app_repo.get_all_pending_marriage_proposals_for_players(
            player1_id, player2_id
        )

        # 批量拒绝
        for app in applications:
            app.status = ApplicationStatus.REJECTED
            app.processed_at = datetime.now()
            await self._social_app_repo.update(app)

    async def update_gift_value(self, player1_id: str, player2_id: str, value: int):
        """
        更新夫妻间礼物总价值

        Args:
            player1_id: 玩家1 ID
            player2_id: 玩家2 ID（配偶）
            value: 增加的礼物价值

        对应原代码:
            marriage_service.py Line 256-261

        P0修复:
            移除Line 261的commit()
        """
        marriage = await self.get_marriage(player1_id)
        if marriage and marriage.involves_player(player2_id):
            await self._marriage_repo.update_gift_value(player1_id, value)
            # P0修复: 移除commit() - 由调用方控制事务
