import asyncio
from contextlib import nullcontext
from types import SimpleNamespace

from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.red_envelope_repository import (
    RedEnvelopeRepository,
)
from plugins.xiuxian_game.social.red_envelope_service import get_red_envelope_group_lock


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _Scalars:
    def __init__(self, values):
        self.values = values

    def first(self):
        return self.values[0] if self.values else None

    def all(self):
        return self.values


class _ExecuteResult:
    def __init__(self, values):
        self.values = values

    def scalars(self):
        return _Scalars(self.values)

    def scalar_one_or_none(self):
        return self.values[0] if self.values else None


class _StatementSession:
    def __init__(self, values):
        self.values = values
        self.statement = None
        self.identity_map = {}
        self.no_autoflush = nullcontext()

    async def execute(self, statement):
        self.statement = statement
        return _ExecuteResult(self.values)


async def test_active_envelope_query_uses_row_lock():
    envelope = SimpleNamespace()
    session = _StatementSession([envelope])

    actual = await RedEnvelopeRepository(session).find_active_by_group_for_update(
        "group-1",
        1,
    )

    assert actual is envelope
    assert session.statement._for_update_arg is not None


async def test_player_asset_query_uses_row_lock_and_refreshes_snapshot():
    player = SimpleNamespace(id="player-1")
    session = _StatementSession([player])

    actual = await PlayerRepository(session).get_by_id_for_update("player-1")

    assert actual is player
    assert session.statement._for_update_arg is not None
    assert session.statement.get_execution_options()["populate_existing"] is True


async def test_group_lock_serializes_same_group():
    group_id = "concurrency-test-group"
    lock = get_red_envelope_group_lock(group_id)
    assert lock is get_red_envelope_group_lock(group_id)

    entered = []

    async def worker(name):
        async with get_red_envelope_group_lock(group_id):
            entered.append(f"{name}-start")
            await asyncio.sleep(0)
            entered.append(f"{name}-end")

    await asyncio.gather(worker("a"), worker("b"))

    assert entered in (
        ["a-start", "a-end", "b-start", "b-end"],
        ["b-start", "b-end", "a-start", "a-end"],
    )
