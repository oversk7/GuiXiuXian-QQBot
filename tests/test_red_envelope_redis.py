"""红包：Lua 脚本的原子性与入账消息（需要 GUIX_REDIS_TEST_URL）。"""

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from plugins.xiuxian_game.social.red_envelope_store import (
    FACTOR_SCALE,
    GrabStatus,
    RedEnvelopeStore,
)
from tests.redis_helpers import redis_backend_factory  # noqa: F401


def _envelope(envelope_id=1, gold=10_000, count=5, sender="sender", minutes=10):
    return SimpleNamespace(
        id=envelope_id,
        remaining_gold=gold,
        remaining_count=count,
        sender_id=sender,
        expires_at=datetime.now() + timedelta(minutes=minutes),
    )


@pytest.fixture
async def store(redis_backend_factory):  # noqa: F811
    store = RedEnvelopeStore(redis_backend_factory(timeout_seconds=2))
    await store.ensure_group()
    return store


async def _stream(store):
    messages = await store.read_new(10_000)
    return [m for m in messages if m.kind == "grab"], [m for m in messages if m.kind == "finished"]


async def test_concurrent_grabs_never_exceed_shares_or_amount(store):
    envelope = _envelope(gold=1_000_000, count=500)
    await store.init_envelope(envelope)

    async def grab(index):
        return await store.grab(envelope.id, f"p{index}", f"玩家{index}", FACTOR_SCALE)

    results = await asyncio.gather(*(grab(i) for i in range(600)))

    won = [r for r in results if r.status == GrabStatus.OK]
    assert len(won) == 500
    assert sum(r.amount for r in won) == 1_000_000
    assert all(r.amount >= 1 for r in won)
    assert {r.status for r in results if r.status != GrabStatus.OK} == {GrabStatus.CLOSED}

    grabs, finished = await _stream(store)
    assert len(grabs) == 500
    assert len({m.player_id for m in grabs}) == 500
    assert sum(m.amount for m in grabs) == 1_000_000
    assert [m.envelope_id for m in finished] == [envelope.id]


async def test_same_player_concurrent_grabs_succeed_once(store):
    envelope = _envelope(gold=1_000, count=10)
    await store.init_envelope(envelope)

    results = await asyncio.gather(
        *(store.grab(envelope.id, "same", "同一人", FACTOR_SCALE) for _ in range(20))
    )

    ok = [r for r in results if r.status == GrabStatus.OK]
    assert len(ok) == 1
    repeats = [r for r in results if r.status == GrabStatus.ALREADY_GRABBED]
    assert len(repeats) == 19
    assert {r.amount for r in repeats} == {ok[0].amount}
    grabs, _ = await _stream(store)
    assert len(grabs) == 1


async def test_single_share_goes_to_exactly_one_of_many(store):
    # 2026-08 事故的刷法：1 份红包，多人同时抢
    envelope = _envelope(gold=239_800, count=1)
    await store.init_envelope(envelope)

    results = await asyncio.gather(
        *(store.grab(envelope.id, f"p{i}", "", FACTOR_SCALE) for i in range(3))
    )

    assert sorted(r.status for r in results) == [GrabStatus.CLOSED, GrabStatus.CLOSED, GrabStatus.OK]
    assert next(r for r in results if r.status == GrabStatus.OK).amount == 239_800


async def test_sender_expired_and_missing_envelopes_are_rejected(store):
    own = _envelope(envelope_id=1, sender="sender")
    expired = _envelope(envelope_id=2, minutes=-1)
    await store.init_envelope(own)
    await store.init_envelope(expired)

    assert (await store.grab(1, "sender", "", FACTOR_SCALE)).status == GrabStatus.OWN_ENVELOPE
    assert (await store.grab(2, "p", "", FACTOR_SCALE)).status == GrabStatus.EXPIRED
    assert (await store.grab(3, "p", "", FACTOR_SCALE)).status == GrabStatus.MISSING


async def test_init_does_not_overwrite_existing_state(store):
    envelope = _envelope(gold=100, count=2)
    await store.init_envelope(envelope)
    await store.grab(envelope.id, "p1", "", FACTOR_SCALE)

    await store.init_envelope(envelope)

    closed = await store.close(envelope.id)
    assert closed.remaining_count == 1


async def test_close_returns_exact_refund_and_blocks_later_grabs(store):
    envelope = _envelope(gold=10_000, count=5)
    await store.init_envelope(envelope)
    first = await store.grab(envelope.id, "p1", "", FACTOR_SCALE)

    closed = await store.close(envelope.id)
    again = await store.close(envelope.id)

    assert closed.found
    assert closed.remaining_gold == 10_000 - first.amount
    assert closed.remaining_count == 4
    assert again == closed
    assert (await store.grab(envelope.id, "p2", "", FACTOR_SCALE)).status == GrabStatus.CLOSED
    assert (await store.close(999)).found is False


async def test_close_racing_grabs_conserves_gold(store):
    envelope = _envelope(gold=50_000, count=100)
    await store.init_envelope(envelope)

    grab_tasks = [store.grab(envelope.id, f"p{i}", "", FACTOR_SCALE) for i in range(100)]
    results = await asyncio.gather(*grab_tasks[:50], store.close(envelope.id), *grab_tasks[50:])
    closed = results[50]
    grabs = [r for r in results[:50] + results[51:] if r.status == GrabStatus.OK]

    final = await store.close(envelope.id)
    assert final == closed
    assert sum(r.amount for r in grabs) + closed.remaining_gold == 50_000
    assert len(grabs) + closed.remaining_count == 100


async def test_large_amounts_stay_exact(store):
    gold = 10**15
    envelope = _envelope(gold=gold, count=3)
    await store.init_envelope(envelope)

    results = [await store.grab(envelope.id, f"p{i}", "", 2 * FACTOR_SCALE) for i in range(3)]

    assert all(r.status == GrabStatus.OK for r in results)
    assert sum(r.amount for r in results) == gold
    grabs, _ = await _stream(store)
    assert sum(m.amount for m in grabs) == gold


async def test_unacked_messages_are_redelivered_until_acked(store):
    envelope = _envelope(gold=100, count=2)
    await store.init_envelope(envelope)
    await store.grab(envelope.id, "p1", "", FACTOR_SCALE)

    first = await store.read_new(10)
    assert len(first) == 1
    assert await store.read_new(10) == []

    pending = await store.read_pending(10)
    assert [m.message_id for m in pending] == [first[0].message_id]
    deliveries = await store.pending_deliveries(10)
    assert deliveries[first[0].message_id] >= 2

    await store.ack([first[0].message_id])
    assert await store.read_pending(10) == []
    assert await store.fetch(first[0].message_id) is None
