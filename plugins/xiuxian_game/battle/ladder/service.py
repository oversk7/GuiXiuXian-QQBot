"""斗法天梯核心服务

封装 ELO 计算、对手匹配、跑战斗、更新评分、单场奖励、赛季管理等业务逻辑。

设计要点：
- 异步快照匹配：QQ Bot 玩家不会同时在线，使用对手当前数据快照进行模拟
- 对称 ELO：守方与攻方积分变化等额，公平且防止匹配池稀释
- 懒加载赛季：每次访问检查赛季是否结束，是则结算并开新赛季
- 多重防滥用：评分差、关系排除、同对手冷却、连胜衰减、守方上限
"""
from __future__ import annotations

import logging
import random
import time
from datetime import datetime, date, timedelta
from typing import List, Optional, Tuple

from sqlalchemy import select, and_, or_, func as sql_func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ...models.player import Player
from ...models.player_relationship import PlayerRelationship, RelationshipType
from ...models.ladder import LadderRating, LadderMatchLog, LadderSeason
from ...models.monthly_card import get_player_card_benefits
from ..integration_helper import BattleIntegrationHelper

logger = logging.getLogger(__name__)


# ==================== 常量定义 ====================

# 段位阈值（按从低到高排序）
RANK_TIERS: List[Tuple[int, str]] = [
    (0, "散修"),
    (1000, "九品"),
    (1150, "八品"),
    (1300, "七品"),
    (1450, "六品"),
    (1600, "五品"),
    (1750, "四品"),
    (1900, "三品"),
    (2050, "二品"),
    (2200, "一品"),
    (2350, "道君"),
]

# 参赛门槛
MIN_LEVEL = 30
DEFAULT_RATING = 1000

# 每日匹配限制
DAILY_MATCHES_BASE = 5
DAILY_MATCHES_PREMIUM_BONUS = 3  # 高级月卡加成
DAILY_DEFENSE_LIMIT = 10  # 守方每日被匹配上限

# 防滥用
SAME_OPPONENT_COOLDOWN_HOURS = 6
MATCH_INTERVAL_SECONDS = 60
WIN_STREAK_DECAY_THRESHOLD = 10  # 连胜阈值

# 匹配评分差
RATING_RANGE_PRIMARY = 150
RATING_RANGE_FALLBACK = 300

# 候选采样上限
CANDIDATE_LIMIT = 30

# 单场奖励
SOUL_CRYSTALS_WIN = 100
SOUL_CRYSTALS_LOSE = 30
SOUL_CRYSTALS_DRAW = 60
SOUL_CRYSTALS_FIRST_WIN_BONUS = 200

# 赛季软重置
SOFT_RESET_THRESHOLD = 1500
SOFT_RESET_RATIO = 0.3


# ==================== 异常 ====================

class LadderError(Exception):
    """斗法天梯通用异常"""
    pass


class LadderMatchError(LadderError):
    """匹配/对战相关异常（用于命令层捕获并提示玩家）"""
    pass


# ==================== 服务类 ====================

class LadderRatingService:
    """斗法天梯核心服务

    用法：
        async with safe_session() as session:
            service = LadderRatingService(session)
            season = await service.get_or_create_active_season()
            result = await service.run_match(player)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ========== 段位/积分工具 ==========

    @staticmethod
    def get_rank_tier(rating: int) -> str:
        """根据积分计算段位名称"""
        tier = "散修"
        for threshold, name in RANK_TIERS:
            if rating >= threshold:
                tier = name
            else:
                break
        return tier

    @staticmethod
    def get_next_tier_info(rating: int) -> Tuple[Optional[str], int]:
        """返回 (下一段位名, 还差多少积分)；已是最高段位返回 (None, 0)"""
        for threshold, name in RANK_TIERS:
            if rating < threshold:
                return name, threshold - rating
        return None, 0

    @staticmethod
    def calculate_elo_change(
        rating_a: int, rating_b: int, result_a: float, k_factor: int
    ) -> int:
        """ELO 积分变化（A 视角）

        Args:
            rating_a: A 当前积分
            rating_b: B 当前积分
            result_a: A 的结果，1=胜, 0.5=平, 0=负
            k_factor: K 因子

        Returns:
            A 应得到的积分变化（可正可负）
        """
        expected_a = 1 / (1 + 10 ** ((rating_b - rating_a) / 400))
        return round(k_factor * (result_a - expected_a))

    @staticmethod
    def get_k_factor(rating: LadderRating) -> int:
        """根据玩家状态计算 K 因子"""
        if rating.matches_played < 30:
            return 40  # 定位赛
        if rating.rating >= 2350:
            return 16  # 道君段位
        return 24  # 常规

    # ========== 档案管理 ==========

    async def get_or_create_rating(self, player_id: str) -> LadderRating:
        """获取或创建玩家天梯档案"""
        stmt = select(LadderRating).where(LadderRating.player_id == player_id)
        rating = (await self.session.execute(stmt)).scalar_one_or_none()
        if rating:
            return rating

        rating = LadderRating(
            player_id=player_id,
            rating=DEFAULT_RATING,
            rank_tier=self.get_rank_tier(DEFAULT_RATING),
            best_rating=DEFAULT_RATING,
            daily_reset_at=date.today(),
        )
        self.session.add(rating)
        await self.session.flush()
        return rating

    async def reset_daily_counters_if_needed(self, rating: LadderRating) -> None:
        """如果跨天则重置每日计数器"""
        today = date.today()
        if rating.daily_reset_at != today:
            rating.daily_matches = 0
            rating.daily_defense_count = 0
            rating.daily_extra_matches = 0
            rating.daily_first_win_claimed = False
            rating.daily_shop_purchases = {}
            rating.daily_reset_at = today

    async def get_daily_match_quota(self, player_id: str, rating: LadderRating) -> int:
        """获取该玩家今日总可用匹配次数（基础 + 月卡 + 斗法令购买）"""
        quota = DAILY_MATCHES_BASE + rating.daily_extra_matches
        try:
            benefits = await get_player_card_benefits(self.session, player_id)
            if benefits.get("premium_active"):
                quota += DAILY_MATCHES_PREMIUM_BONUS
        except (ValueError, AttributeError, KeyError) as e:  # pragma: no cover - 月卡查询失败不影响主流程
            logger.warning(f"获取月卡权益失败: {e}")
        return quota

    # ========== 校验 ==========

    def _validate_attacker(self, attacker: Player, rating: LadderRating, daily_quota: int) -> None:
        """检查攻方是否满足匹配条件，不满足则抛 LadderMatchError"""
        if attacker.level < MIN_LEVEL:
            raise LadderMatchError(f"⛔ 境界 {MIN_LEVEL} 以上方可入斗法场")
        if attacker.hp <= 0:
            raise LadderMatchError("⛔ 你气血枯竭，需先养身后再战")
        if rating.daily_matches >= daily_quota:
            raise LadderMatchError(
                f"⛔ 今日残魂已耗尽（{rating.daily_matches}/{daily_quota}），明日再战"
            )
        if rating.last_match_at:
            elapsed = (datetime.now() - rating.last_match_at).total_seconds()
            if elapsed < MATCH_INTERVAL_SECONDS:
                wait = int(MATCH_INTERVAL_SECONDS - elapsed)
                raise LadderMatchError(f"⛔ 残魂尚需凝聚，请等待 {wait} 秒")

    # ========== 匹配 ==========

    async def _get_relationship_excluded(self, player_id: str) -> set[str]:
        """查询所有需要排除的关系户 ID（婚姻/结义/师徒）"""
        excluded: set[str] = set()
        stmt = select(PlayerRelationship).where(
            and_(
                or_(
                    PlayerRelationship.player_id == player_id,
                    PlayerRelationship.target_id == player_id,
                ),
                PlayerRelationship.relationship_type.in_([
                    RelationshipType.MENTORSHIP.value,
                    RelationshipType.SWORN.value,
                    RelationshipType.MARRIAGE.value,
                ]),
            )
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for r in rows:
            other = r.target_id if r.player_id == player_id else r.player_id
            if other:
                excluded.add(other)
        return excluded

    async def _get_recent_opponent_ids(self, player_id: str, hours: int) -> set[str]:
        """查询近 N 小时内对战过的对手 ID（用于同对手冷却）"""
        cutoff = datetime.now() - timedelta(hours=hours)
        stmt = select(LadderMatchLog).where(
            and_(
                LadderMatchLog.timestamp >= cutoff,
                or_(
                    LadderMatchLog.attacker_id == player_id,
                    LadderMatchLog.defender_id == player_id,
                ),
            )
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        opponents: set[str] = set()
        for log in rows:
            other = log.defender_id if log.attacker_id == player_id else log.attacker_id
            if other:
                opponents.add(other)
        return opponents

    async def _query_candidates(
        self,
        attacker_rating_value: int,
        rating_range: int,
        excluded_ids: set[str],
    ) -> List[Player]:
        """查询符合评分范围的候选守方玩家"""
        rating_low = attacker_rating_value - rating_range
        rating_high = attacker_rating_value + rating_range
        active_cutoff = datetime.now() - timedelta(days=30)

        stmt = (
            select(Player)
            .join(LadderRating, LadderRating.player_id == Player.id)
            .where(
                LadderRating.matchmaking_enabled.is_(True),
                LadderRating.daily_defense_count < DAILY_DEFENSE_LIMIT,
                LadderRating.rating.between(rating_low, rating_high),
                Player.level >= MIN_LEVEL,
                Player.hp > 0,
                or_(
                    Player.last_active_at.is_(None),
                    Player.last_active_at > active_cutoff,
                ),
            )
            .limit(CANDIDATE_LIMIT)
        )

        if excluded_ids:
            stmt = stmt.where(~Player.id.in_(excluded_ids))

        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def find_opponent(
        self, attacker: Player, attacker_rating: LadderRating
    ) -> Optional[Player]:
        """寻找一名匹配的对手；找不到返回 None"""
        excluded_ids = await self._get_relationship_excluded(attacker.id)
        excluded_ids.add(attacker.id)
        excluded_ids.update(
            await self._get_recent_opponent_ids(attacker.id, hours=SAME_OPPONENT_COOLDOWN_HOURS)
        )

        for rating_range in (RATING_RANGE_PRIMARY, RATING_RANGE_FALLBACK):
            candidates = await self._query_candidates(
                attacker_rating.rating, rating_range, excluded_ids
            )
            if candidates:
                return random.choice(candidates)
        return None

    # ========== 跑战斗 ==========

    async def run_match(self, attacker: Player) -> dict:
        """执行一场天梯对战

        Returns:
            dict: {
                "victory": bool,
                "battle_log": List[str],
                "defender": Player,
                "rating_change": int,           # 攻方积分变化
                "new_rating": int,              # 攻方新积分
                "new_rank": str,                # 攻方新段位
                "soul_earned": int,             # 攻方本场获得魂晶
                "first_win_bonus": bool,        # 是否触发首胜奖励
                "season_id": int,
                "match_log_id": int,
            }
        """
        # 0) 先确保赛季存在（避免 settle 重置覆盖本场更新）
        season = await self.get_or_create_active_season()

        # 1) 取/建评分（必须在 season 之后，因为 settle 会清零统计）
        a_rating = await self.get_or_create_rating(attacker.id)
        await self.reset_daily_counters_if_needed(a_rating)

        # 2) 校验
        daily_quota = await self.get_daily_match_quota(attacker.id, a_rating)
        self._validate_attacker(attacker, a_rating, daily_quota)

        # 3) 找对手
        defender = await self.find_opponent(attacker, a_rating)
        if not defender:
            raise LadderMatchError(
                "⛔ 斗法场中无凶名相当的残魂（同段位修士或已隐匿/冷却中）\n"
                "💡 稍后再来，或先去诡域里练练手"
            )

        d_rating = await self.get_or_create_rating(defender.id)
        await self.reset_daily_counters_if_needed(d_rating)

        # 记录积分快照
        a_rating_before = a_rating.rating
        d_rating_before = d_rating.rating

        # 4) 跑战斗
        seed = f"LADDER_{attacker.id}_{defender.id}_{int(time.time() * 1000)}"
        try:
            victory, battle_log, _, _ = await BattleIntegrationHelper.compact_player_vs_player_battle(
                attacker, defender, self.session, seed=seed, max_rounds=30
            )
        except ValueError as e:
            raise LadderMatchError(f"⛔ 战斗过程出错: {e}")

        # 5) ELO 计算
        result_a = 1.0 if victory else 0.0
        k_a = self.get_k_factor(a_rating)
        raw_change = self.calculate_elo_change(a_rating_before, d_rating_before, result_a, k_a)

        # 连胜衰减
        if victory and a_rating.win_streak >= WIN_STREAK_DECAY_THRESHOLD:
            raw_change = max(1, raw_change // 2)

        # 防止积分变化为 0（极端 ELO 差距时）：胜者至少 +1，败者至少 -1
        if victory and raw_change <= 0:
            raw_change = 1
        if not victory and raw_change >= 0:
            raw_change = -1

        # 对称变化（守方扣等量）
        a_rating.rating = max(0, a_rating_before + raw_change)
        d_rating.rating = max(0, d_rating_before - raw_change)

        # 6) 段位刷新
        a_rating.rank_tier = self.get_rank_tier(a_rating.rating)
        d_rating.rank_tier = self.get_rank_tier(d_rating.rating)

        # 7) 战绩
        a_rating.matches_played += 1
        d_rating.matches_played += 1
        if victory:
            a_rating.wins += 1
            a_rating.win_streak += 1
            d_rating.losses += 1
            d_rating.win_streak = 0
        else:
            a_rating.losses += 1
            a_rating.win_streak = 0
            d_rating.wins += 1
            d_rating.win_streak += 1

        a_rating.best_rating = max(a_rating.best_rating, a_rating.rating)
        d_rating.best_rating = max(d_rating.best_rating, d_rating.rating)

        # 8) 计数器
        a_rating.daily_matches += 1
        d_rating.daily_defense_count += 1
        a_rating.last_match_at = datetime.now()

        # 9) 魂晶发放
        first_win_bonus = False
        if victory:
            soul_attack = SOUL_CRYSTALS_WIN
            if not a_rating.daily_first_win_claimed:
                soul_attack += SOUL_CRYSTALS_FIRST_WIN_BONUS
                a_rating.daily_first_win_claimed = True
                first_win_bonus = True
            a_rating.soul_crystals += soul_attack
            d_rating.soul_crystals += SOUL_CRYSTALS_LOSE
            soul_earned = soul_attack
        else:
            a_rating.soul_crystals += SOUL_CRYSTALS_LOSE
            soul_def = SOUL_CRYSTALS_WIN
            if not d_rating.daily_first_win_claimed:
                soul_def += SOUL_CRYSTALS_FIRST_WIN_BONUS
                d_rating.daily_first_win_claimed = True
            d_rating.soul_crystals += soul_def
            soul_earned = SOUL_CRYSTALS_LOSE

        # 10) 写日志（season 已在 step 0 获取）
        a_rating.season_id = season.id
        d_rating.season_id = season.id

        result_str = "attacker_win" if victory else "defender_win"
        match_log = LadderMatchLog(
            season_id=season.id,
            attacker_id=attacker.id,
            defender_id=defender.id,
            attacker_uid=attacker.uid,
            defender_uid=defender.uid,
            attacker_name=attacker.nickname,
            defender_name=defender.nickname,
            result=result_str,
            attacker_rating_before=a_rating_before,
            attacker_rating_after=a_rating.rating,
            attacker_rating_change=a_rating.rating - a_rating_before,
            defender_rating_before=d_rating_before,
            defender_rating_after=d_rating.rating,
            defender_rating_change=d_rating.rating - d_rating_before,
            defender_notified=False,
        )
        self.session.add(match_log)
        await self.session.flush()

        return {
            "victory": victory,
            "battle_log": battle_log,
            "defender": defender,
            "rating_change": a_rating.rating - a_rating_before,
            "new_rating": a_rating.rating,
            "new_rank": a_rating.rank_tier,
            "soul_earned": soul_earned,
            "first_win_bonus": first_win_bonus,
            "season_id": season.id,
            "match_log_id": match_log.id,
            "win_streak": a_rating.win_streak,
            "daily_matches_used": a_rating.daily_matches,
            "daily_quota": daily_quota,
        }

    # ========== 排行榜 ==========

    async def get_top_rankings(self, season_id: int, limit: int = 50) -> List[Tuple[LadderRating, Player]]:
        """获取本赛季 TOP N 排行榜"""
        stmt = (
            select(LadderRating, Player)
            .join(Player, Player.id == LadderRating.player_id)
            .where(LadderRating.season_id == season_id, LadderRating.matches_played > 0)
            .order_by(LadderRating.rating.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [(r.LadderRating, r.Player) for r in rows]

    async def get_player_rank_in_season(self, player_id: str, season_id: int) -> Optional[int]:
        """获取玩家在本赛季的排名（1-based），返回 None 表示无排名"""
        # 玩家必须在本赛季有战绩才计入排行
        stmt = select(LadderRating).where(
            LadderRating.player_id == player_id,
            LadderRating.season_id == season_id,
            LadderRating.matches_played > 0,
        )
        rating = (await self.session.execute(stmt)).scalar_one_or_none()
        if not rating:
            return None

        # 计算本赛季比自己积分高的玩家数量
        count_stmt = select(sql_func.count(LadderRating.player_id)).where(
            LadderRating.season_id == season_id,
            LadderRating.matches_played > 0,
            LadderRating.rating > rating.rating,
        )
        count = (await self.session.execute(count_stmt)).scalar_one()
        return count + 1

    # ========== 战绩历史 ==========

    async def get_recent_matches(self, player_id: str, limit: int = 20) -> List[LadderMatchLog]:
        """获取玩家最近 N 场对战记录"""
        stmt = (
            select(LadderMatchLog)
            .where(
                or_(
                    LadderMatchLog.attacker_id == player_id,
                    LadderMatchLog.defender_id == player_id,
                )
            )
            .order_by(LadderMatchLog.timestamp.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    # ========== 守方推送钩子 ==========

    async def get_pending_notifications(
        self, player_id: str, limit: int = 5
    ) -> List[LadderMatchLog]:
        """获取守方未推送的对战记录"""
        stmt = (
            select(LadderMatchLog)
            .where(
                LadderMatchLog.defender_id == player_id,
                LadderMatchLog.defender_notified.is_(False),
            )
            .order_by(LadderMatchLog.timestamp.desc())
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return list(rows)

    async def mark_notifications_seen(self, player_id: str) -> int:
        """将守方所有未读通知标记为已读，返回标记数量"""
        stmt = select(LadderMatchLog).where(
            LadderMatchLog.defender_id == player_id,
            LadderMatchLog.defender_notified.is_(False),
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        for log in rows:
            log.defender_notified = True
        return len(rows)

    # ========== 赛季管理 ==========

    async def get_or_create_active_season(self) -> LadderSeason:
        """获取当前激活赛季；若已结束则结算并新建"""
        stmt = select(LadderSeason).order_by(LadderSeason.id.desc()).limit(1)
        latest = (await self.session.execute(stmt)).scalar_one_or_none()
        now = datetime.now()

        if latest and latest.status == "active" and latest.end_at > now:
            return latest

        # 需要结算或新建
        if latest and latest.status == "active":
            try:
                await self.settle_season(latest)
            except (SQLAlchemyError, ValueError, KeyError) as e:  # pragma: no cover
                logger.error(f"结算赛季 {latest.season_number} 失败: {e}", exc_info=True)
                # 失败时仍需创建新赛季，避免无限尝试结算同一个失败赛季
                latest.status = "ended"
                latest.rewards_distributed = True

        # 新赛季：当月 1 日 0:00 ~ 当月最后一天 23:59:59
        new_number = (latest.season_number + 1) if latest else 1
        start = datetime(now.year, now.month, 1, 0, 0, 0)
        if now.month == 12:
            next_month = datetime(now.year + 1, 1, 1)
        else:
            next_month = datetime(now.year, now.month + 1, 1)
        end = next_month - timedelta(seconds=1)

        new_season = LadderSeason(
            season_number=new_number,
            start_at=start,
            end_at=end,
            status="active",
            rewards_distributed=False,
        )
        self.session.add(new_season)
        await self.session.flush()
        logger.info(f"✅ 创建新赛季 #{new_number} {start:%Y-%m-%d}~{end:%Y-%m-%d}")
        return new_season

    async def settle_season(self, season: LadderSeason) -> dict:
        """结算赛季：发放奖励 + 软重置积分"""
        from .rewards import distribute_season_rewards

        if season.rewards_distributed:
            return {"already_distributed": True}

        season.status = "settling"
        await self.session.flush()

        # 发放奖励
        result = await distribute_season_rewards(self.session, season)

        # 软重置所有玩家积分
        all_ratings = (await self.session.execute(select(LadderRating))).scalars().all()
        reset_count = 0
        for r in all_ratings:
            if r.rating > SOFT_RESET_THRESHOLD:
                r.rating = int(SOFT_RESET_THRESHOLD + (r.rating - SOFT_RESET_THRESHOLD) * SOFT_RESET_RATIO)
                r.rank_tier = self.get_rank_tier(r.rating)
                reset_count += 1
            # 新赛季统计清零（保留 best_rating）
            r.matches_played = 0
            r.wins = 0
            r.losses = 0
            r.draws = 0
            r.win_streak = 0

        season.status = "ended"
        season.rewards_distributed = True
        await self.session.flush()
        logger.info(f"✅ 赛季 #{season.season_number} 结算完成: 奖励 {result.get('reward_count', 0)} 人, 软重置 {reset_count} 人")
        return {
            "rewarded": result.get("reward_count", 0),
            "soft_reset": reset_count,
        }
