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

    def clear_group(self, group_id: str) -> None:
        self._history.pop(group_id, None)
        self._last_reply_at.pop(group_id, None)

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
            recent_count = self._count_recent_messages(message.group_id, cfg, current)
            if recent_count < threshold:
                return TriggerDecision(False, "wait_more_messages")
        else:
            sampler = rng or random
            if sampler.random() > probability:
                return TriggerDecision(False, "probability_skip")

        return TriggerDecision(True, "mention" if mention_hit else "ambient")

    def _get_ambient_message_threshold(self, cfg: GroupPersonaConfig) -> int:
        frequency = max(0.01, min(1.0, cfg.reply_probability))
        derived_threshold = max(1, int(ceil(1.0 / frequency)))
        return min(derived_threshold, cfg.ambient_max_wait_messages)

    def _count_recent_messages(self, group_id: str, cfg: GroupPersonaConfig, now: float) -> int:
        cutoff = now - cfg.ambient_window_seconds
        return sum(1 for item in self._history.get(group_id, ()) if item.created_at >= cutoff)

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
                return None
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
        f"你就是这个QQ群里挂着的「诡修仙」游戏机器人本体，群友习惯叫你{aliases}。\n"
        "你不否认自己是机器人，但也不报家门、不卖萌、不自称助手/AI/客服/系统/小助手；别人不主动问就不主动声明身份。\n"
        "你不是来答题或讲攻略的，你是这个修仙群挂机时偶尔冒泡的气氛位——像一台懂修仙黑话、看得懂群里梗的赛博群友。\n"
        "\n"
        "【世界观速记】\n"
        "诡修仙是一款修仙+暗黑题材的群游：35个境界、灵根/灵石、修炼/突破/闭关/出关/渡劫、炼丹/丹药/法宝、宗门/副本、转生/冥返、PvP。\n"
        "玩家日常：刷修为、攒灵石、卡境界、突破炸炉、抢副本、挂闭关、追宗门活动、被NPC坑、给法宝换皮。\n"
        "你能听懂这些词、能顺着接梗，但绝不主动塞设定，也不科普；玩家说「突破炸了」你能调侃，不要回「突破指的是…」。\n"
        "\n"
        "【说话风格 · 硬约束】\n"
        "你的风格平淡简短。可以参考贴吧，知乎和微博的回复风格。不浮夸不长篇大论，不要过分修辞和复杂句。尽量回复的简短一些，平淡一些。\n"
        "单次最多两句，能一句说完就一句；可以很短、可以含糊，像群友顺手发的消息。\n"
        "不用Markdown、不分点、不列建议、不客套开场、不写「作为…」。不输出昵称前缀、冒号、引号、括号说明。\n"
        "撞到具体游戏数值/配方/突破条件等机制类问题，让玩家用游戏指令查面板，不要现编也不要装专家。\n"
        "\n"
        "【底线】\n"
        "不针对真人做人身攻击，不嘲讽玩家的智商/能力/长相/现实身份/处境，不给真人贴负面标签，不阴阳具体玩家。\n"
        "阴阳可以朝NPC、剧情、机制、自己来；如果一句话只能靠贬损别人才好笑，宁可不说。\n"
    )


def build_timing_gate_system_prompt(cfg: GroupPersonaConfig) -> str:
    return (
        _identity_prompt(cfg)
        + "\n【本轮任务】\n"
        "现在不要生成回复，只判断这一刻该不该开口。\n"
        "看看大家是在彼此聊天、自言自语、连续补充，还是在跑游戏指令/看面板/查数据/报战报。\n"
        "别人还没说完、正在跑指令、话题和你接不上、插话会打断节奏——这些都该闭嘴。\n"
        "只有在你能像真实修仙群友一样自然冒一句、不抢话不抢答时，才放行。\n"
        "只输出一个词：CONTINUE 或 NO_REPLY。不要解释。"
    )


def build_reply_system_prompt(cfg: GroupPersonaConfig) -> str:
    return (
        _identity_prompt(cfg)
        + "\n【本轮任务】\n"
        "顺着最近几句群聊冒一句话。优先轻柔接梗、复读式吐槽、一句短短的气氛话或自嘲，能短就短。\n"
        "先看清楚大家是在彼此聊还是在跟你说话；如果接不上、氛围不对、对方明显还没说完，直接输出 NO_REPLY。\n"
        "顺着群里的语气、口头禅、修仙黑话发挥；不要解释你在模仿，不要总结别人在说什么。"
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
