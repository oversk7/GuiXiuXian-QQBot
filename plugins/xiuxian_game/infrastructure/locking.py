from collections.abc import Iterable
from typing import TypeVar

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession


T = TypeVar("T")


async def lock_rows(session: AsyncSession, model: type[T], ids: Iterable) -> list[T]:
    """按主键顺序锁定并刷新记录；必须在修改这些对象之前调用。"""
    keys = sorted(set(ids))
    if not keys:
        return []
    mapper = inspect(model)
    primary_key = mapper.primary_key[0]
    pending_metadata = {}
    for key in keys:
        existing = session.identity_map.get(mapper.identity_key_from_primary_key((key,)))
        if existing is None:
            continue
        attributes = inspect(existing).attrs
        pending_metadata[key] = {
            name: attributes[name].value
            for name in (
                "last_active_at", "last_group_openid", "last_group_member_id", "last_group_username"
            )
            if name in attributes and attributes[name].history.has_changes()
        }
    # 身份查询可能留下待写元数据，不能在获取业务锁前自动刷新它们。
    with session.no_autoflush:
        result = await session.execute(
            select(model)
            .where(primary_key.in_(keys))
            .order_by(primary_key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    rows = list(result.scalars().all())
    for row in rows:
        for name, value in pending_metadata.get(getattr(row, primary_key.key), {}).items():
            if name == "last_active_at" and getattr(row, name) is not None:
                value = max(value, getattr(row, name))
            setattr(row, name, value)
    return rows


async def lock_row(session: AsyncSession, model: type[T], key) -> T | None:
    rows = await lock_rows(session, model, [key])
    return rows[0] if rows else None
