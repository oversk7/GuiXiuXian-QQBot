"""
公会活跃度检测与自动管理

- 会长超过 INACTIVE_DAYS 天未登录 → 自动继承给最活跃成员
- 全员超过 INACTIVE_DAYS 天不活跃 → 自动解散公会
- 公会列表按成员活跃度排序
"""
from datetime import datetime, timedelta, date
from sqlalchemy import select, func, delete as sql_delete, case
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.guild import (
    Guild, GuildMember, GuildPosition,
    GuildWarehouseItem, GuildAlchemyProduction, GuildTeleportLog,
)
from ..models.guild_task_record import GuildTaskRecord
import logging

logger = logging.getLogger(__name__)

INACTIVE_DAYS = 30

# 每日只检查一次（进程级缓存）
_last_check_date_by_server: dict[int, date] = {}


def _player_last_active(player: Player) -> datetime | None:
    """取玩家最后活跃时间（last_sign 和 last_active_at 取较新者）"""
    candidates = [t for t in (player.last_sign, player.last_active_at) if t]
    return max(candidates) if candidates else None


async def maybe_run_activity_check(session: AsyncSession, server_id: int = 1) -> list[str]:
    """每日执行一次公会活跃度检查，返回操作日志列表"""
    today = datetime.now().date()
    if _last_check_date_by_server.get(server_id) == today:
        return []
    _last_check_date_by_server[server_id] = today
    try:
        return await _do_activity_check(session, server_id)
    except Exception as e:
        logger.exception(f"公会活跃度检查异常: {e}")
        return []


async def _do_activity_check(session: AsyncSession, server_id: int) -> list[str]:
    """核心：遍历所有公会，执行会长继承/僵尸解散"""
    messages = []
    threshold = datetime.now() - timedelta(days=INACTIVE_DAYS)

    guilds = (await session.execute(select(Guild).where(Guild.server_id == server_id))).scalars().all()

    for guild in guilds:
        president = await session.get(Player, guild.president_id)
        if not president:
            continue

        # 会长还活跃 → 跳过
        last = _player_last_active(president)
        if last is not None and last >= threshold:
            continue

        # 找公会内最活跃的非会长成员
        candidate = await _find_active_candidate(session, guild, threshold)

        if candidate:
            msg = await _auto_transfer_president(session, guild, president, candidate)
            messages.append(msg)
        else:
            msg = await _auto_dissolve_guild(session, guild)
            messages.append(msg)

    if messages:
        await session.commit()
        logger.info(f"公会活跃度检查完成，共处理 {len(messages)} 个公会")

    return messages


async def _find_active_candidate(
    session: AsyncSession, guild: Guild, threshold: datetime
) -> tuple[GuildMember, Player] | None:
    """按职位从高到低查找活跃候选人；同职位取最近活跃者。"""
    stmt = (
        select(GuildMember, Player)
        .join(Player, GuildMember.player_id == Player.id)
        .where(GuildMember.guild_id == guild.id)
        .where(GuildMember.player_id != guild.president_id)
    )
    results = (await session.execute(stmt)).all()

    position_order = (
        GuildPosition.VICE_PRESIDENT,
        GuildPosition.CORE_MEMBER,
        GuildPosition.MEMBER,
    )
    for position in position_order:
        best = None
        best_time = None
        for member, player in results:
            if member.position != position:
                continue
            last = _player_last_active(player)
            if last and last >= threshold:
                if best_time is None or last > best_time:
                    best = (member, player)
                    best_time = last
        if best:
            return best

    return None


async def _auto_transfer_president(
    session: AsyncSession,
    guild: Guild,
    old_president: Player,
    candidate: tuple[GuildMember, Player],
) -> str:
    """自动转让会长并写入公告通知"""
    member, new_president = candidate

    # 旧会长降为普通成员
    old_member = (await session.execute(
        select(GuildMember).where(
            GuildMember.guild_id == guild.id,
            GuildMember.player_id == guild.president_id,
        )
    )).scalar_one_or_none()

    if old_member:
        old_member.position = GuildPosition.MEMBER
        session.add(old_member)

    # 新会长上任
    member.position = GuildPosition.PRESIDENT
    session.add(member)
    guild.president_id = new_president.id

    # 写入公告：成员查看公会时即可看到
    now_str = datetime.now().strftime("%m-%d")
    guild.notice = (
        f"原会长{old_president.nickname}超过{INACTIVE_DAYS}天未登录，"
        f"会长已于{now_str}自动移交给{new_president.nickname}"
    )
    session.add(guild)

    msg = f"公会『{guild.name}』会长自动继承: {old_president.nickname} → {new_president.nickname}"
    logger.info(msg)
    return msg


async def _auto_dissolve_guild(session: AsyncSession, guild: Guild) -> str:
    """自动解散全员不活跃的公会"""
    guild_name = guild.name

    # 清空所有成员的公会字段（与手动解散逻辑一致）
    members = (await session.execute(
        select(Player).where(Player.guild_id == guild.id)
    )).scalars().all()
    for m in members:
        m.guild_id = None
        session.add(m)

    # 删除关联记录
    await session.execute(sql_delete(GuildTaskRecord).where(GuildTaskRecord.guild_id == guild.id))
    await session.execute(sql_delete(GuildWarehouseItem).where(GuildWarehouseItem.guild_id == guild.id))
    await session.execute(sql_delete(GuildAlchemyProduction).where(GuildAlchemyProduction.guild_id == guild.id))
    await session.execute(sql_delete(GuildTeleportLog).where(GuildTeleportLog.guild_id == guild.id))

    # 删除公会（cascade 删除 GuildMember 和 GuildBuilding）
    await session.delete(guild)

    msg = f"公会『{guild_name}』因全员超过{INACTIVE_DAYS}天未登录已自动解散"
    logger.info(msg)
    return msg


async def get_guilds_sorted_by_activity(
    session: AsyncSession, server_id: int = 1, *, page: int = 1, page_size: int = 20,
):
    """
    获取公会列表，按活跃度排序。

    返回当前页公会展示列，包含最近活跃时间、成员数与会长信息。
    - 主排序: 公会最近活跃成员的登录时间降序
    - 次排序: 公会等级降序
    """
    # 子查询：每个公会最近成员活跃时间（取 last_active_at 和 last_sign 中较新者）
    activity_subq = (
        select(
            GuildMember.guild_id,
            func.count(GuildMember.id).label("member_count"),
            func.max(
                func.greatest(
                    func.coalesce(Player.last_active_at, Player.created_at),
                    func.coalesce(Player.last_sign, Player.created_at),
                )
            ).label("latest_active"),
        )
        .outerjoin(Player, GuildMember.player_id == Player.id)
        .group_by(GuildMember.guild_id)
        .subquery()
    )

    stmt = (
        select(
            Guild.id, Guild.name, Guild.level, Guild.treasury,
            activity_subq.c.latest_active,
            func.coalesce(activity_subq.c.member_count, 0).label("member_count"),
            Player.nickname.label("president_name"),
            Player.uid.label("president_uid"),
        )
        .outerjoin(activity_subq, Guild.id == activity_subq.c.guild_id)
        .outerjoin(Player, Guild.president_id == Player.id)
        .where(Guild.server_id == server_id)
        .order_by(
            # NULL（无成员）排最后
            case((activity_subq.c.latest_active.is_(None), 1), else_=0),
            activity_subq.c.latest_active.desc(),
            Guild.level.desc(),
            Guild.id,
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
    )

    result = await session.execute(stmt)
    return result.all()
