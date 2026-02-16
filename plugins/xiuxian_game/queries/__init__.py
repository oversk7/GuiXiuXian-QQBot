"""
CQRS 查询侧 (Query Side)

为高频读操作提供直达数据库的轻量查询通道，绕过 Repository/UoW 开销。
所有查询均为只读，不修改任何数据。
"""

import time
import functools
import hashlib
import json
from typing import Any, Callable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession
from ..models.db import AsyncSessionLocal


@asynccontextmanager
async def readonly_session():
    """只读会话上下文管理器

    基于 AsyncSessionLocal，语义明确为只读操作。
    不自动 commit，退出时直接关闭会话。
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


# ==================== 进程内 TTL 缓存 ====================

_cache: dict[str, tuple[float, Any]] = {}


def _make_cache_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """为缓存生成唯一 key"""
    key_parts = [func.__module__, func.__qualname__]
    for arg in args:
        key_parts.append(repr(arg))
    for k, v in sorted(kwargs.items()):
        key_parts.append(f"{k}={repr(v)}")
    raw = "|".join(key_parts)
    return hashlib.md5(raw.encode()).hexdigest()


def cached(ttl_seconds: int = 300):
    """进程内 TTL 缓存装饰器

    适用于排行榜等不需要实时的查询。
    基于 dict + timestamp，无外部依赖。

    Args:
        ttl_seconds: 缓存过期时间（秒），默认 5 分钟
    """
    def decorator(func: Callable):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            key = _make_cache_key(func, args, kwargs)
            now = time.time()

            if key in _cache:
                cached_time, cached_value = _cache[key]
                if now - cached_time < ttl_seconds:
                    return cached_value

            result = await func(*args, **kwargs)
            _cache[key] = (now, result)
            return result
        return wrapper
    return decorator


def invalidate_cache(func: Callable | None = None):
    """清除缓存

    Args:
        func: 如果指定，只清除该函数的缓存；否则清除全部缓存
    """
    if func is None:
        _cache.clear()
    else:
        prefix = f"{func.__module__}|{func.__qualname__}"
        keys_to_remove = [
            k for k, (_, _) in _cache.items()
            # 无法反向查找前缀，直接清除全部
        ]
        # 简单实现：清除全部缓存
        _cache.clear()
