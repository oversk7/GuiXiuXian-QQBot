"""
邀请奖励服务 - DI版本

采用依赖注入模式，通过Repository访问数据，解决N+1查询问题
"""
from typing import Tuple, Dict, List, Optional
from datetime import datetime

from ..models.player import Player
from ..models.invite_reward import InviteReward
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.invite_reward_repository import InviteRewardRepository


class InviteRewardService:
    """邀请奖励服务类 - DI版本"""

    # 分级奖励配置（香火）
    LEVEL_REWARDS = {
        1: {
            "inviter_incense": 300,
            "inviter_items": [],  # 可以添加道具奖励
            "invitee_incense": 100,
            "invitee_items": [],
            "description": "1级奖励"
        },
        10: {
            "inviter_incense": 800,
            "inviter_items": [],
            "invitee_incense": 300,
            "invitee_items": [],
            "description": "10级奖励"
        },
        50: {
            "inviter_incense": 2000,
            "inviter_items": [],
            "invitee_incense": 800,
            "invitee_items": [],
            "description": "50级奖励"
        }
    }

    def __init__(
        self,
        invite_reward_repo: InviteRewardRepository,
        player_repo: PlayerRepository
    ):
        """
        初始化邀请奖励服务

        Args:
            invite_reward_repo: 邀请奖励仓储
            player_repo: 玩家仓储
        """
        self._invite_reward_repo = invite_reward_repo
        self._player_repo = player_repo

    async def create_invite_record(
        self,
        invitee_uid: int,
        inviter_uid: int,
        server_id: int
    ) -> InviteReward:
        """
        创建邀请记录

        Args:
            invitee_uid: 被邀请者UID
            inviter_uid: 邀请者UID

        Returns:
            创建的邀请记录
        """
        invite_record = InviteReward(
            server_id=server_id,
            invitee_uid=invitee_uid,
            inviter_uid=inviter_uid
        )
        return await self._invite_reward_repo.add(invite_record)

    async def check_and_grant_level_rewards(
        self,
        player_id: str,
        new_level: int
    ) -> List[str]:
        """
        检查并发放等级奖励

        Args:
            player_id: 玩家ID
            new_level: 新等级

        Returns:
            奖励消息列表
        """
        # 获取玩家信息
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return []

        # 查找该玩家的邀请记录
        invite_record = await self._invite_reward_repo.get_by_invitee_uid(
            player.uid,
            player.server_id
        )
        if not invite_record:
            return []  # 没有邀请记录

        # 获取邀请者信息
        inviter = await self._player_repo.get_by_uid(
            invite_record.inviter_uid,
            invite_record.server_id
        )
        if not inviter:
            return []  # 邀请者不存在

        messages = []

        # 检查各级奖励
        for level_threshold in [1, 10, 50]:
            if new_level >= level_threshold:
                reward_granted = await self._grant_level_reward(
                    invite_record, inviter, player, level_threshold
                )
                if reward_granted:
                    messages.append(reward_granted)

        return messages

    async def _grant_level_reward(
        self,
        invite_record: InviteReward,
        inviter: Player,
        invitee: Player,
        level: int
    ) -> str:
        """
        发放指定等级的奖励

        Args:
            invite_record: 邀请记录
            inviter: 邀请者
            invitee: 被邀请者
            level: 等级阈值

        Returns:
            奖励消息，如果已发放则返回空字符串
        """
        # 检查是否已经发放过该等级奖励
        if await self._invite_reward_repo.check_reward_granted(invite_record, level):
            return ""

        reward_config = self.LEVEL_REWARDS.get(level)
        if not reward_config:
            return ""

        # 发放香火奖励
        inviter.incense += reward_config["inviter_incense"]
        invitee.incense += reward_config["invitee_incense"]

        # 更新玩家信息
        await self._player_repo.update(inviter)
        await self._player_repo.update(invitee)

        # 标记奖励已发放
        await self._invite_reward_repo.update_reward_status(invite_record, level)

        return (
            f"🎉 邀请奖励发放！\n"
            f"📈 {invitee.nickname} 达到{level}级\n"
            f"🎁 邀请者 {inviter.nickname} 获得 🪔{reward_config['inviter_incense']} 香火\n"
            f"🎁 被邀请者 {invitee.nickname} 获得 🪔{reward_config['invitee_incense']} 香火"
        )

    async def get_invite_status(self, player_uid: int, server_id: int) -> Dict:
        """
        获取邀请状态信息

        Args:
            player_uid: 玩家UID

        Returns:
            包含邀请统计的字典
        """
        # 查找作为邀请者的记录
        inviter_records = await self._invite_reward_repo.get_by_inviter_uid(
            player_uid,
            server_id
        )

        # 查找作为被邀请者的记录
        invitee_record = await self._invite_reward_repo.get_by_invitee_uid(
            player_uid,
            server_id
        )

        return {
            "invited_count": len(inviter_records),
            "inviter_records": inviter_records,
            "invitee_record": invitee_record
        }

    async def get_pending_rewards_info(self, inviter_uid: int, server_id: int) -> List[Dict]:
        """
        获取待发放奖励信息（优化版，解决N+1查询）

        Args:
            inviter_uid: 邀请者UID

        Returns:
            待发放奖励信息列表
        """
        # 使用优化的查询方法，一次性获取所有记录和玩家信息
        records_with_players = await self._invite_reward_repo.get_records_with_invitee_players(
            inviter_uid,
            server_id
        )

        pending_rewards = []

        for record, invitee in records_with_players:
            if not invitee:
                continue

            # 检查各级奖励状态
            for level in [1, 10, 50]:
                if invitee.level >= level:
                    rewarded = await self._invite_reward_repo.check_reward_granted(
                        record, level
                    )
                    if not rewarded:
                        reward_config = self.LEVEL_REWARDS.get(level)
                        pending_rewards.append({
                            "invitee_name": invitee.nickname,
                            "invitee_level": invitee.level,
                            "reward_level": level,
                            "inviter_incense": reward_config["inviter_incense"],
                            "invitee_incense": reward_config["invitee_incense"]
                        })

        return pending_rewards
