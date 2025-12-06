"""NPC好感度管理服务"""
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.npc_favorability import NPCFavorability
from ..infrastructure.repositories.npc_favorability_repository import NPCFavorabilityRepository

logger = logging.getLogger(__name__)


class NPCFavorabilityService:
    """NPC好感度管理服务"""

    def __init__(self, session: AsyncSession):
        """
        初始化好感度服务

        Args:
            session: 数据库会话
        """
        self._session = session
        self._repo = NPCFavorabilityRepository(session)

    async def get_favorability(
        self,
        npc_id: int,
        player_id: str,
        initial_favorability: int = 50
    ) -> NPCFavorability:
        """
        获取或创建好感度记录

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            initial_favorability: 初始好感度，默认50

        Returns:
            好感度记录
        """
        return await self._repo.get_or_create(
            npc_id=npc_id,
            player_id=player_id,
            initial_favorability=initial_favorability
        )

    async def add_interaction(
        self,
        npc_id: int,
        player_id: str,
        interaction_type: str,
        favorability_delta: int,
        event_description: Optional[str] = None
    ) -> NPCFavorability:
        """
        记录一次互动并更新好感度

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            interaction_type: 互动类型
                - "command_execution": 指令执行
                - "dialogue": 自然对话
                - "gift": 赠送物品
                - "combat": 战斗
            favorability_delta: 好感度变化(可为负)
            event_description: 事件描述

        Returns:
            更新后的NPCFavorability对象
        """
        # 获取或创建好感度记录
        favorability = await self.get_favorability(npc_id, player_id)

        # 更新好感度（限制在0-100范围内）
        old_favorability = favorability.current_favorability
        new_favorability = max(0, min(100, old_favorability + favorability_delta))

        favorability.current_favorability = new_favorability
        favorability.total_interactions += 1
        favorability.total_favorability_gained += favorability_delta

        # 检查并更新关系等级
        old_level = favorability.relationship_level
        await self._update_relationship_level(favorability)
        new_level = favorability.relationship_level

        # 如果关系等级提升，记录里程碑事件
        if old_level != new_level:
            self._record_milestone(favorability, f"relationship_level_{new_level}")
            logger.info(
                f"NPC好感度关系等级提升: npc_id={npc_id}, player_id={player_id}, "
                f"{old_level} -> {new_level}, favorability={new_favorability}"
            )

        # 检查好感度里程碑
        if old_favorability < 100 and new_favorability >= 100:
            self._record_milestone(favorability, "first_100_favorability")

        # 保存
        await self._repo.save(favorability)

        logger.info(
            f"NPC好感度更新: npc_id={npc_id}, player_id={player_id}, "
            f"type={interaction_type}, delta={favorability_delta:+d}, "
            f"favorability={old_favorability}->{new_favorability}"
        )

        return favorability

    async def _update_relationship_level(self, favorability: NPCFavorability):
        """更新关系等级（基于当前好感度）"""
        await self._repo.update_relationship_level(favorability)

    def _record_milestone(self, favorability: NPCFavorability, event_key: str):
        """记录里程碑事件"""
        from datetime import datetime
        if favorability.milestone_events is None:
            favorability.milestone_events = {}

        if event_key not in favorability.milestone_events:
            favorability.milestone_events[event_key] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def analyze_dialogue_sentiment(self, text: str) -> str:
        """
        分析对话内容的情感倾向

        Args:
            text: 对话内容

        Returns:
            情感类型: positive/negative/neutral/very_negative
        """
        # 负面词汇列表
        very_negative_words = [
            "去死", "滚", "傻", "蠢", "废物", "垃圾", "白痴", "该死", "混蛋",
            "王八蛋", "傻逼", "煞笔", "脑残", "智障", "弱智", "死", "杀了你"
        ]

        negative_words = [
            "讨厌", "烦", "无聊", "没用", "笨", "差劲", "糟糕", "恶心",
            "丑", "臭", "坏", "骗子", "不喜欢", "走开", "别烦我"
        ]

        # 正面词汇列表
        positive_words = [
            "喜欢", "爱", "好", "棒", "厉害", "漂亮", "帅", "美", "优秀",
            "谢谢", "感谢", "辛苦", "朋友", "兄弟", "姐妹", "帮忙", "请",
            "您好", "你好", "早安", "晚安", "加油", "关心", "照顾"
        ]

        text_lower = text.lower()

        # 检查极度负面
        for word in very_negative_words:
            if word in text_lower:
                return "very_negative"

        # 检查负面
        for word in negative_words:
            if word in text_lower:
                return "negative"

        # 检查正面
        for word in positive_words:
            if word in text_lower:
                return "positive"

        # 默认中性
        return "neutral"

    def get_favorability_change_by_interaction_type(
        self,
        interaction_type: str,
        success: bool = True,
        dialogue_content: str = None
    ) -> int:
        """
        根据互动类型获取好感度变化值

        Args:
            interaction_type: 互动类型
            success: 是否成功（用于指令执行）
            dialogue_content: 对话内容（用于分析情感）

        Returns:
            好感度变化值
        """
        if interaction_type == "dialogue":
            # 根据对话内容的情感分析调整好感度
            if dialogue_content:
                sentiment = self.analyze_dialogue_sentiment(dialogue_content)
                if sentiment == "very_negative":
                    return -10  # 辱骂等极度负面内容
                elif sentiment == "negative":
                    return -3   # 一般负面内容
                elif sentiment == "positive":
                    return 3    # 正面内容
                else:
                    return 1    # 中性内容
            else:
                return 1  # 默认中性

        elif interaction_type == "command_execution":
            if success:
                # 游戏指令执行成功：+5~+15
                return 10
            else:
                # 游戏指令执行失败：-5
                return -5

        elif interaction_type == "gift":
            # 赠送物品：+10~+30（具体值应根据物品价值调整）
            return 20

        elif interaction_type == "combat":
            if success:
                # 战斗胜利（与NPC队友）：+5
                return 5
            else:
                # 战斗失败（NPC被击杀）：-50
                return -50

        else:
            # 默认
            return 1

    async def set_follower_status(
        self,
        npc_id: int,
        player_id: str,
        is_follower: bool
    ) -> NPCFavorability:
        """
        设置NPC的跟随状态

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            is_follower: 是否跟随

        Returns:
            更新后的好感度记录
        """
        favorability = await self.get_favorability(npc_id, player_id)
        favorability.is_follower = is_follower

        if is_follower:
            self._record_milestone(favorability, "became_follower")

        await self._repo.save(favorability)
        return favorability

    async def set_partner_status(
        self,
        npc_id: int,
        player_id: str,
        is_partner: bool
    ) -> NPCFavorability:
        """
        设置NPC的伴侣状态

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            is_partner: 是否伴侣

        Returns:
            更新后的好感度记录
        """
        favorability = await self.get_favorability(npc_id, player_id)
        favorability.is_partner = is_partner

        if is_partner:
            self._record_milestone(favorability, "became_partner")

        await self._repo.save(favorability)
        return favorability

    def get_favorability_attitude(self, favorability: int) -> str:
        """
        根据好感度返回对应的态度描述

        Args:
            favorability: 好感度值(0-100)

        Returns:
            态度描述文本
        """
        if favorability <= 20:
            return "冷漠、敷衍"
        elif favorability <= 40:
            return "友好、配合"
        elif favorability <= 60:
            return "热情、主动"
        elif favorability <= 80:
            return "亲切、信任"
        else:
            return "忠诚、无条件"
