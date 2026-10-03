from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from nonebot.exception import FinishedException
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.guild import guild as commands, guild_activity as activity
from plugins.xiuxian_game.models.db import Base, safe_session
from plugins.xiuxian_game.models.guild import (
    Guild, GuildMember, GuildPosition, GuildBuilding, GuildWarehouseItem,
    GuildWarehouseLog, GuildAlchemyProduction, GuildTeleportLog, WarehouseLogType,
)
from plugins.xiuxian_game.models.guild_task_record import GuildTaskRecord
from plugins.xiuxian_game.models.player import Player


@pytest.fixture
async def guild_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=[
            Player.__table__, Guild.__table__, GuildMember.__table__, GuildBuilding.__table__,
            GuildWarehouseItem.__table__, GuildWarehouseLog.__table__,
            GuildAlchemyProduction.__table__, GuildTeleportLog.__table__, GuildTaskRecord.__table__,
        ]))
    monkeypatch.setattr(activity, "_last_check_date_by_server", {})
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with safe_session(factory) as session:
        session.add(Player(id="inactive", uid=1, nickname="member", guild_id=1,
                           last_sign=datetime.now() - timedelta(days=40)))
        session.add(Guild(id=1, name="inactive guild", president_id="inactive"))
        session.add(Guild(id=2, name="other guild", president_id="other"))
        await session.flush()
        session.add(GuildMember(guild_id=1, player_id="inactive", position=GuildPosition.PRESIDENT))
        for guild_id in (1, 2):
            session.add(GuildWarehouseLog(guild_id=guild_id, player_id="inactive",
                                         operation=WarehouseLogType.DEPOSIT, item_id="item", quantity=1))
    try:
        yield factory
    finally:
        await engine.dispose()


async def test_fixture_enforces_warehouse_log_foreign_key(guild_store):
    with pytest.raises(IntegrityError):
        async with safe_session(guild_store) as session:
            await session.execute(delete(Guild).where(Guild.id == 1))


@pytest.mark.parametrize("automatic", [True, False])
async def test_dissolution_deletes_logs_and_preserves_other_guild(guild_store, monkeypatch, automatic):
    if automatic:
        async with safe_session(guild_store) as session:
            result = await activity.maybe_run_activity_check(session)
            assert len(result) == 1
            assert activity._last_check_date_by_server[1] == datetime.now().date()
    else:
        monkeypatch.setattr(commands, "safe_session", lambda: safe_session(guild_store))

        async def player(session, event):
            return await session.get(Player, "inactive")

        monkeypatch.setattr(commands, "get_unified_player", player)
        monkeypatch.setattr(commands.GuildPermission, "get_member_position",
                            AsyncMock(return_value=GuildPosition.PRESIDENT))
        monkeypatch.setattr(commands, "message_add_head", lambda text, event: text)
        monkeypatch.setattr(commands.dissolve_guild_cmd, "finish", AsyncMock(side_effect=FinishedException()))
        with pytest.raises(FinishedException):
            await commands.handle_dissolve_guild(SimpleNamespace())
    async with safe_session(guild_store) as session:
        assert await session.get(Guild, 1) is None
        assert await session.get(Guild, 2) is not None
        assert (await session.get(Player, "inactive")).guild_id is None
        assert await session.scalar(select(func.count()).select_from(GuildMember)) == 0
        assert await session.scalar(select(func.count()).select_from(GuildWarehouseLog)
                                    .where(GuildWarehouseLog.guild_id == 1)) == 0
        assert await session.scalar(select(func.count()).select_from(GuildWarehouseLog)
                                    .where(GuildWarehouseLog.guild_id == 2)) == 1


async def test_failed_activity_check_rolls_back_before_query_and_can_retry(monkeypatch):
    monkeypatch.setattr(activity, "_last_check_date_by_server", {})
    error = IntegrityError("delete guild", {}, ValueError("foreign key"))
    check = AsyncMock(side_effect=[error, ["done"]])
    monkeypatch.setattr(activity, "_do_activity_check", check)
    session = AsyncMock()
    assert await activity.maybe_run_activity_check(session) == []
    session.rollback.assert_awaited_once()
    assert activity._last_check_date_by_server == {}
    assert await activity.maybe_run_activity_check(session) == ["done"]
    assert await activity.maybe_run_activity_check(session) == []
    assert check.await_count == 2
    assert activity._last_check_date_by_server[1] == datetime.now().date()
