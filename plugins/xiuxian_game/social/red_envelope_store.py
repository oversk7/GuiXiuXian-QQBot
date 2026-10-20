"""
红包的 Redis 状态：领取资格判断、份额扣减与入账消息。

Key（均带 RedisBackend 前缀）：
- red_envelope:{id}        Hash    status / remain_gold / remain_count / sender / expire_ms / keep_ms
- red_envelope:{id}:grabs  Hash    玩家ID -> 领取金额，判断"一人一次"
- red_envelope:settle      Stream  入账消息，消费者组 settler

抢红包脚本在一次原子执行里完成：查是否抢过 → 查状态和过期 → 算金额 → 扣减 → 记录领取人
→ 写入账消息。入账消息和扣减在同一个脚本里，不会出现"扣了份额却没有入账消息"。
份额用双精度计算，因此红包金额上限远小于 2^53（见 MAX_TOTAL_GOLD）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import IntEnum

from redis.exceptions import ResponseError

from ..infrastructure.redis_service import RedisBackend, get_redis_backend
from ..models.red_envelope import RedEnvelope

STREAM_NAME = "red_envelope:settle"
GROUP_NAME = "settler"
CONSUMER_NAME = "bot"

# 分配系数以百万分之一为单位传入脚本
FACTOR_SCALE = 1_000_000

# 关闭后 Redis 状态再保留一天，便于排查和对账
KEEP_AFTER_EXPIRE = timedelta(days=1)


# KEYS[1]=红包 Hash
# ARGV: 剩余金额, 剩余份数, 发送者, 过期毫秒, 保留到毫秒
_INIT_SCRIPT = """
if redis.call('EXISTS', KEYS[1]) == 1 then
    return 0
end
redis.call('HSET', KEYS[1], 'status', 'active', 'remain_gold', ARGV[1], 'remain_count', ARGV[2],
           'sender', ARGV[3], 'expire_ms', ARGV[4], 'keep_ms', ARGV[5])
redis.call('PEXPIREAT', KEYS[1], ARGV[5])
return 1
"""

# KEYS[1]=红包 Hash  KEYS[2]=领取 Hash  KEYS[3]=入账 Stream
# ARGV: 红包ID, 玩家ID, 昵称, 分配系数(百万分之一)
_GRAB_SCRIPT = """
local state = redis.call('HMGET', KEYS[1], 'status', 'expire_ms', 'sender',
                         'remain_gold', 'remain_count', 'keep_ms')
if not state[1] then
    return {-5}
end
local got = redis.call('HGET', KEYS[2], ARGV[2])
if got then
    return {-4, got}
end
if state[1] ~= 'active' then
    return {-1}
end
local now = redis.call('TIME')
if tonumber(now[1]) * 1000 + math.floor(tonumber(now[2]) / 1000) >= tonumber(state[2]) then
    return {-2}
end
if state[3] == ARGV[2] then
    return {-3}
end

local gold = tonumber(state[4])
local count = tonumber(state[5])
local amount
if count <= 1 then
    amount = gold
else
    amount = math.floor(gold / count * tonumber(ARGV[4]) / 1000000)
    -- 至少 1 金币，并给后面每人至少留 1 金币
    amount = math.max(1, math.min(amount, gold - (count - 1)))
end
local amount_text = string.format('%.0f', amount)

local left_gold = redis.call('HINCRBY', KEYS[1], 'remain_gold', '-' .. amount_text)
local left_count = redis.call('HINCRBY', KEYS[1], 'remain_count', -1)
redis.call('HSET', KEYS[2], ARGV[2], amount_text)
redis.call('PEXPIREAT', KEYS[2], state[6])
redis.call('XADD', KEYS[3], '*', 'type', 'grab', 'envelope', ARGV[1],
           'player', ARGV[2], 'nickname', ARGV[3], 'amount', amount_text)
if left_count == 0 then
    redis.call('HSET', KEYS[1], 'status', 'finished')
    redis.call('XADD', KEYS[3], '*', 'type', 'finished', 'envelope', ARGV[1])
end
return {1, amount_text, left_count, string.format('%.0f', left_gold)}
"""

# KEYS[1]=红包 Hash。关闭以后不会再有人抢成功，返回的剩余金额就是准确的应退金额。
_CLOSE_SCRIPT = """
local state = redis.call('HMGET', KEYS[1], 'status', 'remain_gold', 'remain_count')
if not state[1] then
    return {0}
end
if state[1] == 'active' then
    redis.call('HSET', KEYS[1], 'status', 'closed')
end
return {1, state[2], state[3]}
"""


class GrabStatus(IntEnum):
    OK = 1
    CLOSED = -1          # 已抢完或已关闭
    EXPIRED = -2
    OWN_ENVELOPE = -3
    ALREADY_GRABBED = -4
    MISSING = -5         # Redis 里没有这个红包（尚未初始化或状态丢失）


@dataclass(frozen=True)
class GrabResult:
    status: GrabStatus
    amount: int = 0
    remaining_count: int = 0
    remaining_gold: int = 0


@dataclass(frozen=True)
class CloseResult:
    found: bool
    remaining_gold: int = 0
    remaining_count: int = 0


@dataclass(frozen=True)
class SettleMessage:
    message_id: str
    kind: str
    envelope_id: int
    player_id: str = ""
    nickname: str = ""
    amount: int = 0


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


def _parse_entries(entries) -> list[SettleMessage]:
    messages = []
    for message_id, fields in entries:
        if not fields:
            # 待确认列表里的条目已被删除，只剩 ID
            messages.append(SettleMessage(message_id, "missing", 0))
            continue
        messages.append(SettleMessage(
            message_id=message_id,
            kind=fields.get("type", ""),
            envelope_id=int(fields.get("envelope", 0)),
            player_id=fields.get("player", ""),
            nickname=fields.get("nickname", ""),
            amount=int(fields.get("amount", 0)),
        ))
    return messages


class RedEnvelopeStore:
    def __init__(self, backend: RedisBackend) -> None:
        self._backend = backend

    @property
    def configured(self) -> bool:
        return self._backend.configured

    def _envelope_key(self, envelope_id: int) -> str:
        return self._backend.key(f"red_envelope:{envelope_id}")

    def _grabs_key(self, envelope_id: int) -> str:
        return self._backend.key(f"red_envelope:{envelope_id}:grabs")

    @property
    def stream_key(self) -> str:
        return self._backend.key(STREAM_NAME)

    # ==================== 红包状态 ====================

    async def init_envelope(self, envelope: RedEnvelope) -> None:
        """初始化红包状态；重复调用不会覆盖已有状态。"""
        await self._backend.command(
            "eval", _INIT_SCRIPT, 1, self._envelope_key(envelope.id),
            envelope.remaining_gold, envelope.remaining_count, envelope.sender_id,
            _epoch_ms(envelope.expires_at), _epoch_ms(envelope.expires_at + KEEP_AFTER_EXPIRE),
        )

    async def grab(
        self, envelope_id: int, player_id: str, nickname: str, factor: int
    ) -> GrabResult:
        reply = await self._backend.command(
            "eval", _GRAB_SCRIPT, 3,
            self._envelope_key(envelope_id), self._grabs_key(envelope_id), self.stream_key,
            envelope_id, player_id, nickname, factor,
        )
        status = GrabStatus(int(reply[0]))
        if status == GrabStatus.OK:
            return GrabResult(status, int(reply[1]), int(reply[2]), int(reply[3]))
        if status == GrabStatus.ALREADY_GRABBED:
            return GrabResult(status, int(reply[1]))
        return GrabResult(status)

    async def close(self, envelope_id: int) -> CloseResult:
        reply = await self._backend.command(
            "eval", _CLOSE_SCRIPT, 1, self._envelope_key(envelope_id)
        )
        if not int(reply[0]):
            return CloseResult(found=False)
        return CloseResult(True, int(reply[1]), int(reply[2]))

    # ==================== 入账消息 ====================

    async def ensure_group(self) -> None:
        # 从 0 开始：已确认的消息都会被删除，Stream 里剩下的都是没处理过的。
        try:
            await self._backend.command(
                "xgroup_create", self.stream_key, GROUP_NAME, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def read_new(self, count: int) -> list[SettleMessage]:
        return await self._read(">", count)

    async def read_pending(self, count: int) -> list[SettleMessage]:
        """重新读取本消费者已领取但未确认的消息（进程重启或上次处理失败）。"""
        return await self._read("0", count)

    async def _read(self, start: str, count: int) -> list[SettleMessage]:
        reply = await self._backend.command(
            "xreadgroup", GROUP_NAME, CONSUMER_NAME, {self.stream_key: start}, count=count
        )
        messages = []
        for _, entries in reply or []:
            messages.extend(_parse_entries(entries))
        return messages

    async def pending_deliveries(self, count: int) -> dict[str, int]:
        """未确认消息 ID -> 已投递次数"""
        rows = await self._backend.command(
            "xpending_range", self.stream_key, GROUP_NAME, "-", "+", count
        )
        return {row["message_id"]: int(row["times_delivered"]) for row in rows}

    async def fetch(self, message_id: str) -> SettleMessage | None:
        entries = await self._backend.command("xrange", self.stream_key, message_id, message_id)
        messages = _parse_entries(entries)
        return messages[0] if messages else None

    async def ack(self, message_ids: list[str]) -> None:
        """确认并删除，Stream 里只留下没处理完的消息。"""
        if not message_ids:
            return
        await self._backend.command("xack", self.stream_key, GROUP_NAME, *message_ids)
        await self._backend.command("xdel", self.stream_key, *message_ids)


def get_red_envelope_store() -> RedEnvelopeStore:
    return RedEnvelopeStore(get_redis_backend())
