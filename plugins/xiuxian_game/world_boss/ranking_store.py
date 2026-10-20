"""世界BOSS伤害排行的 Redis 状态：每个"期数 + 区服 + 段位"一个 ZSet。

成员是玩家 ID，分数是本期累计伤害。伤害真账和发奖都在 MySQL 的 world_boss_damage，
这里只负责展示排行；数据丢了可以从 MySQL 重建。
"""

from __future__ import annotations

from datetime import datetime

from ..infrastructure.redis_service import RedisBackend, get_redis_backend

# KEYS: 本期本区各段位的 ZSet，按段位从低到高
# ARGV[1]: 过期的毫秒时间戳；之后每 3 个一组：玩家 ID、段位下标（从 1 开始）、累计伤害
# 写的是累计伤害的绝对值，只有比现有分数大才更新（相当于 Redis 6.2 的 ZADD GT），
# 重试或写入顺序颠倒都不会让旧值覆盖新值。段位只升不降：更高段位里已经有这个玩家，
# 说明这条是转生前的旧数据，直接跳过；否则先从更低段位删掉，实现中途转生的搬迁。
_UPSERT_SCRIPT = """
local expire_at = tonumber(ARGV[1])
for i = 2, #ARGV, 3 do
    local member, tier = ARGV[i], tonumber(ARGV[i + 1])
    local stale = false
    for t = tier + 1, #KEYS do
        if redis.call('ZSCORE', KEYS[t], member) then
            stale = true
            break
        end
    end
    if not stale then
        for t = 1, tier - 1 do
            redis.call('ZREM', KEYS[t], member)
        end
        local current = redis.call('ZSCORE', KEYS[tier], member)
        if (not current) or tonumber(ARGV[i + 2]) > tonumber(current) then
            redis.call('ZADD', KEYS[tier], ARGV[i + 2], member)
            redis.call('PEXPIREAT', KEYS[tier], expire_at)
        end
    end
end
return 1
"""

# 重建时每次脚本调用最多写入的人数，避免单条命令过大
REBUILD_BATCH = 200


def _epoch_ms(moment: datetime) -> int:
    return int(moment.timestamp() * 1000)


class WorldBossRankingStore:
    def __init__(self, backend: RedisBackend, tier_count: int) -> None:
        self._backend = backend
        self._tier_count = tier_count

    @property
    def configured(self) -> bool:
        return self._backend.configured

    def _key(self, cycle_id: int, server_id: int, tier: int) -> str:
        return self._backend.key(f"world_boss:{cycle_id}:{server_id}:{tier}")

    def _ready_key(self, cycle_id: int, server_id: int) -> str:
        return self._backend.key(f"world_boss:{cycle_id}:{server_id}:ready")

    def _tier_keys(self, cycle_id: int, server_id: int) -> list[str]:
        return [self._key(cycle_id, server_id, tier) for tier in range(self._tier_count)]

    async def upsert(
        self, cycle_id: int, server_id: int, entries: list[tuple[str, int, int]], expire_at: datetime
    ) -> None:
        """写入 (玩家ID, 段位, 累计伤害)；可重复执行。"""
        keys = self._tier_keys(cycle_id, server_id)
        for start in range(0, len(entries), REBUILD_BATCH):
            args = [_epoch_ms(expire_at)]
            for player_id, tier, damage in entries[start:start + REBUILD_BATCH]:
                args.extend([player_id, tier + 1, damage])
            await self._backend.command("eval", _UPSERT_SCRIPT, len(keys), *keys, *args)

    async def top(self, cycle_id: int, server_id: int, tier: int, limit: int) -> list[tuple[str, int]]:
        rows = await self._backend.command(
            "zrevrange", self._key(cycle_id, server_id, tier), 0, limit - 1, withscores=True
        )
        return [(player_id, int(score)) for player_id, score in rows]

    async def count(self, cycle_id: int, server_id: int, tier: int) -> int:
        return int(await self._backend.command("zcard", self._key(cycle_id, server_id, tier)))

    async def rank(self, cycle_id: int, server_id: int, tier: int, player_id: str) -> int | None:
        """名次从 1 开始；不在榜上返回 None"""
        rank = await self._backend.command(
            "zrevrank", self._key(cycle_id, server_id, tier), player_id
        )
        return None if rank is None else int(rank) + 1

    async def is_ready(self, cycle_id: int, server_id: int) -> bool:
        return bool(await self._backend.command("exists", self._ready_key(cycle_id, server_id)))

    async def mark_ready(self, cycle_id: int, server_id: int, expire_at: datetime) -> None:
        # 生产 Redis 是 6.0，SET 还不支持 PXAT，按剩余毫秒数设置过期
        ttl_ms = max(1, _epoch_ms(expire_at) - _epoch_ms(datetime.now()))
        await self._backend.command("set", self._ready_key(cycle_id, server_id), "1", px=ttl_ms)


def get_world_boss_ranking_store(tier_count: int) -> WorldBossRankingStore:
    return WorldBossRankingStore(get_redis_backend(), tier_count)
