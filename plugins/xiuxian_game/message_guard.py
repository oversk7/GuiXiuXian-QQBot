"""全局事件去重、消息去重与速率限制守卫

三层防护：
1. 事件级去重：使用 QQ 回调最外层 id 做幂等去重（适用于所有回调事件）
2. 消息级去重：对相同用户相同纯文本在短时间内的重复触发做二次保护
3. 指令速率限制：对高频指令（move、explore 等）做统一速率控制

注意：这不是命令匹配器，故不受“命令必须 block=True”的约束。
"""
from __future__ import annotations

import time
from collections import deque, defaultdict
from typing import Deque, Dict, Tuple, Any, Optional
from dataclasses import dataclass

from nonebot import logger, on_message
from nonebot.matcher import Matcher
from nonebot.adapters.qq import MessageEvent

# -------- 事件级去重（基于回调最外层 id） --------
_EVENT_ID_TTL_SECONDS: float = 300.0  # 5 分钟，覆盖链路重试的重复推送
_event_id_cache: Dict[str, float] = {}
_event_id_queue: Deque[Tuple[float, str]] = deque()

# -------- 消息级去重（相同用户+纯文本） --------
_MSG_TTL_SECONDS: float = 1.5
_message_cache: Dict[str, float] = {}
_message_queue: Deque[Tuple[float, str]] = deque()

# -------- 指令速率限制配置 --------
@dataclass
class RateLimitConfig:
    """速率限制配置"""
    max_requests: int  # 时间窗口内最大请求数
    time_window: float  # 时间窗口（秒）
    cooldown: float = 0.0  # 单次操作最小间隔（秒）


# 指令速率限制注册表
_COMMAND_RATE_LIMITS: Dict[str, RateLimitConfig] = {
    "move": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "explore": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "探索": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "上": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "下": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "左": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "右": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
    "下一层": RateLimitConfig(max_requests=25, time_window=30.0, cooldown=0.9),
}

# 用户指令请求历史 {user_id: {command: deque[timestamp]}}
_command_history: Dict[str, Dict[str, Deque[float]]] = defaultdict(lambda: defaultdict(deque))
# 用户指令最后请求时间 {user_id: {command: timestamp}}
_command_last_time: Dict[str, Dict[str, float]] = defaultdict(dict)


def _cleanup_event_ids(now: float) -> None:
    """根据 TTL 清理事件 id 缓存。"""
    while _event_id_queue:
        ts, key = _event_id_queue[0]
        if now - ts <= _EVENT_ID_TTL_SECONDS:
            break
        _event_id_queue.popleft()
        if _event_id_cache.get(key) == ts:
            _event_id_cache.pop(key, None)


def _cleanup_messages(now: float) -> None:
    """根据 TTL 清理消息去重缓存。"""
    while _message_queue:
        ts, key = _message_queue[0]
        if now - ts <= _MSG_TTL_SECONDS:
            break
        _message_queue.popleft()
        if _message_cache.get(key) == ts:
            _message_cache.pop(key, None)

# 仅打印一次“外层id格式异常”日志，避免刷屏
_outer_id_format_warned: bool = False

def _normalize_outer_id(value: Any) -> Optional[str]:
    global _outer_id_format_warned
    if isinstance(value, (str, int)):
        s = str(value)
        # 经验规则：应包含事件类型前缀+冒号，且长度较长
        if (":" in s) and (len(s) >= 20):
            return s
        if not _outer_id_format_warned:
            logger.debug("Outer id format not recognized, skip dedup: %r", s)
            _outer_id_format_warned = True
    return None


# —— 最外层 id 提取 ——

def _extract_outer_event_id(event: Any) -> Optional[str]:
    """尽可能从适配器事件中提取“最外层 id”。

    适配器实现可能不同，按以下顺序尝试：
    1) 直接属性 event.id
    2) pydantic 的 model_dump()/dict() 返回的字典中的 'id'
    3) 字典中的 header.id
    若均不可得，返回 None。
    """
    # 1) 直接属性
    outer_id = _normalize_outer_id(getattr(event, "id", None))
    if outer_id:
        return outer_id

    # 2) model_dump/by_alias
    data: Optional[dict] = None
    if hasattr(event, "model_dump"):
        try:
            data = event.model_dump(mode="python", by_alias=True)
        except (TypeError, ValueError):
            data = None
    elif hasattr(event, "dict"):
        try:
            data = event.dict(by_alias=True)  # type: ignore[attr-defined]
        except (TypeError, ValueError):
            data = None

    if isinstance(data, dict):
        candidate = data.get("id")
        outer_id = _normalize_outer_id(candidate)
        if outer_id:
            return outer_id
        header = data.get("header") if isinstance(data.get("header"), dict) else None
        if header:
            outer_id = _normalize_outer_id(header.get("id"))
            if outer_id:
                return outer_id

    return None


# —— 使用 Preprocessor 守卫所有回调事件 ——
try:
    from nonebot.message import run_preprocessor  # type: ignore
    from nonebot.exception import IgnoredException  # type: ignore
    from nonebot.adapters import Bot, Event  # type: ignore
    from nonebot.typing import T_State
    _HAS_PREPROCESSOR = True
except ImportError:
    _HAS_PREPROCESSOR = False


if _HAS_PREPROCESSOR:

    @run_preprocessor  # type: ignore[misc]
    async def _event_id_dedup(bot: Bot, event: Event, state: T_State) -> None:
        now = time.monotonic()
        _cleanup_event_ids(now)

        outer_id = _extract_outer_event_id(event)
        if not outer_id:
            return  # 无法提取则不处理，交由后续逻辑

        last_seen = _event_id_cache.get(outer_id)
        if last_seen is not None and now - last_seen <= _EVENT_ID_TTL_SECONDS:
            logger.debug("Duplicate outer event id intercepted: %s", outer_id)
            # 直接忽略本次事件，避免所有匹配器重复处理
            raise IgnoredException("duplicate outer id")

        _event_id_cache[outer_id] = now
        _event_id_queue.append((now, outer_id))


# —— 指令速率限制检查 ——

def _extract_command(text: str) -> Optional[str]:
    """从消息文本中提取指令名称（第一个词）"""
    text = text.strip()
    if not text:
        return None
    # 取第一个空格前的内容作为指令
    parts = text.split(maxsplit=1)
    return parts[0] if parts else None


def _check_command_rate_limit(user_id: str, command: str, now: float) -> Tuple[bool, Optional[str]]:
    """检查指令速率限制

    Returns:
        (是否允许, 错误消息)
    """
    config = _COMMAND_RATE_LIMITS.get(command)
    if not config:
        return True, None

    # 检查冷却时间
    if config.cooldown > 0:
        last_time = _command_last_time[user_id].get(command, 0.0)
        if now - last_time < config.cooldown:
            remaining = config.cooldown - (now - last_time)
            return False, f"⏳ 操作过于频繁，请等待 {remaining:.1f} 秒后再试"

    # 检查滑动窗口
    if config.max_requests > 0 and config.time_window > 0:
        history = _command_history[user_id][command]

        # 清理过期记录
        cutoff_time = now - config.time_window
        while history and history[0] < cutoff_time:
            history.popleft()

        # 检查是否超过限制
        if len(history) >= config.max_requests:
            return False, f"⚠️ 操作过于频繁，请在 {config.time_window:.0f} 秒内最多操作 {config.max_requests} 次"

    return True, None


def _record_command_request(user_id: str, command: str, now: float) -> None:
    """记录指令请求"""
    config = _COMMAND_RATE_LIMITS.get(command)
    if not config:
        return

    # 记录最后请求时间
    _command_last_time[user_id][command] = now

    # 记录到滑动窗口
    if config.max_requests > 0 and config.time_window > 0:
        _command_history[user_id][command].append(now)


# —— 消息级二次保护（短窗口重复输入） + 指令速率限制 ——

def _build_msg_key(event: MessageEvent) -> str:
    return f"{event.get_user_id()}|{event.get_plaintext().strip()}"


guard = on_message(priority=0, block=False)


@guard.handle()
async def _(matcher: Matcher, event: MessageEvent) -> None:
    now = time.monotonic()
    _cleanup_messages(now)

    user_id = event.get_user_id()
    text = event.get_plaintext().strip()

    # 第一层：消息去重（相同用户+相同文本）
    key = _build_msg_key(event)
    last_seen = _message_cache.get(key)

    if last_seen is not None and now - last_seen <= _MSG_TTL_SECONDS:
        logger.debug("Duplicate message intercepted: %s", key)
        matcher.stop_propagation()
        return

    _message_cache[key] = now
    _message_queue.append((now, key))

    # 第二层：指令速率限制
    command = _extract_command(text)
    if command:
        allowed, error_msg = _check_command_rate_limit(user_id, command, now)
        if not allowed:
            logger.debug("Command rate limit exceeded: user=%s, command=%s", user_id, command)
            # 直接回复错误消息并阻止传播
            await matcher.send(error_msg)
            matcher.stop_propagation()
            return

        # 记录本次请求
        _record_command_request(user_id, command, now)
