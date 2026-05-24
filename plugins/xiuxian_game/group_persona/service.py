"""Text-only group persona reply service."""

from __future__ import annotations

import asyncio
import random
import re
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from math import ceil
from typing import Deque

import aiohttp
from nonebot import logger

from ..ai_guide import call_ai_with_fallback
from .config import GroupPersonaConfig, load_group_persona_config


COMMAND_PREFIXES = (
    "帮助",
    "完整帮助",
    "注册",
    "面板",
    "角色",
    "背包",
    "修炼",
    "突破",
    "闭关",
    "出关",
    "签到",
    "排行榜",
    "问",
    "/",
    "!",
    "！",
)


@dataclass(frozen=True)
class PersonaIncomingMessage:
    group_id: str
    user_id: str
    username: str
    text: str
    to_me: bool = False


@dataclass(frozen=True)
class PersonaStoredMessage:
    user_id: str
    username: str
    text: str
    created_at: float


@dataclass(frozen=True)
class TriggerDecision:
    should_reply: bool
    reason: str = ""


class GroupPersonaService:
    """Keeps short text history and decides when to reply like a group member."""

    def __init__(self) -> None:
        self._history: dict[str, Deque[PersonaStoredMessage]] = defaultdict(deque)
        self._last_reply_at: dict[str, float] = {}
        self._ambient_message_counts: dict[str, int] = defaultdict(int)
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def get_config(self) -> GroupPersonaConfig:
        return load_group_persona_config()

    def record_message(self, message: PersonaIncomingMessage, cfg: GroupPersonaConfig) -> None:
        history = self._history[message.group_id]
        history.append(
            PersonaStoredMessage(
                user_id=message.user_id,
                username=message.username,
                text=message.text,
                created_at=time.time(),
            )
        )
        while len(history) > cfg.max_history_messages:
            history.popleft()
        self._ambient_message_counts[message.group_id] += 1

    def clear_group(self, group_id: str) -> None:
        self._history.pop(group_id, None)
        self._last_reply_at.pop(group_id, None)
        self._ambient_message_counts.pop(group_id, None)

    def is_enabled_for_group(self, group_id: str, cfg: GroupPersonaConfig) -> bool:
        return cfg.enabled and group_id in cfg.group_whitelist

    def should_ignore_text(self, text: str, cfg: GroupPersonaConfig) -> bool:
        normalized = text.strip()
        if not normalized:
            return True
        if len(normalized) > 500:
            return True
        if not cfg.ignore_commands:
            return False
        return any(normalized.startswith(prefix) for prefix in COMMAND_PREFIXES)

    def decide_trigger(
        self,
        message: PersonaIncomingMessage,
        cfg: GroupPersonaConfig,
        *,
        now: float | None = None,
        rng: random.Random | None = None,
    ) -> TriggerDecision:
        current = time.time() if now is None else now
        last_reply_at = self._last_reply_at.get(message.group_id, 0.0)
        if current - last_reply_at < cfg.min_interval_seconds:
            return TriggerDecision(False, "cooldown")

        mention_hit = message.to_me or any(alias and alias in message.text for alias in cfg.aliases)
        probability = cfg.mention_reply_probability if mention_hit else cfg.reply_probability
        if probability <= 0:
            return TriggerDecision(False, "probability_zero")

        if not mention_hit:
            threshold = self._get_ambient_message_threshold(cfg)
            if self._ambient_message_counts.get(message.group_id, 0) < threshold:
                return TriggerDecision(False, "wait_more_messages")
        else:
            sampler = rng or random
            if sampler.random() > probability:
                return TriggerDecision(False, "probability_skip")

        return TriggerDecision(True, "mention" if mention_hit else "ambient")

    def _get_ambient_message_threshold(self, cfg: GroupPersonaConfig) -> int:
        frequency = max(0.01, min(1.0, cfg.reply_probability))
        return max(1, int(ceil(1.0 / frequency)))

    async def maybe_reply(self, message: PersonaIncomingMessage) -> str | None:
        cfg = self.get_config()
        if not self.is_enabled_for_group(message.group_id, cfg):
            return None
        if self.should_ignore_text(message.text, cfg):
            return None

        self.record_message(message, cfg)
        decision = self.decide_trigger(message, cfg)
        if not decision.should_reply:
            return None

        lock = self._locks[message.group_id]
        if lock.locked():
            return None

        async with lock:
            fresh_cfg = self.get_config()
            if not self.is_enabled_for_group(message.group_id, fresh_cfg):
                return None
            response = await self._generate_reply(message.group_id, fresh_cfg, decision.reason)
            if not response:
                self._ambient_message_counts[message.group_id] = 0
                return None
            self._ambient_message_counts[message.group_id] = 0
            self._last_reply_at[message.group_id] = time.time()
            return response

    async def _generate_reply(self, group_id: str, cfg: GroupPersonaConfig, trigger_reason: str) -> str:
        if cfg.timing_gate_enabled and trigger_reason == "ambient":
            gate_decision = await self._run_timing_gate(group_id, cfg)
            if gate_decision != "CONTINUE":
                return ""

        messages = [
            {"role": "system", "content": build_reply_system_prompt(cfg)},
            {"role": "user", "content": self._build_reply_user_prompt(group_id, cfg, trigger_reason)},
        ]

        try:
            result = await call_ai_with_fallback(messages)
            content = result["choices"][0]["message"]["content"]
        except (aiohttp.ClientError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("[GroupPersona] AI reply failed: %s", exc)
            return ""

        return sanitize_reply(str(content), cfg.max_response_length)

    async def _run_timing_gate(self, group_id: str, cfg: GroupPersonaConfig) -> str:
        messages = [
            {"role": "system", "content": build_timing_gate_system_prompt(cfg)},
            {"role": "user", "content": self._build_timing_gate_user_prompt(group_id, cfg)},
        ]

        try:
            result = await call_ai_with_fallback(messages)
            content = result["choices"][0]["message"]["content"]
        except (aiohttp.ClientError, TimeoutError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.warning("[GroupPersona] Timing gate failed: %s", exc)
            return "NO_REPLY"

        return parse_timing_gate_decision(str(content))

    def _format_recent_history(self, group_id: str, cfg: GroupPersonaConfig) -> str:
        history = list(self._history.get(group_id, ()))
        lines = [
            f"{item.username}：{item.text}"
            for item in history[-cfg.max_history_messages :]
            if item.text.strip()
        ]
        return "\n".join(lines)

    def _build_timing_gate_user_prompt(self, group_id: str, cfg: GroupPersonaConfig) -> str:
        return (
            "最近群聊：\n"
            + self._format_recent_history(group_id, cfg)
            + "\n\n只判断现在是否适合开口。"
        )

    def _build_reply_user_prompt(self, group_id: str, cfg: GroupPersonaConfig, trigger_reason: str) -> str:
        return (
            f"触发原因：{trigger_reason}\n"
            "最近群聊：\n"
            + self._format_recent_history(group_id, cfg)
            + "\n\n先判断现在是不是适合插话；如果不自然，只输出 NO_REPLY。"
        )


def _identity_prompt(cfg: GroupPersonaConfig) -> str:
    aliases = "、".join(cfg.aliases)
    return (
        f"你是QQ群里的普通群友，名字叫{cfg.persona_name}，也可能被叫作{aliases}。\n"
        "你不是助手，不是AI，不要自称机器人、系统或客服。\n"
    )


def build_timing_gate_system_prompt(cfg: GroupPersonaConfig) -> str:
    return (
        _identity_prompt(cfg)
        + "你的任务不是回复，而是判断现在该不该说话。\n"
        "你需要分析当前多人聊天节奏：大家是在互相聊天、自言自语、连续补充，还是话题已经适合收一句。\n"
        "你的定位是游戏群里偶尔冒泡的气氛位，更适合在一小段聊天后做一句总结、吐槽、补刀、接梗。\n"
        "如果别人还没说完、正在处理游戏指令、话题与你无关、插话会显得突兀、或者你接不上，就不要说话。\n"
        "只有在你像真实群友一样自然补一句能活跃气氛、不打断游戏节奏时，才选择继续。\n"
        "只输出一个词：CONTINUE 或 NO_REPLY。不要解释。"
    )


def build_reply_system_prompt(cfg: GroupPersonaConfig) -> str:
    return (
        _identity_prompt(cfg)
        + "你的目标不是回答问题，而是在游戏群里低频冒泡：总结一句、吐槽一句、补刀一句、接个梗，让气氛轻一点。\n"
        "先判断大家是在彼此聊天、自言自语，还是在跟你说话；不要盲目插话，也不要把每句话都当成提问。\n"
        "如果对方像是还没说完，或者你接不上，输出 NO_REPLY。\n"
        "优先根据最近几句做轻微总结、吐槽、复读式接梗或一句短短的气氛话；不要抢游戏机器人本职，不要认真讲攻略。\n"
        "说话风格要贴近最近聊天记录：可以顺着群里的语气、短句、口头禅和小圈子黑话自然发挥，但不要解释你在模仿。\n"
        "不要使用GPT式长篇说明、Markdown、分点、总结、建议清单、客套开场。\n"
        "不要输出昵称前缀、冒号、引号或括号说明。\n"
        "单次最多两句话；可以很短，可以吐槽，可以含糊，像真实群友随手发的消息。"
    )


def parse_timing_gate_decision(text: str) -> str:
    normalized = text.strip().upper()
    if "CONTINUE" in normalized and "NO_REPLY" not in normalized:
        return "CONTINUE"
    return "NO_REPLY"


def sanitize_reply(text: str, max_length: int) -> str:
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()
    cleaned = cleaned.strip("` \n\r\t")
    if cleaned.upper() in {"NO_REPLY", "NOREPLY"} or cleaned in {"不回复", "空字符串", "沉默"}:
        return ""
    cleaned = re.sub(r"^（?[^：:\n]{1,20}[：:]\s*", "", cleaned)
    cleaned = cleaned.replace("\r", "\n")
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    cleaned = " ".join(lines)
    cleaned = cleaned.strip("\"'“”‘’")
    if not cleaned:
        return ""
    if len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip()
    return cleaned


group_persona_service = GroupPersonaService()
