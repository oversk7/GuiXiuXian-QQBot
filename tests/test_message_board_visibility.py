"""留言板消息可见性过滤的回归测试。

被封号（PlayerBan）或被禁言（MessageBoardBlacklist）的发送者，
其历史消息不应出现在留言板列表与未读计数中。
"""
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from plugins.xiuxian_game.models.db import Base
from plugins.xiuxian_game.models.message_blacklist import MessageBoardBlacklist
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.player_ban import PlayerBan
from plugins.xiuxian_game.models.world_message import WorldMessage
from plugins.xiuxian_game.world import message_board as mb


@asynccontextmanager
async def _make_fake_safe_session(session_factory):
    async with session_factory() as session:
        yield session
        await session.commit()


class _FakeNow:
    """仅用于固定 datetime.now() 的返回值，模拟“第二天再查询”。"""

    def __init__(self, value: datetime):
        self.value = value

    def now(self):
        return self.value


async def test_world_page_and_unread_hide_banned_and_muted_senders(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def _fake_safe_session():
        async with _make_fake_safe_session(session_factory) as session:
            yield session

    monkeypatch.setattr(mb, "safe_session", _fake_safe_session)

    async with session_factory() as session:
        now = datetime.now()
        session.add(Player(id="viewer", uid=10001, nickname="我", server_id=1))
        session.add(Player(id="banned", uid=10002, nickname="被封", server_id=1))
        session.add(Player(id="muted", uid=10003, nickname="被禁", server_id=1))
        session.add(Player(id="normal", uid=10004, nickname="正常", server_id=1))
        session.add(
            WorldMessage(player_id="banned", scope="world", content="骂人消息", created_at=now)
        )
        session.add(
            WorldMessage(player_id="muted", scope="world", content="禁言消息", created_at=now)
        )
        session.add(
            WorldMessage(player_id="normal", scope="world", content="正常消息", created_at=now)
        )
        session.add(
            WorldMessage(
                player_id="banned",
                scope="world",
                content="一天前的旧消息",
                created_at=now - timedelta(days=2),
            )
        )
        session.add(PlayerBan(player_id="banned", admin_id="admin", ban_type="permanent", is_active=True))
        session.add(MessageBoardBlacklist(target_player_id="muted", admin_id="admin", is_active=True))
        await session.commit()

    total, total_pages, page, records, players, card_map = await mb._get_message_page(
        mb.MessageScope.WORLD, "viewer", 1
    )
    assert total == 2
    assert [r.content for r in records] == ["正常消息", "一天前的旧消息"]

    world_has_unread, *_ = await mb.get_unread_message_status("viewer")
    assert world_has_unread is True

    await engine.dispose()


async def test_banned_message_stays_hidden_next_day(monkeypatch):
    """骂人消息在处罚前刚发，第二天查询时仍应被隐藏，不能随时间流逝复活。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def _fake_safe_session():
        async with _make_fake_safe_session(session_factory) as session:
            yield session

    monkeypatch.setattr(mb, "safe_session", _fake_safe_session)

    ban_time = datetime(2026, 1, 10, 12, 0, 0)
    monkeypatch.setattr(mb, "datetime", _FakeNow(ban_time + timedelta(days=2)))

    async with session_factory() as session:
        session.add(Player(id="viewer", uid=10001, nickname="我", server_id=1))
        session.add(Player(id="banned", uid=10002, nickname="被封", server_id=1))
        session.add(
            WorldMessage(
                player_id="banned",
                scope="world",
                content="处罚前刚发的骂人消息",
                created_at=ban_time - timedelta(hours=1),
            )
        )
        session.add(
            WorldMessage(
                player_id="banned",
                scope="world",
                content="处罚前的旧消息",
                created_at=ban_time - timedelta(days=2),
            )
        )
        session.add(
            PlayerBan(
                player_id="banned",
                admin_id="admin",
                ban_type="permanent",
                is_active=True,
                created_at=ban_time,
            )
        )
        await session.commit()

    total, total_pages, page, records, players, card_map = await mb._get_message_page(
        mb.MessageScope.WORLD, "viewer", 1
    )
    assert total == 1
    assert [r.content for r in records] == ["处罚前的旧消息"]
