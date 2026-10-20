"""
红包服务

核心功能：
1. 发红包（含阶梯散财税）
2. 准备抢红包参数（含隐性天道偏移；资格判断与扣减在 Redis 脚本里完成）
3. 红包记录查询

入账、过期关闭与对账见 red_envelope_settlement。
"""

import asyncio
import math
import random
import time
from dataclasses import dataclass
from typing import Optional, Tuple, List, Dict
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import func, select

from ..models.red_envelope import RedEnvelope, RedEnvelopeStatus
from ..models.player import Player
from .red_envelope_store import FACTOR_SCALE
from ..infrastructure.repositories.red_envelope_repository import RedEnvelopeRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


# 发红包冷却记录: {player_id: timestamp}
_send_cooldowns: Dict[str, float] = {}

# 分区平均金币缓存: {server_id: (value, timestamp)}
_avg_gold_cache: Dict[int, Tuple[int, float]] = {}

# 同群发红包串行锁。数据库行锁负责跨进程并发，该锁同时覆盖事务提交，
# 避免单进程内两个“无活跃红包”的事务同时创建红包。
_group_locks: Dict[str, asyncio.Lock] = {}


def get_red_envelope_group_lock(group_id: str) -> asyncio.Lock:
    lock = _group_locks.get(group_id)
    if lock is None:
        lock = asyncio.Lock()
        _group_locks[group_id] = lock
    return lock


# 冷却时间（秒）
SEND_COOLDOWN_SECONDS = 60

# 红包过期时间（分钟）
ENVELOPE_EXPIRE_MINUTES = 10

# 份数限制：按 QQ 群人数上限
MIN_COUNT = 1
MAX_COUNT = 500

# Lua 里用双精度算份额，金额必须远小于 2^53 才能保证整数精确
MAX_TOTAL_GOLD = 10**15


@dataclass(frozen=True)
class GrabPlan:
    """抢红包所需的参数，在数据库会话里准备好，离开会话后再访问 Redis。"""
    envelope_id: int
    player_id: str
    nickname: str
    factor: int


class RedEnvelopeService:
    """红包服务"""

    def __init__(
        self,
        envelope_repo: RedEnvelopeRepository,
        player_repo: PlayerRepository
    ):
        self._envelope_repo = envelope_repo
        self._player_repo = player_repo

    # ==================== 公开方法 ====================

    async def send_red_envelope(
        self,
        sender_id: str,
        group_id: str,
        total_gold: int,
        count: int,
        message: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[RedEnvelope]]:
        """发红包；调用方提交事务后负责初始化 Redis 状态

        Args:
            sender_id: 发送者玩家ID
            group_id: 群ID
            total_gold: 总金额
            count: 份数
            message: 红包留言（可选）

        Returns:
            (成功标志, 消息, 红包对象)
        """
        # 校验份数
        if count < MIN_COUNT or count > MAX_COUNT:
            return False, f"红包份数必须在{MIN_COUNT}-{MAX_COUNT}之间", None

        # 校验最低金额
        if total_gold < count:
            return False, f"金额太少，至少需要{count}金币（每份最低1金币）", None

        # 校验金额上限
        if total_gold <= 0:
            return False, "金额必须为正整数", None
        if total_gold > MAX_TOTAL_GOLD:
            return False, f"单个红包最多{MAX_TOTAL_GOLD // 10**12}万亿金币", None

        # 检查发送冷却
        now = time.time()
        last_send = _send_cooldowns.get(sender_id, 0)
        if now - last_send < SEND_COOLDOWN_SECONDS:
            remaining = int(SEND_COOLDOWN_SECONDS - (now - last_send))
            return False, f"发红包太频繁，请等待{remaining}秒", None

        # 先读取区服，再锁定群红包范围和发送者资产行。
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "玩家不存在", None
        server_id = sender.server_id

        active = await self._envelope_repo.find_active_by_group_for_update(group_id, server_id)
        if active:
            return False, "本群本区已有一个活跃红包，请等待抢完或过期后再发", None

        sender = await self._player_repo.get_by_id_for_update(sender_id)
        if not sender:
            return False, "玩家不存在", None

        # 计算税收
        tax = self._calculate_tax(total_gold)
        total_cost = total_gold  # 玩家支付的总金额（税前金额）

        # 检查金币够不够（玩家支付税前金额，税从中扣除）
        if sender.gold < total_cost:
            return False, f"金币不足！需要{total_cost}金币，你只有{sender.gold}金币", None

        # 扣除金币
        sender.gold -= total_cost
        actual_gold = total_gold - tax

        # 创建红包
        envelope = RedEnvelope(
            server_id=server_id,
            group_id=group_id,
            sender_id=sender_id,
            total_gold=total_gold,
            tax_amount=tax,
            actual_gold=actual_gold,
            total_count=count,
            remaining_gold=actual_gold,
            remaining_count=count,
            status=RedEnvelopeStatus.ACTIVE.value,
            message=message,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=ENVELOPE_EXPIRE_MINUTES),
        )

        await self._envelope_repo.add(envelope)

        # 更新冷却
        _send_cooldowns[sender_id] = now

        logger.info(f"红包发送成功: sender={sender_id}, total={total_gold}, tax={tax}, actual={actual_gold}, count={count}")

        return True, "红包发送成功", envelope

    async def prepare_grab(self, player: Player, group_id: str) -> Optional[GrabPlan]:
        """查本群活跃红包并算好分配系数；没有红包时返回 None。

        这里只做普通读取、不加锁，资格判断和扣减全部在 Redis 脚本里完成。
        """
        envelope = await self._envelope_repo.find_active_by_group(group_id, player.server_id)
        if envelope is None:
            return None
        avg_gold = await self._get_avg_player_gold(player.server_id)
        return GrabPlan(
            envelope_id=envelope.id,
            player_id=player.id,
            nickname=player.nickname or "",
            factor=self._share_factor(player.gold, avg_gold),
        )

    async def get_recent_records(self, group_id: str, server_id: int) -> List[RedEnvelope]:
        """获取群内最近红包记录"""
        return await self._envelope_repo.find_recent_by_group(group_id, server_id, limit=5)

    # ==================== 内部方法 ====================

    @staticmethod
    def _calculate_tax(total_gold: int) -> int:
        """计算阶梯散财税

        税率表：
        - ≤ 1万: 0%
        - 1万-10万: 3%
        - 10万-100万: 5%
        - 100万-1000万: 8%
        - > 1000万: 12%
        """
        if total_gold <= 10000:
            return 0

        tax = 0
        brackets = [
            (10000, 100000, 0.03),      # 1万-10万: 3%
            (100000, 1000000, 0.05),     # 10万-100万: 5%
            (1000000, 10000000, 0.08),   # 100万-1000万: 8%
            (10000000, float('inf'), 0.12),  # >1000万: 12%
        ]

        remaining = total_gold - 10000  # 1万以下免税

        for lower, upper, rate in brackets:
            if remaining <= 0:
                break
            bracket_size = upper - lower
            taxable = min(remaining, bracket_size)
            tax += int(taxable * rate)
            remaining -= taxable

        return tax

    @staticmethod
    def _luck_multiplier(grabber_gold: int, avg_gold: int) -> float:
        """隐性天道偏移：60%概率触发，使用对数曲线柔化，返回 1.0~1.25

        单次抢红包看不出规律，但长期统计下穷玩家平均多~10%。
        """
        if avg_gold > 0 and random.random() < 0.6:
            # 对数曲线：财富越多 ratio 越接近1，加成越小
            wealth_ratio = min(grabber_gold / avg_gold, 2.0)
            ratio = math.log(1 + wealth_ratio) / math.log(3)  # 0~1 柔化映射
            ratio = min(ratio, 1.0)
            return 1.0 + (1.0 - ratio) * 0.25
        return 1.0

    @staticmethod
    def _share_factor(grabber_gold: int, avg_gold: int) -> int:
        """分配系数（百万分之一）：份额 = 剩余均值 × 系数，即双倍均值 + 天道偏移。

        剩余金额只有 Redis 脚本里才知道，所以随机部分在这里算好，脚本只做算术和上下限
        （至少 1 金币，给后面每人留 1 金币，最后一人拿走全部剩余）。
        """
        factor = random.randint(1, 2 * FACTOR_SCALE)
        return int(factor * RedEnvelopeService._luck_multiplier(grabber_gold, avg_gold))

    async def _get_avg_player_gold(self, server_id: int) -> int:
        """获取本区平均金币（带30分钟缓存）"""
        now = time.time()
        cached_value, cached_time = _avg_gold_cache.get(server_id, (0, 0.0))

        # 30分钟缓存
        if now - cached_time < 1800 and cached_value > 0:
            return cached_value

        # 查询本区平均金币
        stmt = select(func.avg(Player.gold)).where(
            Player.server_id == server_id,
            Player.gold > 0
        )
        result = await self._envelope_repo._session.execute(stmt)
        avg_val = result.scalar()
        avg_gold = int(avg_val) if avg_val else 10000  # 默认1万

        _avg_gold_cache[server_id] = (avg_gold, now)
        return avg_gold
