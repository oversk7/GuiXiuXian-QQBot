"""
红包服务

核心功能：
1. 发红包（含阶梯散财税）
2. 抢红包（含隐性天道偏移）
3. 过期红包清理
4. 红包记录查询
"""

import json
import math
import random
import time
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime, timedelta
from loguru import logger
from sqlalchemy import func, select

from ..models.red_envelope import RedEnvelope, RedEnvelopeStatus
from ..models.player import Player
from ..infrastructure.repositories.red_envelope_repository import RedEnvelopeRepository
from ..infrastructure.repositories.player_repository import PlayerRepository


# 发红包冷却记录: {player_id: timestamp}
_send_cooldowns: Dict[str, float] = {}

# 分区平均金币缓存: {server_id: (value, timestamp)}
_avg_gold_cache: Dict[int, Tuple[int, float]] = {}

# 冷却时间（秒）
SEND_COOLDOWN_SECONDS = 60

# 红包过期时间（分钟）
ENVELOPE_EXPIRE_MINUTES = 10

# 份数限制
MIN_COUNT = 1
MAX_COUNT = 20


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
        message: Optional[str] = None
    ) -> Tuple[bool, str, Optional[RedEnvelope]]:
        """发红包

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

        # 检查发送冷却
        now = time.time()
        last_send = _send_cooldowns.get(sender_id, 0)
        if now - last_send < SEND_COOLDOWN_SECONDS:
            remaining = int(SEND_COOLDOWN_SECONDS - (now - last_send))
            return False, f"发红包太频繁，请等待{remaining}秒", None

        # 获取发送者
        sender = await self._player_repo.get_by_id(sender_id)
        if not sender:
            return False, "玩家不存在", None
        server_id = sender.server_id

        # 检查本区本群是否有活跃红包
        active = await self._envelope_repo.find_active_by_group(group_id, server_id)
        if active:
            return False, "本群本区已有一个活跃红包，请等待抢完或过期后再发", None

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
            grab_records="[]",
            best_luck_player_id=None,
            best_luck_amount=0
        )

        await self._envelope_repo.add(envelope)

        # 更新冷却
        _send_cooldowns[sender_id] = now

        logger.info(f"红包发送成功: sender={sender_id}, total={total_gold}, tax={tax}, actual={actual_gold}, count={count}")

        return True, "红包发送成功", envelope

    async def grab_red_envelope(
        self,
        player_id: str,
        group_id: str
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """抢红包

        Args:
            player_id: 抢红包的玩家ID
            group_id: 群ID

        Returns:
            (成功标志, 消息, 抢红包信息{amount, is_last, envelope})
        """
        # 获取抢红包的玩家
        player = await self._player_repo.get_by_id(player_id)
        if not player:
            return False, "玩家不存在", None

        # 查找同区活跃红包
        envelope = await self._envelope_repo.find_active_by_group(group_id, player.server_id)
        if not envelope:
            return False, "当前群本区没有可抢的红包", None

        if envelope.server_id != player.server_id:
            return False, "不能抢其他区服的红包", None

        # 检查是否过期
        if datetime.now() > envelope.expires_at:
            # 触发过期处理
            await self._expire_envelope(envelope)
            return False, "红包已过期", None

        # 检查是否是自己发的
        if envelope.sender_id == player_id:
            return False, "不能抢自己发的红包", None

        # 检查是否已经抢过
        records = json.loads(envelope.grab_records)
        for record in records:
            if record["player_id"] == player_id:
                return False, f"你已经抢过了，获得了{record['amount']}金币", None

        # 计算份额
        avg_gold = await self._get_avg_player_gold(player.server_id)
        amount = self._calculate_share(
            envelope.remaining_gold,
            envelope.remaining_count,
            player.gold,
            avg_gold
        )

        # 发放金币
        player.gold += amount

        # 更新红包状态
        envelope.remaining_gold -= amount
        envelope.remaining_count -= 1

        # 更新最佳手气
        if amount > envelope.best_luck_amount:
            envelope.best_luck_amount = amount
            envelope.best_luck_player_id = player_id

        # 记录抢红包
        records.append({
            "player_id": player_id,
            "nickname": player.nickname,
            "amount": amount,
            "is_lucky": False  # 后续判定
        })

        # 检查是否抢完
        is_last = envelope.remaining_count <= 0
        if is_last:
            envelope.status = RedEnvelopeStatus.FINISHED.value
            # 标记最佳手气
            for record in records:
                if record["player_id"] == envelope.best_luck_player_id:
                    record["is_lucky"] = True

        envelope.grab_records = json.dumps(records, ensure_ascii=False)

        grab_info = {
            "amount": amount,
            "is_last": is_last,
            "envelope": envelope,
            "player_nickname": player.nickname
        }

        logger.info(f"抢红包: player={player_id}, amount={amount}, remaining={envelope.remaining_count}")

        return True, f"恭喜获得{amount}金币", grab_info

    async def expire_stale_envelopes(self) -> int:
        """清理过期红包，退还余额

        Returns:
            清理数量
        """
        expired_list = await self._envelope_repo.find_expired_envelopes()
        count = 0
        for envelope in expired_list:
            await self._expire_envelope(envelope)
            count += 1
        return count

    async def get_recent_records(self, group_id: str, server_id: int) -> List[RedEnvelope]:
        """获取群内最近红包记录"""
        return await self._envelope_repo.find_recent_by_group(group_id, server_id, limit=5)

    # ==================== 内部方法 ====================

    async def _expire_envelope(self, envelope: RedEnvelope) -> None:
        """处理红包过期，退还余额给发送者"""
        if envelope.status != RedEnvelopeStatus.ACTIVE.value:
            return

        envelope.status = RedEnvelopeStatus.EXPIRED.value

        # 退还剩余金币
        if envelope.remaining_gold > 0:
            sender = await self._player_repo.get_by_id(envelope.sender_id)
            if sender:
                sender.gold += envelope.remaining_gold
                logger.info(f"红包过期退还: sender={envelope.sender_id}, refund={envelope.remaining_gold}")

        # 如果有人抢过，标记最佳手气
        records = json.loads(envelope.grab_records)
        if records and envelope.best_luck_player_id:
            for record in records:
                if record["player_id"] == envelope.best_luck_player_id:
                    record["is_lucky"] = True
            envelope.grab_records = json.dumps(records, ensure_ascii=False)

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
    def _calculate_share(
        remaining_gold: int,
        remaining_count: int,
        grabber_gold: int,
        avg_gold: int
    ) -> int:
        """计算抢红包份额（双倍均值 + 隐性天道偏移）

        使用概率触发制：60%概率触发微弱的财富偏向（对数曲线，最高+25%），
        40%概率完全随机。单次抢红包看不出规律，但长期统计下穷玩家平均多~10%。

        Args:
            remaining_gold: 剩余金额
            remaining_count: 剩余份数
            grabber_gold: 抢红包者的金币数量
            avg_gold: 全服平均金币

        Returns:
            分配金额
        """
        # 最后一个人拿走全部
        if remaining_count <= 1:
            return remaining_gold

        # 双倍均值算法
        avg = remaining_gold / remaining_count
        upper = int(avg * 2)
        upper = max(upper, 1)  # 至少1
        base_share = random.randint(1, upper)

        # 隐性天道偏移：60%概率触发，使用对数曲线柔化
        if avg_gold > 0 and random.random() < 0.6:
            # 对数曲线：财富越多 ratio 越接近1，加成越小
            # log(1+x)/log(2) 在 x=0 时为0，x=1 时为1，增长逐渐放缓
            wealth_ratio = min(grabber_gold / avg_gold, 2.0)
            ratio = math.log(1 + wealth_ratio) / math.log(3)  # 0~1 柔化映射
            ratio = min(ratio, 1.0)
            luck_multiplier = 1.0 + (1.0 - ratio) * 0.25  # 1.0~1.25
            base_share = int(base_share * luck_multiplier)

        # 确保不超过剩余金额，且至少给后面的人留够每人1金币
        max_allowed = remaining_gold - (remaining_count - 1)
        base_share = max(1, min(base_share, max_allowed))

        return base_share

    async def _get_avg_player_gold(self, server_id: int) -> int:
        """获取本区平均金币（带30分钟缓存）"""
        global _avg_gold_cache
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
