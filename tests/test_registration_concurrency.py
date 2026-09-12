"""单进程并发注册的 UID 分配与事务边界。"""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.infrastructure.repositories.account_ownership_repository import AccountOwnershipRepository
from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.account_ownership import AccountOwnership
from plugins.xiuxian_game.models.player import Gender, Player
from plugins.xiuxian_game.player import info
from plugins.xiuxian_game.quest.novice_quest_service import NoviceQuestService


def register(platform_id, server_id=1):
    event = SimpleNamespace(get_user_id=lambda: platform_id)
    return info.create_player(event, platform_id, Gender.MALE, server_id)


@pytest.fixture
def registration_hooks(monkeypatch):
    monkeypatch.setattr(info, "_registration_lock", asyncio.Lock())
    monkeypatch.setattr(info, "ensure_platform_server_binding", AsyncMock(
        side_effect=lambda session, user_id, server_id: (True, "", server_id),
    ))
    monkeypatch.setattr(info.player_identity_cache, "put", Mock())
    monkeypatch.setattr(NoviceQuestService, "init_novice_quests", AsyncMock(return_value=True))


@pytest.fixture
def registration_store(monkeypatch, registration_hooks):
    store = SimpleNamespace(
        players=[], ownerships=[], pause_at=None, paused=False,
        paused_event=asyncio.Event(), release=asyncio.Event(), fail_commit=False,
    )

    async def pause_at(stage):
        if store.pause_at == stage and not store.paused:
            store.paused = True
            store.paused_event.set()
            await store.release.wait()

    class Session:
        def __init__(self):
            self.pending = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def execute(self, statement):
            if "max(player.uid)" in str(statement):
                maximum = max((entry.uid for entry in store.players), default=None)
                await pause_at("read")
                return SimpleNamespace(scalar=lambda: maximum)
            platform_id = statement.compile().params["id_1"]
            existing = next((entry for entry in store.players if entry.id == platform_id), None)
            return SimpleNamespace(scalars=lambda: SimpleNamespace(first=lambda: existing))

        def add(self, entry):
            self.pending.append(entry)

        def validate_uids(self):
            existing = {entry.uid for entry in store.players}
            for entry in self.pending:
                if isinstance(entry, Player):
                    if entry.uid in existing:
                        raise IntegrityError("INSERT player", {}, ValueError("duplicate player.uid"))
                    existing.add(entry.uid)

        async def flush(self):
            self.validate_uids()

        async def commit(self):
            await pause_at("commit")
            if store.fail_commit:
                store.fail_commit = False
                raise SQLAlchemyError("提交失败")
            self.validate_uids()
            store.players.extend(entry for entry in self.pending if isinstance(entry, Player))
            store.ownerships.extend(entry for entry in self.pending if isinstance(entry, AccountOwnership))
            self.pending.clear()

        async def rollback(self):
            self.pending.clear()

        async def close(self):
            pass

    monkeypatch.setattr(db, "AsyncSessionLocal", Session)
    monkeypatch.setattr(AccountOwnershipRepository, "find_all_by_owner", AsyncMock(
        side_effect=lambda owner_id: [entry for entry in store.ownerships if entry.owner_platform_id == owner_id],
    ))
    monkeypatch.setattr(AccountOwnershipRepository, "find_by_player_id", AsyncMock(return_value=None))
    monkeypatch.setattr(AccountOwnershipRepository, "deactivate_all_accounts", AsyncMock())
    return store


async def register_pair(store, first_id="user-a", second_id="user-b"):
    first = asyncio.create_task(register(first_id, 1))
    await asyncio.wait_for(store.paused_event.wait(), timeout=2)
    second_started = asyncio.Event()

    async def second_registration():
        second_started.set()
        return await register(second_id, 2)

    second = asyncio.create_task(second_registration())
    await second_started.wait()
    store.release.set()
    return await asyncio.gather(first, second, return_exceptions=True)


@pytest.mark.parametrize("pause_at", ["read", "commit"])
@pytest.mark.parametrize("existing_uid", [None, 7249])
async def test_concurrent_registrations_get_distinct_uids(registration_store, pause_at, existing_uid):
    store = registration_store
    store.pause_at = pause_at
    if existing_uid is not None:
        store.players.append(Player(id="legacy-player", uid=existing_uid, nickname="老角色"))

    results = await register_pair(store)

    assert all(not isinstance(result, BaseException) for result in results), results
    new_players = [entry for entry in store.players if entry.id != "legacy-player"]
    first_uid = 100 if existing_uid is None else existing_uid + 1
    assert sorted(entry.uid for entry in new_players) == [first_uid, first_uid + 1]
    assert {entry.server_id for entry in new_players} == {1, 2}
    assert {entry.player_id for entry in store.ownerships} == {entry.id for entry in new_players}
    assert all(entry.is_active for entry in store.ownerships)


async def test_concurrent_same_account_registers_only_once(registration_store):
    store = registration_store
    store.pause_at = "read"

    results = await register_pair(store, "same-user", "same-user")

    assert all(not isinstance(result, BaseException) for result in results), results
    assert len(store.players) == len(store.ownerships) == 1
    assert store.players[0].uid == 100
    assert any("已经拥有游戏账号" in str(result) for result in results)


async def test_failed_registration_releases_lock_and_rolls_back(registration_store):
    store = registration_store
    store.fail_commit = True
    with pytest.raises(SQLAlchemyError, match="提交失败"):
        await register("failed-user")
    assert not store.players
    assert not store.ownerships
    info.player_identity_cache.put.assert_not_called()

    await asyncio.wait_for(register("next-user"), timeout=2)
    assert len(store.players) == len(store.ownerships) == 1
    assert store.players[0].uid == 100


async def test_concurrent_registration_with_real_database(tmp_path, monkeypatch, registration_hooks):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'registration.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: db.Base.metadata.create_all(conn, tables=[
                Player.__table__, AccountOwnership.__table__,
            ]))
        monkeypatch.setattr(db, "AsyncSessionLocal", async_sessionmaker(engine, expire_on_commit=False))
        async with db.safe_session() as session:
            session.add(Player(id="legacy-player", uid=500, nickname="老角色"))

        await asyncio.gather(*(register(f"user-{index}", 1 + index % 2) for index in range(6)))

        async with db.safe_session() as session:
            players = list((await session.execute(select(Player).order_by(Player.uid))).scalars())
            owners = list((await session.execute(select(AccountOwnership))).scalars())
        assert [entry.uid for entry in players] == list(range(500, 507))
        assert len({entry.id for entry in players}) == 7
        assert {entry.player_id for entry in owners} == {entry.id for entry in players[1:]}
        assert all(entry.is_active for entry in owners)
    finally:
        await engine.dispose()
