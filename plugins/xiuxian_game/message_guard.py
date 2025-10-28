"""全局事件去重与消息去重守卫

- 事件级：使用 QQ 回调最外层 id 做幂等去重（适用于所有回调事件）
- 消息级：对相同用户相同纯文本在短时间内的重复触发做二次保护

注意：这不是命令匹配器，故不受“命令必须 block=True”的约束。
"""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Tuple, Any, Optional

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
    _HAS_PREPROCESSOR = True
except ImportError:
    _HAS_PREPROCESSOR = False


if _HAS_PREPROCESSOR:

    @run_preprocessor  # type: ignore[misc]
    async def _event_id_dedup(bot: Bot, event: Event, state: Dict[str, Any]) -> None:
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


# —— 仍保留消息级二次保护（短窗口重复输入） ——

def _build_msg_key(event: MessageEvent) -> str:
    return f"{event.get_user_id()}|{event.get_plaintext().strip()}"


guard = on_message(priority=0, block=False)


@guard.handle()
async def _(matcher: Matcher, event: MessageEvent) -> None:
    now = time.monotonic()
    _cleanup_messages(now)

    key = _build_msg_key(event)
    last_seen = _message_cache.get(key)

    if last_seen is not None and now - last_seen <= _MSG_TTL_SECONDS:
        logger.debug("Duplicate message intercepted: %s", key)
        matcher.stop_propagation()
        return

    _message_cache[key] = now
    _message_queue.append((now, key))
