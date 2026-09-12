"""QQ 回调事件幂等守卫，按平台事件 ID 去重。"""

from __future__ import annotations

import time
from collections import deque
from typing import Any

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot.exception import IgnoredException
from nonebot.message import event_preprocessor
from nonebot.typing import T_State


_EVENT_ID_TTL_SECONDS: float = 300.0
_event_id_cache: dict[str, float] = {}
_event_id_queue: deque[tuple[float, str]] = deque()


def _cleanup_event_ids(now: float) -> None:
    """根据 TTL 清理事件 id 缓存。"""
    while _event_id_queue:
        ts, key = _event_id_queue[0]
        if now - ts < _EVENT_ID_TTL_SECONDS:
            break
        _event_id_queue.popleft()
        if _event_id_cache.get(key) == ts:
            _event_id_cache.pop(key, None)


def _normalize_outer_id(value: Any) -> str | None:
    if not isinstance(value, (str, int)):
        return None
    normalized = str(value).strip()
    return normalized if len(normalized) >= 8 else None


def _extract_outer_event_id(event: Any) -> str | None:
    # QQ Adapter 1.7.2 把 Dispatch payload.id 写入 event_id；消息 id 仅作回退。
    direct = _normalize_outer_id(getattr(event, "event_id", None))
    if direct:
        return direct

    data = None
    if hasattr(event, "model_dump"):
        try:
            data = event.model_dump(mode="python", by_alias=True)
        except (TypeError, ValueError):
            data = None
    elif hasattr(event, "dict"):
        try:
            data = event.dict(by_alias=True)
        except (TypeError, ValueError):
            data = None
    if not isinstance(data, dict):
        return _normalize_outer_id(getattr(event, "id", None))
    direct = _normalize_outer_id(data.get("event_id"))
    if direct:
        return direct
    header = data.get("header")
    direct = _normalize_outer_id(header.get("id")) if isinstance(header, dict) else None
    if direct:
        return direct
    return _normalize_outer_id(getattr(event, "id", None) or data.get("id"))


@event_preprocessor
async def _event_id_dedup(bot: Bot, event: Event, state: T_State) -> None:
    now = time.monotonic()
    _cleanup_event_ids(now)

    outer_id = _extract_outer_event_id(event)
    if not outer_id:
        return
    if outer_id in _event_id_cache:
        logger.debug(f"Duplicate outer event id intercepted: {outer_id}")
        raise IgnoredException("duplicate outer id")

    _event_id_cache[outer_id] = now
    _event_id_queue.append((now, outer_id))
