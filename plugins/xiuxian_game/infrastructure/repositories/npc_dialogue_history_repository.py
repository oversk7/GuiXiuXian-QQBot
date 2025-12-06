"""NPC对话历史仓储实现"""
from typing import Optional, List
from datetime import datetime, timedelta
from sqlalchemy import select, and_, desc, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.repositories.base import IRepository
from ...models.npc_dialogue_history import NPCDialogueHistory


class NPCDialogueHistoryRepository(IRepository[NPCDialogueHistory]):
    """NPC对话历史仓储"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, history_id: int) -> Optional[NPCDialogueHistory]:
        """按ID查询对话历史"""
        stmt = select(NPCDialogueHistory).where(NPCDialogueHistory.id == history_id)
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_recent_interactions(
        self,
        npc_id: int,
        player_id: str,
        limit: int = 10
    ) -> List[NPCDialogueHistory]:
        """
        获取最近N条对话记录（用于构建AI上下文）

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            limit: 返回条数，默认10

        Returns:
            按时间倒序的对话历史列表
        """
        stmt = (
            select(NPCDialogueHistory)
            .where(
                and_(
                    NPCDialogueHistory.npc_id == npc_id,
                    NPCDialogueHistory.player_id == player_id
                )
            )
            .order_by(desc(NPCDialogueHistory.created_at))
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        # 返回时反转顺序，使最早的对话在前
        return list(reversed(result.scalars().all()))

    async def save(self, history: NPCDialogueHistory) -> NPCDialogueHistory:
        """保存对话历史"""
        self._session.add(history)
        await self._session.flush()
        return history

    async def get_total_interactions(self, npc_id: int, player_id: str) -> int:
        """获取总对话次数"""
        from sqlalchemy import func
        stmt = select(func.count(NPCDialogueHistory.id)).where(
            and_(
                NPCDialogueHistory.npc_id == npc_id,
                NPCDialogueHistory.player_id == player_id
            )
        )
        result = await self._session.execute(stmt)
        return result.scalar() or 0

    async def delete_old_records(self, days: int = 30) -> int:
        """
        删除N天前的对话记录

        Args:
            days: 保留天数，默认30天

        Returns:
            删除的记录数
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        stmt = delete(NPCDialogueHistory).where(
            NPCDialogueHistory.created_at < cutoff_date
        )
        result = await self._session.execute(stmt)
        return result.rowcount

    async def get_dialogue_stats(
        self,
        npc_id: int = None,
        player_id: str = None,
        start_date: datetime = None,
        end_date: datetime = None
    ) -> dict:
        """
        获取对话统计数据

        Args:
            npc_id: 可选，NPC ID
            player_id: 可选，玩家ID
            start_date: 可选，开始时间
            end_date: 可选，结束时间

        Returns:
            统计数据字典
        """
        from sqlalchemy import func

        # 构建查询条件
        conditions = []
        if npc_id is not None:
            conditions.append(NPCDialogueHistory.npc_id == npc_id)
        if player_id is not None:
            conditions.append(NPCDialogueHistory.player_id == player_id)
        if start_date is not None:
            conditions.append(NPCDialogueHistory.created_at >= start_date)
        if end_date is not None:
            conditions.append(NPCDialogueHistory.created_at <= end_date)

        # 查询统计数据
        stmt = select(
            func.count(NPCDialogueHistory.id).label('total_count'),
            func.sum(NPCDialogueHistory.dialogue_duration_seconds).label('total_duration'),
            func.sum(NPCDialogueHistory.ai_tokens_used).label('total_tokens'),
            func.sum(NPCDialogueHistory.ai_cost).label('total_cost')
        )

        if conditions:
            stmt = stmt.where(and_(*conditions))

        result = await self._session.execute(stmt)
        row = result.one()

        return {
            'total_count': row.total_count or 0,
            'total_duration_seconds': row.total_duration or 0,
            'total_tokens_used': row.total_tokens or 0,
            'total_cost_cents': row.total_cost or 0,  # 以分为单位
        }
