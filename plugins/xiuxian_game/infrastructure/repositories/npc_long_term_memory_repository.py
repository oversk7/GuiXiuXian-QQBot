"""
NPC长期记忆Repository

负责NPC长期记忆和总结检查点的数据库操作
"""

from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.npc_long_term_memory import NPCLongTermMemory, NPCDialogueSummaryCheckpoint


class NPCLongTermMemoryRepository:
    """NPC长期记忆Repository"""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== 长期记忆操作 ==========

    async def create_memory(
        self,
        npc_id: int,
        player_id: str,
        memory_type: str,
        content: str,
        event_type: Optional[str] = None,
        importance_score: int = 5,
        emotion_change: int = 0,
        from_dialogue_id: Optional[int] = None,
        to_dialogue_id: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> NPCLongTermMemory:
        """
        创建新的长期记忆

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            memory_type: 记忆类型（summary/event）
            content: 记忆内容
            event_type: 事件类型（仅event类型需要）
            importance_score: 重要性评分（1-10）
            emotion_change: 情感变化值
            from_dialogue_id: 起始对话ID
            to_dialogue_id: 结束对话ID
            metadata: 额外元数据

        Returns:
            创建的记忆对象
        """
        memory = NPCLongTermMemory(
            npc_id=npc_id,
            player_id=player_id,
            memory_type=memory_type,
            content=content,
            event_type=event_type,
            importance_score=importance_score,
            emotion_change=emotion_change,
            from_dialogue_id=from_dialogue_id,
            to_dialogue_id=to_dialogue_id,
            metadata=metadata,
            created_at=datetime.now(),
            weight=1.0,
            last_accessed_at=datetime.now()
        )
        self.session.add(memory)
        await self.session.flush()
        return memory

    async def get_memories_by_npc_player(
        self,
        npc_id: int,
        player_id: str,
        memory_type: Optional[str] = None,
        limit: int = 20,
        min_importance: int = 0,
        min_weight: float = 0.1
    ) -> List[NPCLongTermMemory]:
        """
        获取NPC和玩家的长期记忆列表

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            memory_type: 记忆类型过滤（可选）
            limit: 返回数量限制
            min_importance: 最小重要性评分
            min_weight: 最小权重

        Returns:
            记忆列表（按创建时间倒序）
        """
        query = select(NPCLongTermMemory).where(
            and_(
                NPCLongTermMemory.npc_id == npc_id,
                NPCLongTermMemory.player_id == player_id,
                NPCLongTermMemory.importance_score >= min_importance,
                NPCLongTermMemory.weight >= min_weight
            )
        )

        if memory_type:
            query = query.where(NPCLongTermMemory.memory_type == memory_type)

        query = query.order_by(desc(NPCLongTermMemory.created_at)).limit(limit)

        result = await self.session.execute(query)
        memories = result.scalars().all()

        # 加载到内存避免懒加载问题
        return list(memories)

    async def get_recent_summaries(
        self,
        npc_id: int,
        player_id: str,
        limit: int = 3
    ) -> List[NPCLongTermMemory]:
        """
        获取最近的对话总结

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            limit: 返回数量

        Returns:
            总结列表
        """
        return await self.get_memories_by_npc_player(
            npc_id=npc_id,
            player_id=player_id,
            memory_type="summary",
            limit=limit
        )

    async def get_important_events(
        self,
        npc_id: int,
        player_id: str,
        min_importance: int = 7,
        limit: int = 10
    ) -> List[NPCLongTermMemory]:
        """
        获取重要关键事件

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            min_importance: 最小重要性评分
            limit: 返回数量

        Returns:
            事件列表
        """
        return await self.get_memories_by_npc_player(
            npc_id=npc_id,
            player_id=player_id,
            memory_type="event",
            limit=limit,
            min_importance=min_importance
        )

    async def update_memory_weight(self, memory_id: int, new_weight: float):
        """更新记忆权重"""
        result = await self.session.execute(
            select(NPCLongTermMemory).where(NPCLongTermMemory.id == memory_id)
        )
        memory = result.scalar_one_or_none()
        if memory:
            memory.weight = new_weight
            memory.last_accessed_at = datetime.now()
            await self.session.flush()

    async def decay_old_memories(self, npc_id: int, player_id: str, days_threshold: int = 7):
        """
        衰减旧记忆的权重

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            days_threshold: 天数阈值（超过此天数的记忆会衰减）
        """
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        result = await self.session.execute(
            select(NPCLongTermMemory).where(
                and_(
                    NPCLongTermMemory.npc_id == npc_id,
                    NPCLongTermMemory.player_id == player_id,
                    NPCLongTermMemory.created_at < threshold_date,
                    NPCLongTermMemory.weight > 0.1
                )
            )
        )
        memories = result.scalars().all()

        for memory in memories:
            days_passed = (datetime.now() - memory.created_at).days
            memory.decay_weight(days_passed=days_passed - days_threshold)

        await self.session.flush()

    async def delete_low_weight_memories(self, npc_id: int, player_id: str, weight_threshold: float = 0.05):
        """删除权重过低的记忆"""
        result = await self.session.execute(
            select(NPCLongTermMemory).where(
                and_(
                    NPCLongTermMemory.npc_id == npc_id,
                    NPCLongTermMemory.player_id == player_id,
                    NPCLongTermMemory.weight < weight_threshold
                )
            )
        )
        memories = result.scalars().all()

        for memory in memories:
            await self.session.delete(memory)

        await self.session.flush()

    # ========== 总结检查点操作 ==========

    async def get_or_create_checkpoint(
        self,
        npc_id: int,
        player_id: str,
        initial_dialogue_id: int = 0
    ) -> NPCDialogueSummaryCheckpoint:
        """
        获取或创建总结检查点

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            initial_dialogue_id: 初始对话ID

        Returns:
            检查点对象
        """
        result = await self.session.execute(
            select(NPCDialogueSummaryCheckpoint).where(
                and_(
                    NPCDialogueSummaryCheckpoint.npc_id == npc_id,
                    NPCDialogueSummaryCheckpoint.player_id == player_id
                )
            )
        )
        checkpoint = result.scalar_one_or_none()

        if not checkpoint:
            checkpoint = NPCDialogueSummaryCheckpoint(
                npc_id=npc_id,
                player_id=player_id,
                last_summarized_dialogue_id=initial_dialogue_id,
                total_dialogues_summarized=0,
                last_summary_time=datetime.now(),
                next_summary_threshold=20
            )
            self.session.add(checkpoint)
            await self.session.flush()

        return checkpoint

    async def update_checkpoint(
        self,
        npc_id: int,
        player_id: str,
        latest_dialogue_id: int,
        summarized_count: int
    ):
        """
        更新总结检查点

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            latest_dialogue_id: 最新总结的对话ID
            summarized_count: 本次总结的对话数量
        """
        checkpoint = await self.get_or_create_checkpoint(npc_id, player_id)
        checkpoint.update_after_summary(latest_dialogue_id, summarized_count)
        await self.session.flush()

    async def should_trigger_summary(
        self,
        npc_id: int,
        player_id: str,
        current_dialogue_count: int
    ) -> bool:
        """
        判断是否应该触发总结

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            current_dialogue_count: 当前对话总数

        Returns:
            是否应该触发
        """
        checkpoint = await self.get_or_create_checkpoint(npc_id, player_id)
        return checkpoint.should_trigger_summary(current_dialogue_count)
