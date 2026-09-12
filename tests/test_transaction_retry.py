import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from plugins.xiuxian_game.models import db
from plugins.xiuxian_game.models.inventory import ItemInstance
from plugins.xiuxian_game.models.player import Player
from tests.mysql_helpers import mysql_session_factory


async def test_retry_reexecutes_entire_transaction_with_fresh_session(mysql_session_factory, monkeypatch):
    factory = mysql_session_factory
    monkeypatch.setattr(db, "AsyncSessionLocal", factory)
    async with db.safe_session() as setup:
        setup.add(Player(id="p", uid=1, nickname="甲", gold=0))
    attempts = []

    async def operation(session):
        attempts.append(session)
        player = await session.get(Player, "p")
        player.gold += 100
        session.add(ItemInstance(player_id="p", item_id="bone_fragment", quantity=1))
        await session.flush()
        if len(attempts) == 1:
            raise OperationalError("UPDATE", {}, RuntimeError(1213, "deadlock"))
        return player.gold

    assert await db.run_transaction(operation) == 100
    assert len(attempts) == 2 and attempts[0] is not attempts[1]
    async with db.safe_session() as check:
        assert (await check.get(Player, "p")).gold == 100
        assert len((await check.execute(select(ItemInstance))).scalars().all()) == 1


@pytest.mark.parametrize("error_code,expected_attempts", [(1064, 1), (1205, 2)])
async def test_retry_is_bounded_and_does_not_swallow_database_errors(mysql_session_factory, monkeypatch, error_code, expected_attempts):
    monkeypatch.setattr(db, "AsyncSessionLocal", mysql_session_factory)
    calls = 0

    async def operation(session):
        nonlocal calls
        calls += 1
        session.add(Player(id="p", uid=1, nickname="甲"))
        await session.flush()
        raise OperationalError("UPDATE", {}, RuntimeError(error_code, "failure"))

    with pytest.raises(OperationalError):
        await db.run_transaction(operation, max_attempts=2)
    assert calls == expected_attempts
    async with db.safe_session() as check:
        assert await check.get(Player, "p") is None
