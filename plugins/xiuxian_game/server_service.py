"""区服归属服务。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models.platform_server_binding import PlatformServerBinding
from .server_config import DEFAULT_SERVER_ID, get_server_name, get_servers_config, is_server_open_for_registration

_CN_NUMBERS = {
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def parse_server_id(text: str | None, default: int = DEFAULT_SERVER_ID) -> int | None:
    """解析 1区/2区/二区/2 等区服输入。"""
    if not text:
        return default
    value = text.strip().replace("服", "").replace("区", "")
    if not value:
        return default
    if value.isdigit():
        return int(value)
    return _CN_NUMBERS.get(value)


def format_server(server_id: int | None) -> str:
    return get_server_name(server_id or DEFAULT_SERVER_ID)


async def get_platform_server_binding(
    session: AsyncSession,
    owner_platform_id: str,
) -> PlatformServerBinding | None:
    stmt = select(PlatformServerBinding).where(
        PlatformServerBinding.owner_platform_id == owner_platform_id
    )
    return (await session.execute(stmt)).scalars().first()


async def get_bound_server_id(session: AsyncSession, owner_platform_id: str) -> int | None:
    binding = await get_platform_server_binding(session, owner_platform_id)
    return binding.server_id if binding else None


async def get_owner_server_id(
    session: AsyncSession,
    owner_platform_id: str,
    default: int = DEFAULT_SERVER_ID,
) -> int:
    """返回平台账号当前区服；未绑定时按老服处理。"""
    return await get_bound_server_id(session, owner_platform_id) or default


async def ensure_platform_server_binding(
    session: AsyncSession,
    owner_platform_id: str,
    server_id: int,
    *,
    allow_closed: bool = False,
) -> tuple[bool, str, int | None]:
    """确保平台账号绑定到指定区服。

    已绑定其他区服时返回失败；未绑定时创建绑定。
    """
    if server_id not in get_servers_config():
        return False, f"⛔ 区服 {server_id} 不存在", None
    if not allow_closed and not is_server_open_for_registration(server_id):
        return False, f"⛔ {format_server(server_id)} 暂未开放注册", None

    binding = await get_platform_server_binding(session, owner_platform_id)
    if binding:
        if binding.server_id != server_id:
            return (
                False,
                f"⛔ 你的QQ已绑定{format_server(binding.server_id)}，不能操作{format_server(server_id)}账号",
                binding.server_id,
            )
        return True, "", binding.server_id

    session.add(PlatformServerBinding(owner_platform_id=owner_platform_id, server_id=server_id))
    await session.flush()
    return True, "", server_id


async def ensure_same_server_binding(
    session: AsyncSession,
    owner_platform_id: str,
    server_id: int,
    *,
    allow_closed: bool = True,
) -> tuple[bool, str]:
    ok, message, _ = await ensure_platform_server_binding(
        session,
        owner_platform_id,
        server_id,
        allow_closed=allow_closed,
    )
    return ok, message


async def get_or_create_platform_server_id(
    session: AsyncSession,
    owner_platform_id: str,
    preferred_server_id: int = DEFAULT_SERVER_ID,
) -> tuple[bool, str, int | None]:
    return await ensure_platform_server_binding(
        session,
        owner_platform_id,
        preferred_server_id,
    )
