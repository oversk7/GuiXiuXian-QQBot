import asyncio
import json
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.red_envelope_repository import (
    RedEnvelopeRepository,
)
from plugins.xiuxian_game.social import red_envelope_service as service_module
from plugins.xiuxian_game.social.red_envelope_service import (
    RedEnvelopeService,
    get_red_envelope_group_lock,
)


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
    player = SimpleNamespace()
    session = _StatementSession([player])

    actual = await PlayerRepository(session).get_by_id_for_update("player-1")

    assert actual is player
    assert session.statement._for_update_arg is not None
    assert session.statement.get_execution_options()["populate_existing"] is True


async def test_grab_uses_locked_envelope_and_player_rows():
    calls = []
    player = SimpleNamespace(
        id="grabber",
        server_id=1,
        nickname="领取者",
        gold=100,
    )
    envelope = SimpleNamespace(
        sender_id="sender",
        server_id=1,
        expires_at=datetime.now() + timedelta(minutes=5),
        remaining_gold=1000,
        remaining_count=1,
        best_luck_amount=0,
        best_luck_player_id=None,
        grab_records="[]",
        status="active",
    )

    class _EnvelopeRepo:
        _session = None

        async def find_active_by_group_for_update(self, group_id, server_id):
            calls.append(("envelope", group_id, server_id))
            return envelope

    class _PlayerRepo:
        async def get_by_id(self, player_id):
            calls.append(("player_read", player_id))
            return player

        async def get_by_id_for_update(self, player_id):
            calls.append(("player_lock", player_id))
            return player

    service_module._avg_gold_cache[1] = (1000, time.time())
    service = RedEnvelopeService(_EnvelopeRepo(), _PlayerRepo())

    success, _, info = await service.grab_red_envelope("grabber", "group-1")

    assert success is True
    assert info["amount"] == 1000
    assert player.gold == 1100
    assert envelope.remaining_count == 0
    assert envelope.remaining_gold == 0
    assert envelope.status == "finished"
    assert json.loads(envelope.grab_records)[0]["player_id"] == "grabber"
    assert calls == [
        ("player_read", "grabber"),
        ("envelope", "group-1", 1),
        ("player_lock", "grabber"),
    ]


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
