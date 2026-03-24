"""AI对话生成服务"""
from typing import Optional, List
from datetime import datetime

from nonebot import logger

from ..models.npc import NPC
from ..models.npc_dialogue_history import NPCDialogueHistory
from ..dialogue.npc_personality import PersonalityTemplate
from ..ai_guide import call_zhipu_api
from ..config import config


class AIDialogueService:
    """使用智谱AI生成NPC对话的服务"""

    def __init__(self):
        """初始化AI对话服务"""
        ai_config = config.game_config.get("ai_dialogue", {})

        # AI配置
        self.provider = ai_config.get("provider", "zhipu")
        self.zhipu_config = ai_config.get("zhipu", {})
        self.ai302_config = ai_config.get("ai302", {})
        self.scnet_config = ai_config.get("scnet", {})
        self.volcengine_config = ai_config.get("volcengine", {})
        self.max_tokens = self.zhipu_config.get("max_tokens", 300)
        self.temperature = self.zhipu_config.get("temperature", 0.75)
        provider_configs = {"zhipu": self.zhipu_config, "ai302": self.ai302_config, "scnet": self.scnet_config, "volcengine": self.volcengine_config}
        provider_config = provider_configs.get(self.provider, self.zhipu_config)
        self.timeout = provider_config.get("timeout", 30)

        # 降级策略配置
        fallback_config = ai_config.get("fallback", {})
        self.fallback_enabled = fallback_config.get("enabled", True)
        self.fallback_provider = fallback_config.get("fallback_provider", "ai302")
        self.max_retries = fallback_config.get("max_retries", 1)

        # 对话历史配置
        history_config = ai_config.get("history", {})
        self.max_history_rounds = history_config.get("max_rounds", 10)

        # 内容安全配置
        safety_config = ai_config.get("safety", {})
        self.max_response_length = safety_config.get("max_response_length", 200)
        self.min_response_length = safety_config.get("min_response_length", 10)

    async def generate_dialogue(
        self,
        npc: NPC,
        personality: PersonalityTemplate,
        question: str,
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: Optional[dict] = None
    ) -> tuple[str, int]:
        """
        生成NPC对自然对话的回复

        Args:
            npc: NPC对象
            personality: NPC人设
            question: 玩家提问
            dialogue_history: 对话历史
            favorability: 当前好感度
            context: 附加上下文

        Returns:
            (NPC回复文本, 消耗的token数)
        """
        try:
            # 构建系统提示词
            system_prompt = personality.build_system_prompt(
                favorability=favorability,
                context=context or {}
            )

            # 添加长期记忆上下文（如果context中提供）
            long_term_memory = context.get("long_term_memory", "") if context else ""
            if long_term_memory:
                system_prompt += f"\n\n{long_term_memory}"

            # 构建messages列表，包含对话历史
            messages = [{"role": "system", "content": system_prompt}]

            # 添加对话历史（最近N轮），保持对话的连续性
            if dialogue_history:
                # 只取最近的对话，避免token过多
                recent_history = dialogue_history[-(self.max_history_rounds):]
                for history in recent_history:
                    # 添加玩家消息
                    messages.append({"role": "user", "content": history.player_input})
                    # 添加NPC回复
                    messages.append({"role": "assistant", "content": history.npc_response})

            # 添加当前的用户问题
            messages.append({"role": "user", "content": question})

            # 调用AI（支持fallback降级）
            result = await self._call_ai_with_fallback(messages)

            # 提取回复内容
            response = result['choices'][0]['message']['content'].strip()

            # 获取token使用情况
            tokens_used = result.get('usage', {}).get('total_tokens', 0)

            # 验证回复质量
            if not self._validate_response(response):
                logger.warning(f"AI回复质量验证失败，NPC: {npc.name}, 回复: {response}")
                return self._get_fallback_response(npc, favorability), 0

            return response, tokens_used

        except Exception as e:
            logger.error(f"AI对话生成失败: {type(e).__name__}: {str(e)}", exc_info=True)
            # 降级方案：返回预设回复
            return self._get_fallback_response(npc, favorability), 0

    async def generate_roleplay_response(
        self,
        npc: NPC,
        personality: PersonalityTemplate,
        action: str,
        game_output: str,
        dialogue_history: List[NPCDialogueHistory],
        favorability: int,
        context: Optional[dict] = None
    ) -> tuple[str, int]:
        """
        生成NPC执行游戏指令后的角色扮演回复

        Args:
            npc: NPC对象
            personality: NPC人设
            action: 执行的动作
            game_output: 游戏执行结果
            dialogue_history: 对话历史
            favorability: 当前好感度
            context: 附加上下文

        Returns:
            (NPC回复文本, 消耗的token数)
        """
        try:
            # 构建系统提示词
            system_prompt = personality.build_system_prompt(
                favorability=favorability,
                context=context or {}
            )

            # 添加指令执行风格指导
            system_prompt += """

执行完了，就顺口说几句你的感受，一两句台词就够，不用多。如果有动作就用括号带一笔，比如（接过东西看了看）。别拿这当正式汇报，随意聊就行，不超过100字。"""

            # 构建用户消息
            user_message = f"刚才{action}了，结果是：{game_output}"

            # 调用AI（支持fallback降级）
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ]

            result = await self._call_ai_with_fallback(messages)

            # 提取回复内容
            response = result['choices'][0]['message']['content'].strip()

            # 获取token使用情况
            tokens_used = result.get('usage', {}).get('total_tokens', 0)

            # 验证回复质量
            if not self._validate_response(response):
                logger.warning(f"AI角色扮演回复质量验证失败，NPC: {npc.name}, 回复: {response}")
                return self._get_roleplay_fallback_response(npc, action), 0

            return response, tokens_used

        except Exception as e:
            logger.error(f"AI角色扮演回复生成失败: {type(e).__name__}: {str(e)}", exc_info=True)
            # 降级方案：返回预设回复
            return self._get_roleplay_fallback_response(npc, action), 0

    def _build_history_context(self, dialogue_history: List[NPCDialogueHistory]) -> str:
        """构建对话历史上下文"""
        if not dialogue_history:
            return "这是你们的第一次对话。"

        # 只取最近的N轮对话
        recent_history = dialogue_history[-self.max_history_rounds:]

        context_lines = ["最近的对话历史："]
        for history in recent_history:
            context_lines.append(f"玩家: {history.player_input}")
            # 使用NPC回复字段，避免懒加载问题
            context_lines.append(f"NPC: {history.npc_response}")

        return "\n".join(context_lines)

    def _validate_response(self, response: str) -> bool:
        """验证回复质量"""
        # 检查长度
        if len(response) < self.min_response_length:
            return False

        if len(response) > self.max_response_length:
            return False

        # 检查是否为空或仅包含空白字符
        if not response.strip():
            return False

        return True

    def _get_fallback_response(self, npc: NPC, favorability: int) -> str:
        """获取降级回复（自然对话）"""
        if favorability <= 20:
            return f"{npc.name}冷漠地看了你一眼，没有多说什么。"
        elif favorability <= 40:
            return f"{npc.name}客气地点了点头。"
        elif favorability <= 60:
            return f"{npc.name}友好地和你交谈了几句。"
        elif favorability <= 80:
            return f"{npc.name}亲切地回应了你的问题。"
        else:
            return f"{npc.name}热情地与你交流。"

    def _get_roleplay_fallback_response(self, npc: NPC, action: str) -> str:
        """获取降级回复（角色扮演）"""
        return f"{npc.name}点了点头，按照你的要求执行了操作。"

    def calculate_cost(self, tokens_used: int) -> int:
        """
        计算AI调用成本（以分为单位）

        智谱AI GLM-4.5-Flash定价（参考）:
        - 输入: 0.1元/百万token
        - 输出: 0.1元/百万token

        Args:
            tokens_used: 使用的token数

        Returns:
            成本（以分为单位，人民币）
        """
        # 简化计算：假设输入输出各占一半
        # 成本 = (tokens_used / 1000000) * 0.1元 * 100分
        cost_cents = int((tokens_used / 1000000) * 0.1 * 100)
        return max(cost_cents, 1)  # 最少1分

    async def _call_ai_with_fallback(self, messages: list, provider: str = None) -> dict:
        """
        调用AI API并支持fallback降级机制

        Args:
            messages: 对话消息列表
            provider: 指定provider（None则使用默认）

        Returns:
            AI API返回结果

        Raises:
            Exception: 所有provider均失败时抛出异常
        """
        from ..ai_guide import call_zhipu_api, call_302ai_api, call_scnet_api, call_volcengine_api

        # 确定主provider
        primary_provider = provider or self.provider
        errors = []

        # 尝试主provider
        try:
            if primary_provider == "zhipu":
                zhipu_model = self.zhipu_config.get("model", "GLM-4-Flash-250414")
                logger.info(f"[AIDialogue] 使用智谱AI调用, model={zhipu_model}")
                result = await call_zhipu_api(
                    messages,
                    model=zhipu_model,
                    timeout=self.timeout,
                    temperature=self.temperature
                )
                logger.info(f"[AIDialogue] 智谱AI调用成功")
                return result
            elif primary_provider == "ai302":
                ai302_model = self.ai302_config.get("model", "gpt-3.5-turbo")
                logger.info(f"[AIDialogue] 使用302.ai调用, model={ai302_model}")
                result = await call_302ai_api(
                    messages,
                    model=ai302_model,
                    timeout=self.timeout,
                    temperature=self.temperature
                )
                logger.info(f"[AIDialogue] 302.ai调用成功")
                return result
            elif primary_provider == "scnet":
                scnet_model = self.scnet_config.get("model", "DeepSeek-R1-Distill-Qwen-7B")
                logger.info(f"[AIDialogue] 使用scnet调用, model={scnet_model}")
                result = await call_scnet_api(
                    messages,
                    model=scnet_model,
                    timeout=self.timeout,
                    temperature=self.temperature
                )
                logger.info(f"[AIDialogue] scnet调用成功")
                return result
            elif primary_provider == "volcengine":
                volc_model = self.volcengine_config.get("model", "ep-20260321201048-h78tm")
                logger.info(f"[AIDialogue] 使用火山引擎调用, model={volc_model}")
                result = await call_volcengine_api(
                    messages,
                    model=volc_model,
                    timeout=self.timeout,
                    temperature=self.temperature
                )
                logger.info(f"[AIDialogue] 火山引擎调用成功")
                return result
            else:
                raise ValueError(f"不支持的provider: {primary_provider}")

        except Exception as e:
            error_msg = f"{primary_provider} 调用失败: {type(e).__name__}: {str(e)}"
            logger.warning(f"[AIDialogue] {error_msg}")
            errors.append(error_msg)

            # 如果fallback未启用，直接抛出异常
            if not self.fallback_enabled:
                raise

            # 尝试fallback provider
            try:
                fallback = self.fallback_provider
                if fallback == primary_provider:
                    # fallback provider与主provider相同，直接抛出异常
                    raise Exception(f"主provider和fallback provider相同，无法降级")

                logger.warning(f"[AIDialogue] 尝试降级到备用provider: {fallback}")

                if fallback == "zhipu":
                    result = await call_zhipu_api(
                        messages,
                        model=self.zhipu_config.get("model", "GLM-4-Flash-250414"),
                        timeout=self.timeout,
                        temperature=self.temperature
                    )
                    logger.info(f"[AIDialogue] 备用provider {fallback} 调用成功")
                    return result
                elif fallback == "ai302":
                    result = await call_302ai_api(
                        messages,
                        model=self.ai302_config.get("model", "gpt-3.5-turbo"),
                        timeout=self.timeout,
                        temperature=self.temperature
                    )
                    logger.info(f"[AIDialogue] 备用provider {fallback} 调用成功")
                    return result
                elif fallback == "scnet":
                    result = await call_scnet_api(
                        messages,
                        model=self.scnet_config.get("model", "DeepSeek-R1-Distill-Qwen-7B"),
                        timeout=self.timeout,
                        temperature=self.temperature
                    )
                    logger.info(f"[AIDialogue] 备用provider {fallback} 调用成功")
                    return result
                elif fallback == "volcengine":
                    result = await call_volcengine_api(
                        messages,
                        model=self.volcengine_config.get("model", "ep-20260321201048-h78tm"),
                        timeout=self.timeout,
                        temperature=self.temperature
                    )
                    logger.info(f"[AIDialogue] 备用provider {fallback} 调用成功")
                    return result
                else:
                    raise ValueError(f"不支持的fallback provider: {fallback}")

            except Exception as fallback_error:
                fallback_error_msg = f"{fallback} 调用失败: {type(fallback_error).__name__}: {str(fallback_error)}"
                logger.error(f"[AIDialogue] {fallback_error_msg}")
                errors.append(fallback_error_msg)

                # 所有provider都失败，抛出综合异常
                raise Exception(f"所有AI provider均失败: {'; '.join(errors)}")
