"""
InviteRewardRepository - 邀请奖励数据访问层

提供邀请奖励相关的数据库操作，解决N+1查询问题
"""
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from ...models.invite_reward import InviteReward
from ...models.player import Player
from ...domain.repositories.base import IRepository


class InviteRewardRepository(IRepository[InviteReward]):
    """邀请奖励仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, entity_id: int) -> Optional[InviteReward]:
        """根据ID获取邀请记录"""
        return await self._session.get(InviteReward, entity_id)

    async def add(self, entity: InviteReward) -> InviteReward:
        """添加邀请记录"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def update(self, entity: InviteReward) -> InviteReward:
        """更新邀请记录"""
        self._session.add(entity)
        await self._session.flush()
        return entity

    async def delete(self, entity: InviteReward):
        """删除邀请记录"""
        await self._session.delete(entity)
        await self._session.flush()

    async def list(self, **filters) -> List[InviteReward]:
        """列出所有邀请记录"""
        stmt = select(InviteReward)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count(self, **filters) -> int:
        """统计邀请记录数量"""
        from sqlalchemy import func
        stmt = select(func.count()).select_from(InviteReward)
        result = await self._session.execute(stmt)
        return result.scalar()

    async def exists(self, entity_id: int) -> bool:
        """
        检查邀请记录是否存在

        Args:
            entity_id: 邀请记录ID

        Returns:
            是否存在
        """
        entity = await self.get_by_id(entity_id)
        return entity is not None

    # ==================== 邀请奖励特定方法 ====================

    async def get_by_invitee_uid(self, invitee_uid: int, server_id: int | None = None) -> Optional[InviteReward]:
        """
        根据被邀请者UID获取邀请记录

        Args:
            invitee_uid: 被邀请者UID

        Returns:
            邀请记录，如果不存在则返回None
        """
        stmt = select(InviteReward).where(InviteReward.invitee_uid == invitee_uid)
        if server_id is not None:
            stmt = stmt.where(InviteReward.server_id == server_id)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def get_by_inviter_uid(self, inviter_uid: int, server_id: int | None = None) -> List[InviteReward]:
        """
        根据邀请者UID获取所有邀请记录

        Args:
            inviter_uid: 邀请者UID

        Returns:
            邀请记录列表
        """
        stmt = select(InviteReward).where(InviteReward.inviter_uid == inviter_uid)
        if server_id is not None:
            stmt = stmt.where(InviteReward.server_id == server_id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_records_with_invitee_players(
        self, inviter_uid: int, server_id: int | None = None
    ) -> List[tuple[InviteReward, Optional[Player]]]:
        """
        获取邀请记录并预加载被邀请者玩家信息（解决N+1查询）

        Args:
            inviter_uid: 邀请者UID

        Returns:
            (InviteReward, Player)元组列表
        """
        # 查询邀请记录
        invite_stmt = select(InviteReward).where(InviteReward.inviter_uid == inviter_uid)
        if server_id is not None:
            invite_stmt = invite_stmt.where(InviteReward.server_id == server_id)
        invite_result = await self._session.execute(invite_stmt)
        records = list(invite_result.scalars().all())

        if not records:
            return []

        # 批量查询所有被邀请者
        invitee_uids = [r.invitee_uid for r in records]
        player_stmt = select(Player).where(Player.uid.in_(invitee_uids))
        if server_id is not None:
            player_stmt = player_stmt.where(Player.server_id == server_id)
        player_result = await self._session.execute(player_stmt)
        players = {p.uid: p for p in player_result.scalars().all()}

        # 组合结果
        return [(record, players.get(record.invitee_uid)) for record in records]

    async def update_reward_status(
        self,
        record: InviteReward,
        level: int,
    ) -> InviteReward:
        """
        更新奖励发放状态

        Args:
            record: 邀请记录
            level: 等级（1, 10, 50）

        Returns:
            更新后的记录
        """
        from datetime import datetime

        now = datetime.now()

        if level == 1:
            record.level_1_rewarded = True
            record.level_1_rewarded_at = now
        elif level == 10:
            record.level_10_rewarded = True
            record.level_10_rewarded_at = now
        elif level == 50:
            record.level_50_rewarded = True
            record.level_50_rewarded_at = now
        else:
            raise ValueError(f"Invalid level: {level}. Must be 1, 10, or 50.")

        self._session.add(record)
        await self._session.flush()
        return record

    async def check_reward_granted(self, record: InviteReward, level: int) -> bool:
        """
        检查指定等级的奖励是否已发放

        Args:
            record: 邀请记录
            level: 等级（1, 10, 50）

        Returns:
            True如果已发放，False否则
        """
        if level == 1:
            return record.level_1_rewarded
        elif level == 10:
            return record.level_10_rewarded
        elif level == 50:
            return record.level_50_rewarded
        else:
            raise ValueError(f"Invalid level: {level}. Must be 1, 10, or 50.")
