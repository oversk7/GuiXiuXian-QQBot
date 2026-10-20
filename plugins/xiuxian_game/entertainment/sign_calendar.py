"""签到日历：每个玩家每月一个 Redis BitMap，第 N 天签到就把第 N-1 位置 1。

发奖、"今天签没签过"和连续天数仍以 player.last_sign / sign_streak 为准；
BitMap 只负责签到日历和月累计展示。数据库里没有签到历史，所以 Redis 是这份数据的唯一存储（靠 AOF）。
"""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from nonebot import logger, on_command
from nonebot.adapters.qq import MessageEvent
from redis.exceptions import ResponseError

from ..infrastructure.redis_service import RedisBackend, RedisUnavailable, get_redis_backend
from ..utils_markdown import build_markdown, cmd

# 跨年查看上一年的日历也够用
KEEP_SECONDS = int(timedelta(days=400).total_seconds())


class SignCalendarStore:
    def __init__(self, backend: RedisBackend) -> None:
        self._backend = backend

    @property
    def configured(self) -> bool:
        return self._backend.configured

    def _key(self, player_id: str, year: int, month: int) -> str:
        return self._backend.key(f"sign:{player_id}:{year}{month:02d}")

    async def record(self, player_id: str, sign_date: date, streak: int) -> None:
        """记下以 sign_date 结尾、连续 streak 天的签到（只写 sign_date 所在月份）。

        签到时调用，可重复执行。连同前面连续的几天一起写，是为了上线前已经在连签的玩家，
        日历上也能看到本月这段连续签到；Redis 数据丢了，下一次签到也会把这段补回来。
        """
        first_day = max(1, sign_date.day - max(streak, 1) + 1)
        ops = []
        for day in range(first_day, sign_date.day + 1):
            ops.extend(["SET", "u1", day - 1, 1])
        key = self._key(player_id, sign_date.year, sign_date.month)
        await self._backend.command("execute_command", "BITFIELD", key, *ops)
        await self._backend.command("expire", key, KEEP_SECONDS)

    async def exists(self, player_id: str, year: int, month: int) -> bool:
        return bool(await self._backend.command("exists", self._key(player_id, year, month)))

    async def month(self, player_id: str, year: int, month: int) -> tuple[list[bool], int]:
        """返回 (每天是否签到, 本月签到天数)"""
        days = calendar.monthrange(year, month)[1]
        key = self._key(player_id, year, month)
        # 一条 BITFIELD 取出整月：最高位是 1 号
        (bits,) = await self._backend.command("execute_command", "BITFIELD", key, "GET", f"u{days}", 0)
        signed = [bool(bits >> (days - day) & 1) for day in range(1, days + 1)]
        count = int(await self._backend.command("bitcount", key))
        return signed, count


def get_sign_calendar_store() -> SignCalendarStore:
    return SignCalendarStore(get_redis_backend())


async def record_sign(player_id: str, sign_date: date, streak: int) -> None:
    """签到事务提交后调用；写失败只影响日历展示，不影响签到本身"""
    store = get_sign_calendar_store()
    if not store.configured:
        return
    try:
        await store.record(player_id, sign_date, streak)
    except (RedisUnavailable, ResponseError) as exc:
        logger.warning(f"[签到日历] 写入 Redis 失败: {type(exc).__name__}")


def render_calendar(year: int, month: int, signed: list[bool], today: date) -> list[str]:
    """按周一到周日排成表格：✅ 已签、⬜ 未签、▫️ 还没到"""
    lines = ["一 二 三 四 五 六 日"]
    # 1 号之前用全角空格占位，和表头的汉字等宽
    week = ["　"] * calendar.monthrange(year, month)[0]
    for day, done in enumerate(signed, 1):
        if done:
            week.append("✅")
        elif date(year, month, day) > today:
            week.append("▫️")
        else:
            week.append("⬜")
        if len(week) == 7:
            lines.append(" ".join(week))
            week = []
    if week:
        lines.append(" ".join(week))
    return lines


sign_calendar_cmd = on_command("签到日历", aliases={"签到记录"}, block=True, priority=13)


@sign_calendar_cmd.handle()
async def handle_sign_calendar(event: MessageEvent):
    from ..models.db import safe_session
    from ..platform_utils import require_player

    async with safe_session() as session:
        player = await require_player(session, event, sign_calendar_cmd)
        player_id = player.id
        last_sign = player.last_sign
        streak = player.sign_streak or 0

    store = get_sign_calendar_store()
    if not store.configured:
        await sign_calendar_cmd.finish("⛔ 签到日历暂未开放")

    today = datetime.now().date()
    try:
        # 上线前没有签到历史：本月还没有记录时，按上次签到和连续天数把最近这段补上
        if (last_sign and (last_sign.year, last_sign.month) == (today.year, today.month)
                and not await store.exists(player_id, today.year, today.month)):
            await store.record(player_id, last_sign.date(), streak)
        signed, count = await store.month(player_id, today.year, today.month)
    except (RedisUnavailable, ResponseError) as exc:
        logger.warning(f"[签到日历] 读取 Redis 失败: {type(exc).__name__}")
        await sign_calendar_cmd.finish("⛔ 签到日历暂时不可用，请稍后再试")

    last_date = last_sign.date() if last_sign else None
    # sign_streak 只在签到时更新：上次签到早于昨天，说明已经断签
    current_streak = streak if last_date and last_date >= today - timedelta(days=1) else 0
    lines = [
        f"# 📅 {today.year}年{today.month}月 签到日历",
        *render_calendar(today.year, today.month, signed, today),
        "***",
        f"本月已签到 **{count}** 天 · 连续签到 **{current_streak}** 天",
        f"> 今天{'已签到' if last_date == today else '还没签到，发送 ' + cmd('签到')}",
    ]
    await sign_calendar_cmd.finish(build_markdown("\n".join(lines)))
