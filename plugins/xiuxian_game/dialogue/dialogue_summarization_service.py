"""
对话总结服务

负责对NPC对话历史进行总结，提取关键事件，构建长期记忆
"""

import json
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from ..ai_guide import call_ai_with_fallback
from ..models.npc_dialogue_history import NPCDialogueHistory
from ..infrastructure.repositories.npc_long_term_memory_repository import NPCLongTermMemoryRepository
from ..infrastructure.repositories.npc_dialogue_history_repository import NPCDialogueHistoryRepository

logger = logging.getLogger(__name__)


class DialogueSummarizationService:
    """对话总结服务"""

    def __init__(
        self,
        memory_repo: NPCLongTermMemoryRepository,
        dialogue_repo: NPCDialogueHistoryRepository
    ):
        """
        初始化对话总结服务

        Args:
            memory_repo: 长期记忆Repository
            dialogue_repo: 对话历史Repository
        """
        self.memory_repo = memory_repo
        self.dialogue_repo = dialogue_repo
        self.summary_threshold = 20  # 每20轮对话触发一次总结
        self.max_summary_dialogues = 30  # 每次最多总结30轮对话

    async def should_trigger_summary(
        self,
        npc_id: int,
        player_id: str
    ) -> bool:
        """
        判断是否应该触发总结

        Args:
            npc_id: NPC ID
            player_id: 玩家ID

        Returns:
            是否应该触发总结
        """
        # 获取对话总数
        total_count = await self.dialogue_repo.get_dialogue_count(npc_id, player_id)

        # 检查是否达到总结阈值
        return await self.memory_repo.should_trigger_summary(
            npc_id=npc_id,
            player_id=player_id,
            current_dialogue_count=total_count
        )

    async def summarize_dialogues(
        self,
        npc_id: int,
        player_id: str,
        npc_name: str,
        force: bool = False
    ) -> Optional[Dict]:
        """
        对对话历史进行总结

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            npc_name: NPC名称
            force: 是否强制总结（忽略阈值）

        Returns:
            总结结果字典（包含summary_id和event_ids），失败返回None
        """
        try:
            # 检查是否需要总结
            if not force:
                should_summarize = await self.should_trigger_summary(npc_id, player_id)
                if not should_summarize:
                    logger.debug(f"NPC {npc_name}(ID:{npc_id}) 与玩家 {player_id} 的对话尚未达到总结阈值")
                    return None

            # 获取检查点
            checkpoint = await self.memory_repo.get_or_create_checkpoint(npc_id, player_id)

            # 获取未总结的对话
            dialogues = await self.dialogue_repo.get_dialogues_after_id(
                npc_id=npc_id,
                player_id=player_id,
                after_dialogue_id=checkpoint.last_summarized_dialogue_id,
                limit=self.max_summary_dialogues
            )

            if not dialogues:
                logger.warning(f"没有找到NPC {npc_name} 与玩家 {player_id} 的未总结对话")
                return None

            logger.info(f"开始总结NPC {npc_name}(ID:{npc_id}) 与玩家 {player_id} 的 {len(dialogues)} 轮对话")

            # 调用AI进行总结
            summary_result = await self._call_ai_for_summary(
                dialogues=dialogues,
                npc_name=npc_name
            )

            if not summary_result:
                logger.error(f"AI总结失败 - NPC: {npc_name}, 玩家: {player_id}")
                return None

            # 存储总结
            summary_id = await self._store_summary(
                npc_id=npc_id,
                player_id=player_id,
                summary_content=summary_result["summary"],
                from_dialogue_id=dialogues[0].id,
                to_dialogue_id=dialogues[-1].id
            )

            # 存储关键事件
            event_ids = await self._store_key_events(
                npc_id=npc_id,
                player_id=player_id,
                key_events=summary_result.get("key_events", []),
                from_dialogue_id=dialogues[0].id,
                to_dialogue_id=dialogues[-1].id
            )

            # 更新检查点
            await self.memory_repo.update_checkpoint(
                npc_id=npc_id,
                player_id=player_id,
                latest_dialogue_id=dialogues[-1].id,
                summarized_count=len(dialogues)
            )

            logger.info(
                f"总结完成 - NPC: {npc_name}, 玩家: {player_id}, "
                f"总结ID: {summary_id}, 事件数: {len(event_ids)}"
            )

            return {
                "summary_id": summary_id,
                "event_ids": event_ids,
                "dialogues_summarized": len(dialogues)
            }

        except Exception as e:
            logger.error(f"对话总结失败 - NPC: {npc_name}, 玩家: {player_id}, 错误: {e}", exc_info=True)
            return None

    async def _call_ai_for_summary(
        self,
        dialogues: List[NPCDialogueHistory],
        npc_name: str
    ) -> Optional[Dict]:
        """
        调用AI进行对话总结

        Args:
            dialogues: 对话列表
            npc_name: NPC名称

        Returns:
            总结结果字典（包含summary和key_events），失败返回None
        """
        try:
            # 构建对话文本
            dialogue_text = self._format_dialogues_for_summary(dialogues)

            # 构建系统提示词
            system_prompt = f"""你是一个擅长总结和分析对话的AI助手。请仔细阅读以下玩家与NPC「{npc_name}」的对话历史，并完成以下任务：

1. **对话总结**：用100字以内简要总结这段对话的核心内容和情感基调
2. **关键事件提取**：识别对话中的重要事件（如送礼、承诺、冲突、情感表达等）

请以JSON格式输出结果，格式如下：
{{
  "summary": "对话总结（100字以内）",
  "key_events": [
    {{
      "event_type": "gift | quest | promise | conflict | emotion | other",
      "description": "事件描述（50字以内）",
      "importance": 7,
      "emotion_change": 3
    }}
  ]
}}

**注意**：
- event_type 可选值：gift（送礼）、quest（任务）、promise（承诺）、conflict（冲突）、emotion（情感表达）、other（其他）
- importance 评分范围：1-10（10最重要）
- emotion_change 情感变化：-10到+10（负数表示好感度下降）
- 如果没有关键事件，key_events 可以为空数组
- 只输出JSON，不要其他内容"""

            # 调用AI（走统一provider配置）
            result = await call_ai_with_fallback(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": dialogue_text}
                ]
            )
            response = result['choices'][0]['message']['content']

            if not response:
                logger.error("AI总结调用失败 - 未返回响应")
                return None

            # 解析JSON响应
            try:
                # 尝试提取JSON（可能包含其他文本）
                response_text = response.strip()
                if "```json" in response_text:
                    json_start = response_text.find("```json") + 7
                    json_end = response_text.find("```", json_start)
                    response_text = response_text[json_start:json_end].strip()
                elif "```" in response_text:
                    json_start = response_text.find("```") + 3
                    json_end = response_text.find("```", json_start)
                    response_text = response_text[json_start:json_end].strip()

                result = json.loads(response_text)

                # 验证必需字段
                if "summary" not in result:
                    logger.error("AI返回的JSON缺少summary字段")
                    return None

                # 确保key_events存在且是列表
                if "key_events" not in result or not isinstance(result["key_events"], list):
                    result["key_events"] = []

                return result

            except json.JSONDecodeError as e:
                logger.error(f"AI返回的JSON解析失败: {e}, 响应内容: {response}")
                return None

        except Exception as e:
            logger.error(f"AI总结调用异常: {e}", exc_info=True)
            return None

    def _format_dialogues_for_summary(self, dialogues: List[NPCDialogueHistory]) -> str:
        """
        格式化对话历史为文本

        Args:
            dialogues: 对话列表

        Returns:
            格式化后的对话文本
        """
        lines = ["=== 对话历史 ===\n"]
        for i, dialogue in enumerate(dialogues, 1):
            timestamp = dialogue.created_at.strftime("%m-%d %H:%M")
            lines.append(f"[{i}. {timestamp}]")
            lines.append(f"玩家: {dialogue.player_input}")
            lines.append(f"NPC: {dialogue.npc_response}")
            if dialogue.favorability_change != 0:
                lines.append(f"(好感度变化: {dialogue.favorability_change:+d})")
            lines.append("")  # 空行分隔

        return "\n".join(lines)

    async def _store_summary(
        self,
        npc_id: int,
        player_id: str,
        summary_content: str,
        from_dialogue_id: int,
        to_dialogue_id: int
    ) -> int:
        """
        存储对话总结

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            summary_content: 总结内容
            from_dialogue_id: 起始对话ID
            to_dialogue_id: 结束对话ID

        Returns:
            总结记录的ID
        """
        memory = await self.memory_repo.create_memory(
            npc_id=npc_id,
            player_id=player_id,
            memory_type="summary",
            content=summary_content,
            importance_score=5,  # 总结的默认重要性
            from_dialogue_id=from_dialogue_id,
            to_dialogue_id=to_dialogue_id
        )
        return memory.id

    async def _store_key_events(
        self,
        npc_id: int,
        player_id: str,
        key_events: List[Dict],
        from_dialogue_id: int,
        to_dialogue_id: int
    ) -> List[int]:
        """
        存储关键事件

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            key_events: 关键事件列表
            from_dialogue_id: 起始对话ID
            to_dialogue_id: 结束对话ID

        Returns:
            事件记录的ID列表
        """
        event_ids = []
        for event in key_events:
            try:
                memory = await self.memory_repo.create_memory(
                    npc_id=npc_id,
                    player_id=player_id,
                    memory_type="event",
                    content=event.get("description", ""),
                    event_type=event.get("event_type", "other"),
                    importance_score=event.get("importance", 5),
                    emotion_change=event.get("emotion_change", 0),
                    from_dialogue_id=from_dialogue_id,
                    to_dialogue_id=to_dialogue_id,
                    extra_metadata=event  # 存储完整事件数据
                )
                event_ids.append(memory.id)
            except Exception as e:
                logger.error(f"存储关键事件失败: {e}, 事件内容: {event}")

        return event_ids

    async def get_long_term_context(
        self,
        npc_id: int,
        player_id: str,
        include_summaries: int = 3,
        include_events: int = 5
    ) -> str:
        """
        获取长期记忆上下文（用于AI对话）

        Args:
            npc_id: NPC ID
            player_id: 玩家ID
            include_summaries: 包含的总结数量
            include_events: 包含的事件数量

        Returns:
            格式化的长期记忆上下文文本
        """
        try:
            # 获取最近的总结
            summaries = await self.memory_repo.get_recent_summaries(
                npc_id=npc_id,
                player_id=player_id,
                limit=include_summaries
            )

            # 获取重要事件
            events = await self.memory_repo.get_important_events(
                npc_id=npc_id,
                player_id=player_id,
                min_importance=6,
                limit=include_events
            )

            if not summaries and not events:
                return ""

            lines = ["【长期记忆】"]

            # 添加总结
            if summaries:
                lines.append("\n过往对话总结:")
                for i, summary in enumerate(reversed(summaries), 1):
                    time_desc = self._format_time_description(summary.created_at)
                    lines.append(f"- [{time_desc}] {summary.content}")

            # 添加关键事件
            if events:
                lines.append("\n重要事件:")
                for event in reversed(events):
                    time_desc = self._format_time_description(event.created_at)
                    emotion_mark = ""
                    if event.emotion_change > 0:
                        emotion_mark = f"(好感度+{event.emotion_change})"
                    elif event.emotion_change < 0:
                        emotion_mark = f"(好感度{event.emotion_change})"

                    lines.append(f"- [{time_desc}] {event.content} {emotion_mark}")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"获取长期记忆上下文失败: {e}", exc_info=True)
            return ""

    def _format_time_description(self, dt: datetime) -> str:
        """
        将时间转换为人类可读的描述

        Args:
            dt: datetime对象

        Returns:
            时间描述（如"3天前"、"1周前"）
        """
        now = datetime.now()
        delta = now - dt

        if delta.days == 0:
            return "今天"
        elif delta.days == 1:
            return "昨天"
        elif delta.days < 7:
            return f"{delta.days}天前"
        elif delta.days < 30:
            return f"{delta.days // 7}周前"
        else:
            return f"{delta.days // 30}个月前"
