"""红包的入账、关闭退款与对账（需要 GUIX_REDIS_TEST_URL）。

设置 GUIX_MYSQL_TEST_URL 时使用真实 MySQL，否则使用临时 SQLite。
"""

import asyncio
import os
from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm.exc import StaleDataError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from plugins.xiuxian_game.infrastructure.repositories.player_repository import PlayerRepository
from plugins.xiuxian_game.infrastructure.repositories.red_envelope_repository import (
    RedEnvelopeRepository,
)
from plugins.xiuxian_game.models.db import Base
from plugins.xiuxian_game.models.player import Player
from plugins.xiuxian_game.models.red_envelope import (
    ReconcileState,
    RedEnvelope,
    RedEnvelopeGrab,
    RedEnvelopeStatus,
)
from plugins.xiuxian_game.social import red_envelope_settlement as settlement
from plugins.xiuxian_game.social.red_envelope_service import RedEnvelopeService
from plugins.xiuxian_game.social.red_envelope_settlement import (
    RedEnvelopeSettler,
    cancel_uninitialized,
    close_expired_envelopes,
    reconcile_envelopes,
    settle_message,
)
from plugins.xiuxian_game.social.red_envelope_store import (
    FACTOR_SCALE,
    GrabStatus,
    RedEnvelopeStore,
    SettleMessage,
)
from tests.mysql_helpers import mysql_session_factory  # noqa: F401
from tests.redis_helpers import redis_backend_factory  # noqa: F401


@pytest.fixture
def factory(request):
    use_mysql = bool(os.environ.get("GUIX_MYSQL_TEST_URL", "").strip())
    return request.getfixturevalue("mysql_session_factory" if use_mysql else "sqlite_session_factory")


@pytest.fixture
async def sqlite_session_factory(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{(tmp_path / 'envelope.db').as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()


@pytest.fixture
async def store(redis_backend_factory):  # noqa: F811
    store = RedEnvelopeStore(redis_backend_factory(timeout_seconds=2))
    await store.ensure_group()
    return store


async def _seed(factory, grabbers=0, *, actual=10_000, count=5, sender_gold=0, expires_in=timedelta(minutes=10)):
    async with factory() as session:
        session.add(Player(id="sender", uid=1, nickname="发包人", gold=sender_gold))
        for i in range(grabbers):
            session.add(Player(id=f"p{i}", uid=100 + i, nickname=f"玩家{i}", gold=0))
        envelope = RedEnvelope(
            server_id=1, group_id="g", sender_id="sender",
            total_gold=actual + 100, tax_amount=100, actual_gold=actual,
            total_count=count, remaining_gold=actual, remaining_count=count,
            status=RedEnvelopeStatus.ACTIVE.value,
            expires_at=datetime.now() + expires_in,
        )
        session.add(envelope)
        await session.commit()
        return envelope


async def _gold(factory, player_id):
    async with factory() as session:
        return await session.scalar(select(Player.gold).where(Player.id == player_id))


async def _envelope(factory, envelope_id):
    async with factory() as session:
        return await session.get(RedEnvelope, envelope_id)


async def _grabbed(factory, envelope_id):
    async with factory() as session:
        return int(await session.scalar(
            select(func.coalesce(func.sum(RedEnvelopeGrab.amount), 0))
            .where(RedEnvelopeGrab.envelope_id == envelope_id)
        ))


async def _drain(settler):
    while await settler.run_once():
        pass


async def _expire(factory, envelope_id, ago=timedelta(minutes=11)):
    async with factory() as session:
        envelope = await session.get(RedEnvelope, envelope_id)
        envelope.expires_at = datetime.now() - ago
        await session.commit()


async def test_concurrent_grabs_settle_exactly_once(factory, store):
    envelope = await _seed(factory, grabbers=60, actual=100_000, count=50)
    await store.init_envelope(envelope)

    results = await asyncio.gather(
        *(store.grab(envelope.id, f"p{i}", f"玩家{i}", FACTOR_SCALE) for i in range(60))
    )
    won = {f"p{i}": r.amount for i, r in enumerate(results) if r.status == GrabStatus.OK}
    assert len(won) == 50

    settler = RedEnvelopeSettler(store, factory, retry_interval=0)
    await _drain(settler)

    assert await _grabbed(factory, envelope.id) == 100_000
    for player_id, amount in won.items():
        assert await _gold(factory, player_id) == amount
    final = await _envelope(factory, envelope.id)
    assert final.status == RedEnvelopeStatus.FINISHED.value
    # 每条领取都从数据库剩余里扣，全部入账后正好扣完
    assert (final.remaining_gold, final.remaining_count) == (0, 0)
    assert await store.read_pending(100) == []


async def test_redelivered_message_is_not_credited_twice(factory, store):
    envelope = await _seed(factory, grabbers=1)
    await store.init_envelope(envelope)
    await store.grab(envelope.id, "p0", "玩家0", FACTOR_SCALE)
    message = (await store.read_new(10))[0]

    await settle_message(message, factory)
    gold = await _gold(factory, "p0")
    # 模拟入账已提交、确认之前进程退出，消息再次投递
    await settle_message(message, factory)

    assert await _gold(factory, "p0") == gold == message.amount
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(RedEnvelopeGrab)) == 1


async def test_failing_message_is_retried_then_dead_lettered_and_compensated(
    factory, store, monkeypatch
):
    envelope = await _seed(factory, grabbers=2, actual=1_000, count=2)
    await store.init_envelope(envelope)
    await store.grab(envelope.id, "p0", "玩家0", FACTOR_SCALE)
    lost = await store.grab(envelope.id, "p1", "玩家1", FACTOR_SCALE)

    original = settlement.settle_message

    async def flaky(message, session_factory=None):
        if message.player_id == "p1":
            raise OperationalError("UPDATE", {}, Exception("模拟数据库故障"))
        await original(message, session_factory)

    monkeypatch.setattr(settlement, "settle_message", flaky)
    settler = RedEnvelopeSettler(store, factory, retry_interval=0)
    for _ in range(settlement.MAX_DELIVERIES + 1):
        await settler.run_once()

    assert await store.read_pending(10) == []
    assert await _gold(factory, "p1") == 0

    await _expire(factory, envelope.id)
    await close_expired_envelopes(store, factory)
    summary = await reconcile_envelopes(factory)

    assert summary == {ReconcileState.COMPENSATED: 1}
    assert await _gold(factory, "sender") == lost.amount
    final = await _envelope(factory, envelope.id)
    assert await _grabbed(factory, envelope.id) + final.refund_gold == final.actual_gold
    assert final.remaining_gold == 0


async def test_close_refunds_redis_remaining_once_even_before_settlement(factory, store):
    envelope = await _seed(factory, grabbers=3, actual=9_000, count=5)
    await store.init_envelope(envelope)
    grabs = [await store.grab(envelope.id, f"p{i}", "", FACTOR_SCALE) for i in range(3)]
    taken = sum(g.amount for g in grabs)

    await _expire(factory, envelope.id)
    # 入账消息还没消费，数据库里没有任何领取记录；退款仍然必须按 Redis 剩余算
    assert await close_expired_envelopes(store, factory) == 1
    assert await close_expired_envelopes(store, factory) == 0

    assert await _gold(factory, "sender") == 9_000 - taken
    closed = await _envelope(factory, envelope.id)
    assert closed.status == RedEnvelopeStatus.EXPIRED.value
    assert closed.refund_gold == 9_000 - taken
    assert (await store.grab(envelope.id, "p3", "", FACTOR_SCALE)).status == GrabStatus.CLOSED

    # 退款已从数据库剩余里扣掉，剩下的正好是还在路上的领取
    assert closed.remaining_gold == taken

    await _drain(RedEnvelopeSettler(store, factory, retry_interval=0))
    for i, grab in enumerate(grabs):
        assert await _gold(factory, f"p{i}") == grab.amount
    settled = await _envelope(factory, envelope.id)
    assert (settled.remaining_gold, settled.remaining_count) == (0, 2)
    assert await reconcile_envelopes(factory) == {ReconcileState.CONSISTENT: 1}
    assert await _gold(factory, "sender") == 9_000 - taken


async def test_close_without_redis_state_refunds_only_unsettled_gold(factory, store):
    envelope = await _seed(factory, grabbers=1, actual=5_000)
    async with factory() as session:
        session.add(RedEnvelopeGrab(envelope_id=envelope.id, player_id="p0", amount=1_200))
        await session.commit()
    await _expire(factory, envelope.id)

    assert await close_expired_envelopes(store, factory) == 1

    assert await _gold(factory, "sender") == 3_800
    assert await reconcile_envelopes(factory) == {ReconcileState.CONSISTENT: 1}


async def test_settlement_refuses_to_overdraw_envelope(factory):
    # 模拟 Redis 丢过数据、同一份钱被重复发放：数据库剩余不够时整笔不入账
    envelope = await _seed(factory, grabbers=2, actual=1_000, count=2)

    def grab(player_id, amount):
        return SettleMessage(
            message_id=f"0-{player_id}", kind="grab", envelope_id=envelope.id,
            player_id=player_id, amount=amount,
        )

    await settle_message(grab("p0", 700), factory)
    await settle_message(grab("p1", 700), factory)

    assert await _gold(factory, "p0") == 700
    assert await _gold(factory, "p1") == 0
    assert await _grabbed(factory, envelope.id) == 700
    stored = await _envelope(factory, envelope.id)
    assert (stored.remaining_gold, stored.remaining_count) == (300, 1)


async def test_close_never_refunds_more_than_db_remaining(factory, store):
    envelope = await _seed(factory, actual=1_000)
    await store.init_envelope(envelope)
    async with factory() as session:
        # Redis 剩余 1000，数据库只剩 400：只可能是 Redis 丢过数据
        stored = await session.get(RedEnvelope, envelope.id)
        stored.remaining_gold = 400
        await session.commit()
    await _expire(factory, envelope.id)

    assert await close_expired_envelopes(store, factory) == 1

    assert await _gold(factory, "sender") == 400
    closed = await _envelope(factory, envelope.id)
    assert (closed.refund_gold, closed.remaining_gold) == (400, 0)


async def test_reconcile_flags_overpaid_without_touching_balances(factory):
    envelope = await _seed(factory, grabbers=2, actual=1_000, count=2)
    async with factory() as session:
        session.add(RedEnvelopeGrab(envelope_id=envelope.id, player_id="p0", amount=1_000))
        session.add(RedEnvelopeGrab(envelope_id=envelope.id, player_id="p1", amount=1_000))
        stored = await session.get(RedEnvelope, envelope.id)
        stored.status = RedEnvelopeStatus.FINISHED.value
        stored.expires_at = datetime.now() - timedelta(minutes=11)
        await session.commit()

    assert await reconcile_envelopes(factory) == {ReconcileState.OVERPAID: 1}
    assert await reconcile_envelopes(factory) == {}
    assert await _gold(factory, "sender") == 0


async def test_cancel_uninitialized_refunds_everything_once(factory):
    envelope = await _seed(factory, actual=1_000)

    assert await cancel_uninitialized(envelope.id, factory) is True
    assert await cancel_uninitialized(envelope.id, factory) is False

    assert await _gold(factory, "sender") == 1_100  # 含散财税
    assert await reconcile_envelopes(factory) == {}


async def test_legacy_envelopes_are_closed_by_db_remaining_and_never_reconciled(factory, store):
    # 改造前上线时还在进行中的旧红包：没有 Redis 状态，领取记录在 JSON 里，数据库剩余是准的
    envelope = await _seed(factory, actual=1_000)
    async with factory() as session:
        stored = await session.get(RedEnvelope, envelope.id)
        stored.remaining_gold = 300
        stored.grab_records = '[{"player_id": "old", "amount": 700}]'
        stored.reconcile_state = None
        await session.commit()
    await _expire(factory, envelope.id)

    assert await close_expired_envelopes(store, factory) == 1

    assert await _gold(factory, "sender") == 300
    assert await reconcile_envelopes(factory) == {}
    assert await _gold(factory, "sender") == 300


async def test_historical_envelopes_are_not_reconciled(factory):
    envelope = await _seed(factory, actual=1_000)
    async with factory() as session:
        stored = await session.get(RedEnvelope, envelope.id)
        stored.status = RedEnvelopeStatus.FINISHED.value
        stored.reconcile_state = None
        stored.expires_at = datetime.now() - timedelta(days=30)
        await session.commit()

    assert await reconcile_envelopes(factory) == {}
    assert await _gold(factory, "sender") == 0


async def test_credit_bumps_version_so_stale_writers_cannot_overwrite(factory, store):
    envelope = await _seed(factory, grabbers=1, actual=500, count=1)
    await store.init_envelope(envelope)
    await store.grab(envelope.id, "p0", "", FACTOR_SCALE)

    async with factory() as stale:
        player = await stale.get(Player, "p0")
        await _drain(RedEnvelopeSettler(store, factory, retry_interval=0))
        player.gold += 1  # 基于入账前快照的写入
        with pytest.raises(StaleDataError):
            await stale.commit()
    assert await _gold(factory, "p0") == 500


async def test_prepare_grab_reads_active_envelope_without_locking(factory):
    envelope = await _seed(factory, grabbers=1, actual=1_000)

    async with factory() as session:
        service = RedEnvelopeService(RedEnvelopeRepository(session), PlayerRepository(session))
        player = await session.get(Player, "p0")
        plan = await service.prepare_grab(player, "g")
        assert plan is not None
        assert plan.envelope_id == envelope.id
        assert 1 <= plan.factor <= int(2 * FACTOR_SCALE * 1.25)
        assert await service.prepare_grab(player, "other-group") is None


async def test_send_limits(factory):
    async with factory() as session:
        session.add(Player(id="rich", uid=9, nickname="富", gold=10**16))
        await session.commit()

    async with factory() as session:
        service = RedEnvelopeService(RedEnvelopeRepository(session), PlayerRepository(session))
        ok, msg, _ = await service.send_red_envelope("rich", "g1", 1_000, 501)
        assert not ok and "1-500" in msg
        ok, msg, _ = await service.send_red_envelope("rich", "g3", 10**15 + 1, 2)
        assert not ok and "1000万亿" in msg
        ok, _, envelope = await service.send_red_envelope("rich", "g2", 1_000, 500)
        assert ok and envelope.reconcile_state == ReconcileState.PENDING.value
        await session.rollback()
