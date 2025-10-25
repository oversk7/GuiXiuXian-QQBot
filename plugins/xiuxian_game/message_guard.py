"""Message guard to prevent duplicate command processing within a short window."""
from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Tuple

from nonebot import logger, on_message
from nonebot.matcher import Matcher
from nonebot.adapters.qq import MessageEvent

_TTL_SECONDS = 1.5
_message_cache: Dict[str, float] = {}
_message_queue: Deque[Tuple[float, str]] = deque()


def _cleanup(now: float) -> None:
    """Remove expired cache entries based on the TTL."""
    while _message_queue:
        timestamp, key = _message_queue[0]
        if now - timestamp <= _TTL_SECONDS:
            break
        _message_queue.popleft()
        if _message_cache.get(key) == timestamp:
            _message_cache.pop(key, None)


def _build_key(event: MessageEvent) -> str:
    return f"{event.get_user_id()}|{event.get_plaintext().strip()}"


guard = on_message(priority=0, block=False)


@guard.handle()
async def _(matcher: Matcher, event: MessageEvent) -> None:
    now = time.monotonic()
    _cleanup(now)

    key = _build_key(event)
    last_seen = _message_cache.get(key)

    if last_seen is not None and now - last_seen <= _TTL_SECONDS:
        logger.debug("Duplicate message intercepted: %s", key)
        matcher.stop_propagation()
        return

    _message_cache[key] = now
    _message_queue.append((now, key))

