"""签到日历 BitMap（Redis 部分需要 GUIX_REDIS_TEST_URL）。"""

from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException

from plugins.xiuxian_game import platform_utils
from plugins.xiuxian_game.entertainment import sign_calendar
from plugins.xiuxian_game.entertainment.sign_calendar import SignCalendarStore, render_calendar
from plugins.xiuxian_game.models import db
from tests.redis_helpers import redis_backend_factory  # noqa: F401


@pytest.fixture
def store(redis_backend_factory):  # noqa: F811
    return SignCalendarStore(redis_backend_factory(timeout_seconds=2))


def _days(signed):
    return [day for day, done in enumerate(signed, 1) if done]


async def test_record_writes_streak_run_within_month(store):
    await store.record("p", date(2026, 10, 20), streak=3)
    signed, count = await store.month("p", 2026, 10)
    assert len(signed) == 31
    assert _days(signed) == [18, 19, 20]
    assert count == 3

    # 重复执行结果不变；第二天接着签只多一位
    await store.record("p", date(2026, 10, 20), streak=3)
    await store.record("p", date(2026, 10, 21), streak=4)
    signed, count = await store.month("p", 2026, 10)
    assert _days(signed) == [18, 19, 20, 21]
    assert count == 4


async def test_streak_crossing_month_only_touches_that_month(store):
    await store.record("p", date(2026, 11, 2), streak=5)
    signed, count = await store.month("p", 2026, 11)
    assert _days(signed) == [1, 2]
    assert count == 2
    assert not await store.exists("p", 2026, 10)


async def test_short_month_and_empty_month(store):
    await store.record("p", date(2026, 2, 28), streak=1)
    signed, count = await store.month("p", 2026, 2)
    assert len(signed) == 28 and _days(signed) == [28] and count == 1

    signed, count = await store.month("nobody", 2026, 3)
    assert len(signed) == 31 and not any(signed) and count == 0


def test_render_calendar_aligns_weekdays():
    # 2026-10-01 是周四：第一行前面空 3 格
    signed = [day in (1, 2, 5) for day in range(1, 32)]
    lines = render_calendar(2026, 10, signed, today=date(2026, 10, 6))
    assert lines[0] == "一 二 三 四 五 六 日"
    assert lines[1].split(" ") == ["　", "　", "　", "✅", "✅", "⬜", "⬜"]
    assert lines[2].split(" ")[:3] == ["✅", "⬜", "▫️"]
    assert len(lines) == 6 and all(len(line.split(" ")) == 7 for line in lines[1:-1])


async def test_calendar_backfills_current_streak_once(store, monkeypatch):
    today = datetime.now().date()
    last_sign = datetime.now() - timedelta(days=1)
    player = SimpleNamespace(id="p", last_sign=last_sign, sign_streak=3)

    @asynccontextmanager
    async def session_factory():
        yield SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock(), close=AsyncMock())

    async def identity(session, event, *args):
        return player

    replies = []

    async def finish(message):
        replies.append(str(message))
        raise FinishedException

    monkeypatch.setattr(db, "AsyncSessionLocal", session_factory)
    monkeypatch.setattr(platform_utils, "require_player", identity)
    monkeypatch.setattr(sign_calendar, "get_sign_calendar_store", lambda: store)
    monkeypatch.setattr(sign_calendar.sign_calendar_cmd, "finish", finish)

    with pytest.raises(FinishedException):
        await sign_calendar.handle_sign_calendar(SimpleNamespace())

    if (last_sign.year, last_sign.month) == (today.year, today.month):
        signed, count = await store.month("p", today.year, today.month)
        expected = [d for d in range(last_sign.day - 2, last_sign.day + 1) if d >= 1]
        assert _days(signed) == expected
        assert f"本月已签到 **{count}** 天 · 连续签到 **3** 天" in replies[0]
        assert "还没签到" in replies[0]
