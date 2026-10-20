"""
红包的落库：入账消费者、过期关闭退款、对账补偿。

- 入账：消费者从 Redis Stream 读入账消息，在一个事务里写领取记录并给玩家加金币，
  提交后确认消息。领取记录 (envelope_id, player_id) 唯一，消息重复只入账一次。
  未确认的消息留在待确认列表，进程重启后重新处理；投递超过 MAX_DELIVERIES 次记死信。
- 关闭：先用 Lua 关闭 Redis 状态，之后不会再有人抢成功，Redis 剩余金额就是应退金额；
  数据库用 status='active' 条件更新，只有改成功的那次退款。
- 对账：关闭一段时间后核对"已领总额 + 退款 = 实发金额"。少了把差额退给发送者，
  多了只告警，留给人工处理。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta

from loguru import logger
from redis.exceptions import ResponseError
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from ..infrastructure.redis_service import RedisUnavailable
from ..models.db import run_transaction
from ..models.player import Player
from ..models.red_envelope import (
    ReconcileState,
    RedEnvelope,
    RedEnvelopeGrab,
    RedEnvelopeStatus,
)
from .red_envelope_store import RedEnvelopeStore, SettleMessage

MAX_DELIVERIES = 5
# 关闭后等这么久再对账：失败消息此时要么已入账，要么已进死信
RECONCILE_DELAY = timedelta(minutes=10)


async def _credit_player(session, player_id: str, amount: int) -> bool:
    # 原子加法，不读旧值；同时推进版本号，持有旧玩家快照的事务提交时会冲突重试，
    # 不会用旧金币值覆盖这笔入账。
    result = await session.execute(
        update(Player)
        .where(Player.id == player_id)
        .values(gold=Player.gold + amount, version_id=Player.version_id + 1)
    )
    return result.rowcount == 1


# ==================== 入账 ====================

async def settle_message(message: SettleMessage, session_factory=None) -> None:
    """处理一条入账消息；抛出数据库异常时消息保持未确认，稍后重试。"""
    if message.kind == "grab":
        async def credit(session):
            session.add(RedEnvelopeGrab(
                envelope_id=message.envelope_id,
                player_id=message.player_id,
                nickname=message.nickname[:64],
                amount=message.amount,
            ))
            await session.flush()
            if not await _credit_player(session, message.player_id, message.amount):
                logger.warning(
                    f"[红包入账] 玩家不存在，记录领取但未加金币: envelope={message.envelope_id} "
                    f"player={message.player_id} amount={message.amount}"
                )

        try:
            await run_transaction(credit, session_factory=session_factory)
        except IntegrityError:
            # 唯一约束冲突：这条消息之前已经入过账（例如提交后、确认前进程退出）
            logger.info(
                f"[红包入账] 重复消息已跳过: envelope={message.envelope_id} player={message.player_id}"
            )
    elif message.kind == "finished":
        async def finish(session):
            await session.execute(
                update(RedEnvelope)
                .where(
                    RedEnvelope.id == message.envelope_id,
                    RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value,
                )
                .values(status=RedEnvelopeStatus.FINISHED.value, remaining_gold=0, remaining_count=0)
            )

        await run_transaction(finish, session_factory=session_factory)
    else:
        logger.warning(f"[红包入账] 未知消息已丢弃: id={message.message_id} type={message.kind}")


class RedEnvelopeSettler:
    """单实例的入账消费者，随机器人进程启动。"""

    def __init__(
        self,
        store: RedEnvelopeStore,
        session_factory=None,
        *,
        batch_size: int = 50,
        idle_wait: float = 1.0,
        retry_interval: float = 30.0,
        error_backoff: float = 5.0,
    ) -> None:
        self._store = store
        self._session_factory = session_factory
        self._batch_size = batch_size
        self._idle_wait = idle_wait
        self._retry_interval = retry_interval
        self._error_backoff = error_backoff
        self._wakeup = asyncio.Event()
        self._next_retry_at = 0.0  # 启动后先处理重启前没确认的消息

    def wake(self) -> None:
        """抢红包成功后调用，让消费者立刻处理，不必等下一次轮询。"""
        self._wakeup.set()

    async def process(self, messages: list[SettleMessage]) -> int:
        done = []
        for message in messages:
            if message.kind == "missing":
                done.append(message.message_id)
                continue
            try:
                await settle_message(message, self._session_factory)
            except SQLAlchemyError as exc:
                logger.error(
                    f"[红包入账] 处理失败，稍后重试: id={message.message_id} "
                    f"envelope={message.envelope_id} error={type(exc).__name__}"
                )
                continue
            done.append(message.message_id)
        await self._store.ack(done)
        return len(messages)

    async def retry_pending(self) -> None:
        deliveries = await self._store.pending_deliveries(self._batch_size)
        dead = [mid for mid, count in deliveries.items() if count >= MAX_DELIVERIES]
        for message_id in dead:
            message = await self._store.fetch(message_id)
            # 死信：不再重试，这笔钱由对账补偿给发送者
            logger.error(f"[红包入账] 死信: id={message_id} message={message}")
        await self._store.ack(dead)
        if len(dead) < len(deliveries):
            await self.process(await self._store.read_pending(self._batch_size))

    async def run_once(self) -> int:
        if time.monotonic() >= self._next_retry_at:
            self._next_retry_at = time.monotonic() + self._retry_interval
            await self.retry_pending()
        return await self.process(await self._store.read_new(self._batch_size))

    async def run_forever(self) -> None:
        while True:
            try:
                await self._store.ensure_group()
                break
            except RedisUnavailable:
                await asyncio.sleep(self._error_backoff)
        while True:
            try:
                handled = await self.run_once()
            except RedisUnavailable:
                await asyncio.sleep(self._error_backoff)
                continue
            except (ResponseError, SQLAlchemyError) as exc:
                logger.error(f"[红包入账] 消费循环出错，稍后重试: {type(exc).__name__}: {exc}")
                await asyncio.sleep(self._error_backoff)
                continue
            if handled:
                continue
            self._wakeup.clear()
            try:
                await asyncio.wait_for(self._wakeup.wait(), self._idle_wait)
            except asyncio.TimeoutError:
                pass


# ==================== 过期关闭与退款 ====================

async def _finalize(
    session, envelope_id: int, remaining_gold: int | None, remaining_count: int | None
) -> int | None:
    """回写最终状态并退款，返回退款金额；红包已被处理过时返回 None。"""
    envelope = await session.get(RedEnvelope, envelope_id)
    if envelope is None or envelope.status != RedEnvelopeStatus.ACTIVE.value:
        return None
    if remaining_gold is None:
        # Redis 里没有这个红包：状态丢了，没入账的领取消息也一起丢了，已入账的记录就是
        # 最终结果。改造前的旧红包同样没有 Redis 状态，它们的数据库剩余金额是准的，取较小值。
        granted = await session.scalar(
            select(func.coalesce(func.sum(RedEnvelopeGrab.amount), 0))
            .where(RedEnvelopeGrab.envelope_id == envelope_id)
        )
        remaining_gold = max(min(envelope.remaining_gold, envelope.actual_gold - int(granted)), 0)
        remaining_count = None
    status = (
        RedEnvelopeStatus.FINISHED if remaining_count == 0 else RedEnvelopeStatus.EXPIRED
    ).value
    values = dict(status=status, remaining_gold=remaining_gold, refund_gold=remaining_gold)
    if remaining_count is not None:
        values["remaining_count"] = remaining_count
    result = await session.execute(
        update(RedEnvelope)
        .where(RedEnvelope.id == envelope_id, RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value)
        .values(**values)
    )
    if result.rowcount != 1:
        return None
    if remaining_gold > 0:
        await _credit_player(session, envelope.sender_id, remaining_gold)
    return remaining_gold


async def close_expired_envelopes(store: RedEnvelopeStore, session_factory=None) -> int:
    """关闭已过期的红包并退款，返回处理数量。"""
    async def expired_ids(session):
        rows = await session.scalars(
            select(RedEnvelope.id).where(
                RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value,
                RedEnvelope.expires_at < datetime.now(),
            )
        )
        return list(rows)

    closed = 0
    for envelope_id in await run_transaction(expired_ids, session_factory=session_factory):
        try:
            state = await store.close(envelope_id)
        except RedisUnavailable:
            # 拿不到准确的剩余金额就不退款，下一轮再试
            logger.warning(f"[红包关闭] Redis 不可用，稍后重试: envelope={envelope_id}")
            continue
        if not state.found:
            logger.warning(f"[红包关闭] Redis 状态缺失，按已入账记录退款: envelope={envelope_id}")
        refund = await run_transaction(
            lambda session: _finalize(
                session, envelope_id,
                state.remaining_gold if state.found else None,
                state.remaining_count if state.found else None,
            ),
            session_factory=session_factory,
        )
        if refund is not None:
            closed += 1
            logger.info(f"[红包关闭] envelope={envelope_id} refund={refund}")
    return closed


async def cancel_uninitialized(envelope_id: int, session_factory=None) -> bool:
    """Redis 初始化失败的红包：直接关闭并全额退回（含散财税），视为对账一致。"""
    async def cancel(session):
        envelope = await session.get(RedEnvelope, envelope_id)
        result = await session.execute(
            update(RedEnvelope)
            .where(RedEnvelope.id == envelope_id, RedEnvelope.status == RedEnvelopeStatus.ACTIVE.value)
            .values(
                status=RedEnvelopeStatus.EXPIRED.value,
                refund_gold=envelope.total_gold,
                reconcile_state=ReconcileState.CONSISTENT.value,
            )
        )
        if result.rowcount != 1:
            return False
        await _credit_player(session, envelope.sender_id, envelope.total_gold)
        return True

    return await run_transaction(cancel, session_factory=session_factory)


# ==================== 对账 ====================

async def _reconcile_one(session, envelope_id: int) -> ReconcileState | None:
    envelope = await session.scalar(
        select(RedEnvelope).where(RedEnvelope.id == envelope_id).with_for_update()
    )
    if envelope is None or envelope.reconcile_state != ReconcileState.PENDING.value:
        return None
    granted = int(await session.scalar(
        select(func.coalesce(func.sum(RedEnvelopeGrab.amount), 0))
        .where(RedEnvelopeGrab.envelope_id == envelope_id)
    ))
    expected = envelope.actual_gold - envelope.refund_gold
    if granted == expected:
        state = ReconcileState.CONSISTENT
    elif granted < expected:
        # 有领取消息最终没能入账（死信），差额退给发送者，金币总量守恒
        diff = expected - granted
        envelope.refund_gold += diff
        await _credit_player(session, envelope.sender_id, diff)
        state = ReconcileState.COMPENSATED
        logger.warning(f"[红包对账] 少发已补偿: envelope={envelope_id} diff={diff}")
    else:
        # 只可能是 Redis 丢过数据导致重复发放，不自动扣回，交给人工
        state = ReconcileState.OVERPAID
        logger.error(
            f"[红包对账] 超发，需人工处理: envelope={envelope_id} "
            f"granted={granted} expected={expected}"
        )
    envelope.reconcile_state = state.value
    return state


async def reconcile_envelopes(session_factory=None) -> dict[ReconcileState, int]:
    async def due_ids(session):
        rows = await session.scalars(
            select(RedEnvelope.id).where(
                RedEnvelope.status != RedEnvelopeStatus.ACTIVE.value,
                # 旧红包为 NULL，不会被选中
                RedEnvelope.reconcile_state == ReconcileState.PENDING.value,
                RedEnvelope.expires_at < datetime.now() - RECONCILE_DELAY,
            )
        )
        return list(rows)

    summary: dict[ReconcileState, int] = {}
    for envelope_id in await run_transaction(due_ids, session_factory=session_factory):
        state = await run_transaction(
            lambda session: _reconcile_one(session, envelope_id),
            session_factory=session_factory,
        )
        if state is not None:
            summary[state] = summary.get(state, 0) + 1
    return summary


# ==================== 进程级单例 ====================

_settler: RedEnvelopeSettler | None = None


def get_settler() -> RedEnvelopeSettler | None:
    return _settler


def set_settler(settler: RedEnvelopeSettler | None) -> None:
    global _settler
    _settler = settler
