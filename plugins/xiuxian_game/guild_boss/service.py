"""
公会镇诡业务服务

复用世界BOSS的理智战斗结算路径（EnhancedBattleEngine + 属性预计算），
血量/结算/周次数等公会侧逻辑在本服务内实现。
设计文档：llmdoc/design/specs/2026-07-08-guild-boss-design.md
"""
import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.exc import StaleDataError

from ..infrastructure.locking import lock_rows
from ..models.player import Player
from ..models.guild import Guild, GuildMember, GuildPosition
from ..models.guild_boss import GuildBossInstance, GuildBossDamage
from ..world_boss.service import WorldBossService
from .config import (
    SUMMON_COST_BASE,
    SUMMON_COST_PER_LEVEL,
    DAILY_SUMMON_LIMIT,
    DURATION_HOURS,
    ATTACKS_PER_INSTANCE,
    ATTACK_COOLDOWN_SECONDS,
    HP_FACTOR,
    HP_ACTIVE_DAYS,
    GUILD_EXP_BASE,
    POINTS_PARTICIPANT,
    POINTS_FULL_ATTENDANCE,
    POINTS_TOP3,
    BOSS_POOL,
    BLOOD_TIERS,
    BLOOD_BOSS_POOL,
    BLOOD_TITLE,
    BLOOD_RELIC_ITEM_ID,
    BLOOD_RELIC_TOP_N,
    SUBDUE_LINES,
    EXPIRE_LINES,
    ferocity_multiplier,
)


class GuildBossService:
    """公会镇诡核心服务"""

    def __init__(self, session: AsyncSession):
        self._session = session

    async def _lock_current_rows(self, model, ids):
        transaction = self._session.sync_session.get_transaction()
        state = self._session.info.get("guild_boss_locked_rows")
        if state is None or state[0] is not transaction:
            state = (transaction, {})
        held = state[1]
        keys = sorted(set(ids))
        missing = [key for key in keys if (model, key) not in held]
        if missing:
            rows = await lock_rows(self._session, model, missing)
            for row in rows:
                held[model, row.id] = row
        # 同一事务重入时保留已持锁对象的待写字段；提交或回滚后重新获取当前读。
        self._session.info["guild_boss_locked_rows"] = (
            self._session.sync_session.get_transaction(), held,
        )
        return [held[model, key] for key in keys if (model, key) in held]

    async def _lock_current(self, model, key):
        rows = await self._lock_current_rows(model, [key])
        return rows[0] if rows else None

    # ==================== 查询 ====================

    async def get_membership(self, player: Player, *, for_update: bool = False) -> Tuple[Optional[Guild], Optional[GuildPosition]]:
        """获取玩家所在公会与职位"""
        if not player.guild_id:
            return None, None
        with self._session.no_autoflush:
            guild = (await self._lock_current(Guild, player.guild_id) if for_update
                     else await self._session.get(Guild, player.guild_id))
        if not guild:
            return None, None
        stmt = select(GuildMember).where(
            GuildMember.guild_id == guild.id,
            GuildMember.player_id == player.id,
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        with self._session.no_autoflush:
            member = (await self._session.execute(stmt)).scalars().first()
        return guild, (member.position if member else None)

    async def get_active_instance(self, guild_id: int, *, for_update: bool = False) -> Optional[GuildBossInstance]:
        if not for_update:
            with self._session.no_autoflush:
                return (await self._session.execute(
                    select(GuildBossInstance)
                    .where(GuildBossInstance.guild_id == guild_id, GuildBossInstance.status == "active")
                    .order_by(desc(GuildBossInstance.id)).limit(1)
                )).scalars().first()
        await self._lock_current(Guild, guild_id)
        pending = [
            row for row in self._session.new.union(self._session.dirty)
            if isinstance(row, GuildBossInstance) and row.guild_id == guild_id
        ]
        if pending:
            await self._session.flush(pending)
        stmt = (
            select(GuildBossInstance.id)
            .where(
                GuildBossInstance.guild_id == guild_id,
                GuildBossInstance.status == "active",
            )
            .order_by(desc(GuildBossInstance.id))
            .limit(1)
            .with_for_update()
        )
        with self._session.no_autoflush:
            key = (await self._session.execute(stmt)).scalars().first()
        return await self._lock_current(GuildBossInstance, key) if key is not None else None

    async def get_latest_instance(self, guild_id: int) -> Optional[GuildBossInstance]:
        """最近一场（不限状态），供战报回看"""
        stmt = (
            select(GuildBossInstance)
            .where(GuildBossInstance.guild_id == guild_id)
            .order_by(desc(GuildBossInstance.id))
            .limit(1)
        )
        with self._session.no_autoflush:
            return (await self._session.execute(stmt)).scalars().first()

    async def get_damage_rows(self, instance_id: int, *, for_update: bool = False) -> List[GuildBossDamage]:
        """按伤害降序返回本场全部出力记录"""
        # 当前读绕过 RR 快照；仅落盘伤害，查询页面不能提前写入尚未加锁的玩家元数据。
        pending = [row for row in self._session.new.union(self._session.dirty) if isinstance(row, GuildBossDamage)]
        if for_update and pending:
            await self._session.flush(pending)
        stmt = (
            select(GuildBossDamage)
            .where(
                GuildBossDamage.instance_id == instance_id,
                GuildBossDamage.attacks_used > 0,
            )
            .order_by(desc(GuildBossDamage.total_damage))
        )
        if for_update:
            stmt = stmt.with_for_update().execution_options(populate_existing=True)
        with self._session.no_autoflush:
            return list((await self._session.execute(stmt)).scalars().all())

    async def get_member_players(self, guild_id: int) -> List[Player]:
        stmt = select(Player).join(GuildMember, GuildMember.player_id == Player.id).where(
            GuildMember.guild_id == guild_id,
        )
        with self._session.no_autoflush:
            return list((await self._session.execute(stmt)).scalars().all())

    async def settle_if_expired(self, guild: Guild, instance: Optional[GuildBossInstance]) -> Optional[Dict]:
        """懒结算：场次已超时则结算并返回结算摘要，否则返回 None"""
        if not instance or instance.status != "active" or instance.settled or datetime.now() < instance.expires_at:
            return None
        guild = await self._lock_current(Guild, guild.id)
        instance = await self._lock_current(GuildBossInstance, instance.id)
        if not instance or instance.status != "active" or instance.settled:
            return None
        if datetime.now() < instance.expires_at:
            return None
        players = await self._lock_participants(instance.id)
        return await self._settle_locked(instance, guild, killed=False, players=players)

    # ==================== 开坛 ====================

    @staticmethod
    def summon_cost(ferocity: int) -> int:
        return SUMMON_COST_BASE + ferocity * SUMMON_COST_PER_LEVEL

    @staticmethod
    def _day_key(now: datetime) -> str:
        return now.strftime("%Y-%m-%d")

    def refresh_day_counter(self, guild: Guild):
        """每日零点重置开坛计数（按日期键懒重置，复用 boss_week_* 字段）"""
        dk = self._day_key(datetime.now())
        if guild.boss_week_key != dk:
            guild.boss_week_key = dk
            guild.boss_week_summons = 0
            self._session.add(guild)

    @staticmethod
    def _pick_boss(ferocity: int, blood_tier: str = "") -> Dict:
        if blood_tier and BLOOD_TIERS.get(blood_tier, {}).get("exclusive_pool"):
            return random.choice(BLOOD_BOSS_POOL)
        pool = [b for b in BOSS_POOL if b["min_ferocity"] <= ferocity]
        return random.choice(pool)

    async def donate_resentment(self, guild: Guild, player: Player, amount: int) -> Tuple[bool, str]:
        """献怨：成员将个人怨念注入公会怨念池（不可取回）"""
        await self._lock_current(Guild, guild.id)
        await self._lock_current(Player, player.id)
        if amount <= 0:
            return False, "献怨数量需要是正数"
        if player.resentment < amount:
            return False, f"你的怨念不足：想献 {amount:,}，身上只有 {player.resentment:,}"
        player.resentment -= amount
        guild.resentment_pool += amount
        self._session.add(player)
        self._session.add(guild)
        return True, ""

    async def summon(self, guild: Guild, player: Player, blood_tier: str = "") -> Tuple[bool, Union[str, Dict]]:
        """开坛引诡。blood_tier 非空时为血祭开坛（消耗公会怨念池）。返回 (ok, 错误文案或结果数据)"""
        active = await self.get_active_instance(guild.id, for_update=True)
        if active:
            return False, "阵眼已被占据——上一只诡异还没走。先用【镇诡】出力。"

        self.refresh_day_counter(guild)
        if guild.boss_week_summons >= DAILY_SUMMON_LIMIT:
            return False, f"今日开坛次数已用完（{DAILY_SUMMON_LIMIT}/{DAILY_SUMMON_LIMIT}），明日再来"

        if blood_tier:
            tier_cfg = BLOOD_TIERS[blood_tier]
            cost = tier_cfg["cost"]
            if guild.resentment_pool < cost:
                return False, (
                    f"公会怨念池不足：血祭·{blood_tier}需要 {cost:,}，池中仅 {guild.resentment_pool:,}\n"
                    "用【献怨 数量】把你多余的怨念注入坛中"
                )
        else:
            cost = self.summon_cost(guild.boss_level)
            if guild.treasury < cost:
                return False, (
                    f"公会资金不足：开坛需要 {cost:,}，库中仅 {guild.treasury:,}\n"
                    "用【捐献金币】充实资金库"
                )

        # 全会有效攻击力快照（防"开坛后拉人/踢人"操纵血量）
        # 只统计近 HP_ACTIVE_DAYS 天活跃的成员：躺尸号不撑血量，但仍可参战
        members = await self.get_member_players(guild.id)
        cutoff = datetime.now() - timedelta(days=HP_ACTIVE_DAYS)
        active_members = [
            p for p in members
            if p.last_active_at and p.last_active_at >= cutoff
        ]
        # 参战意愿加权：进一步只算近 HP_ACTIVE_DAYS 天在本会镇诡中出过手的人，
        # 活跃但从不参战的成员不再撑血量。按整周口径而非仅上一场，
        # 防止"故意派一个弱号送走一场"来压低下一场血量。无出手记录（新公会）回退全员活跃。
        fighter_stmt = (
            select(GuildBossDamage.player_id)
            .join(GuildBossInstance, GuildBossInstance.id == GuildBossDamage.instance_id)
            .where(
                GuildBossInstance.guild_id == guild.id,
                GuildBossInstance.summoned_at >= cutoff,
                GuildBossDamage.attacks_used > 0,
            )
        )
        with self._session.no_autoflush:
            fighters = set((await self._session.execute(fighter_stmt)).scalars().all())
        hp_members = [p for p in active_members if p.id in fighters] or active_members
        total_attack = 0
        with self._session.no_autoflush:
            for p in hp_members:
                attrs = await p.get_effective_attributes(self._session)
                total_attack += max(1, int(attrs.get("attack", p.attack)))

        d_mult = ferocity_multiplier(guild.boss_level)
        hp_mult = BLOOD_TIERS[blood_tier]["hp_mult"] if blood_tier else 1.0
        hp_max = max(1000, int(total_attack * HP_FACTOR * d_mult * hp_mult))
        boss = self._pick_boss(guild.boss_level, blood_tier)

        now = datetime.now()
        instance = GuildBossInstance(
            guild_id=guild.id,
            boss_name=boss["name"],
            boss_title=boss["title"],
            boss_level=guild.boss_level,
            blood_tier=blood_tier,
            hp_max=hp_max,
            hp_left=hp_max,
            atk_snapshot=total_attack,
            summoned_by=player.id,
            summoned_at=now,
            expires_at=now + timedelta(hours=DURATION_HOURS),
        )
        if blood_tier:
            guild.resentment_pool -= cost
        else:
            guild.treasury -= cost
        guild.boss_week_summons += 1
        self._session.add(guild)
        self._session.add(instance)

        return True, {"instance": instance, "boss": boss, "cost": cost, "member_count": len(members)}

    # ==================== 讨伐 ====================

    async def _get_or_create_damage(self, instance_id: int, player_id: str) -> GuildBossDamage:
        stmt = select(GuildBossDamage).where(
            GuildBossDamage.instance_id == instance_id,
            GuildBossDamage.player_id == player_id,
        )
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
        row = (await self._session.execute(stmt)).scalars().first()
        if not row:
            row = GuildBossDamage(instance_id=instance_id, player_id=player_id)
            self._session.add(row)
            await self._session.flush([row])
        return row

    def _boss_stats(self, instance: GuildBossInstance, player: Player) -> Dict:
        """诡异战斗属性。

        锚定参战者自身（会内强弱成员各自公平），沿用世界BOSS的段位倍率，
        防御/理智侵蚀随凶戾度放大；attack 专用于削减玩家理智（同世界BOSS机制）。
        """
        tier = WorldBossService.get_reincarnation_tier(player.reincarnation_level)
        tier_idx = min(tier, len(WorldBossService.TIER_STATS_MULTIPLIERS) - 1)
        def_mult, agi_mult, atk_mult = WorldBossService.TIER_STATS_MULTIPLIERS[tier_idx]
        d_mult = ferocity_multiplier(instance.boss_level)
        return {
            "hp": 9_999_999_999,  # 引擎内不判Boss死亡，血量由本服务扣减并钳制溢出
            "defense": 10 + int(player.defense * def_mult * d_mult),
            "agility": 10 + int(player.agility * agi_mult),
            "attack": int((player.max_mp if player.max_mp > 0 else 1000) * atk_mult * d_mult),
            "level": "???",
        }

    async def attack(self, guild: Guild, instance: GuildBossInstance, player: Player) -> Tuple[bool, Union[str, Dict]]:
        """出手一次。返回 (ok, 错误文案或战斗结果数据)"""
        await self._lock_current(Guild, guild.id)
        instance = await self._lock_current(GuildBossInstance, instance.id)
        if not instance or instance.status != "active" or instance.settled:
            return False, "阵中无诡。会长或副会长可用【开坛引诡】召唤\n（用【公会Boss】查看开坛条件）"
        if datetime.now() >= instance.expires_at:
            players = await self._lock_participants(instance.id)
            settlement = await self._settle_locked(instance, guild, killed=False, players=players)
            return True, {"expired": True, "settlement": settlement}
        # 引擎可修改玩家字段；获取玩家锁之前禁止自动落盘，也不能刷新攻击者。
        with self._session.no_autoflush:
            actor_version = player.version_id
            row = await self._get_or_create_damage(instance.id, player.id)

            if row.attacks_used >= ATTACKS_PER_INSTANCE:
                return False, f"你这一场的 {ATTACKS_PER_INSTANCE} 次出手已经用完，等同门把它送走吧"

            now_ts = int(time.time())
            if now_ts - row.last_attack_ts < ATTACK_COOLDOWN_SECONDS:
                return False, "喘口气，阵纹还没稳住"

            if player.hp <= 0:
                return False, "你已重伤倒地，无法参战。先恢复生命值"
            if player.mp <= 0:
                return False, "你的理智已经见底——它正等着你这样的人走进阵里。先恢复理智"

            boss_stats = self._boss_stats(instance, player)
            ws = WorldBossService(
                session=self._session,
                cycle_repo=None,
                damage_repo=None,
                player_repo=None,
                item_repo=None,
            )
            seed = f"GuildBoss:{instance.id}:{player.id}:{int(time.time() * 1000)}"
            _victory, battle_log, sanity_damage, damage_dealt = await ws._execute_sanity_battle_v2(
                player,
                boss_stats,
                f"{instance.boss_name}·{instance.boss_title}",
                weakness="",
                seed=seed,
                max_rounds=30,
            )
            killed = damage_dealt >= instance.hp_left
            players = await self._lock_attack_players(instance.id, player, actor_version, killed)

        original_mp = player.mp
        player.mp = max(0, player.mp - sanity_damage)
        if player.mp <= 0:
            player.hp = 0

        # 溢出钳制：只按实际扣血计伤害，保证伤害榜合计 = 总血量
        applied = min(damage_dealt, instance.hp_left)
        instance.hp_left -= applied
        row.total_damage += applied
        row.attacks_used += 1
        row.last_attack_ts = now_ts
        self._session.add(player)
        self._session.add(row)
        self._session.add(instance)

        killed = instance.hp_left <= 0
        settlement = None
        if killed:
            instance.final_blow_by = player.id
            settlement = await self._settle_locked(instance, guild, killed=True, players=players)

        return True, {
            "battle_log": battle_log,
            "applied": applied,
            "raw_damage": damage_dealt,
            "sanity_damage": sanity_damage,
            "original_mp": original_mp,
            "row": row,
            "killed": killed,
            "settlement": settlement,
        }

    # ==================== 结算 ====================

    async def _participant_ids(self, instance_id: int) -> set:
        # 公会根锁保护参与者集合；当前读须覆盖等待根锁期间已提交的出手。
        stmt = select(GuildBossDamage.player_id).where(
            GuildBossDamage.instance_id == instance_id,
            GuildBossDamage.attacks_used > 0,
        ).with_for_update()
        with self._session.no_autoflush:
            ids = set((await self._session.execute(stmt)).scalars().all())
        ids.update(
            row.player_id for row in self._session.new.union(self._session.dirty)
            if isinstance(row, GuildBossDamage) and row.instance_id == instance_id and row.attacks_used > 0
        )
        return ids

    async def _lock_attack_players(
        self, instance_id: int, actor: Player, actor_version: int, killed: bool,
    ) -> Dict[str, Player]:
        ids = await self._participant_ids(instance_id) if killed else set()
        ids.add(actor.id)
        versions = dict((await self._session.execute(
            select(Player.id, Player.version_id)
            .where(Player.id.in_(sorted(ids)))
            .order_by(Player.id)
            .with_for_update()
        )).all())
        if versions.get(actor.id) != actor_version:
            raise StaleDataError("镇诡期间玩家状态已变更，请重新出手")
        others = await self._lock_current_rows(Player, ids - {actor.id})
        state = self._session.info.get("guild_boss_locked_rows")
        transaction = self._session.sync_session.get_transaction()
        held = state[1] if state is not None and state[0] is transaction else {}
        held[Player, actor.id] = actor
        self._session.info["guild_boss_locked_rows"] = (transaction, held)
        return {actor.id: actor, **{player.id: player for player in others}}

    async def _lock_participants(self, instance_id: int) -> Dict[str, Player]:
        ids = await self._participant_ids(instance_id)
        ids.update(player.id for player in self._session.dirty if isinstance(player, Player))
        players = await self._lock_current_rows(Player, ids)
        return {player.id: player for player in players}

    async def _settle(self, instance: GuildBossInstance, guild: Guild, killed: bool) -> Optional[Dict]:
        """独立结算入口：获取当前状态与全部奖励接收者的锁。"""
        await self._lock_current(Guild, guild.id)
        instance = await self._lock_current(GuildBossInstance, instance.id)
        if not instance or instance.status != "active" or instance.settled:
            return None
        if killed and instance.hp_left > 0:
            return None
        if not killed and datetime.now() < instance.expires_at:
            return None
        players = await self._lock_participants(instance.id)
        return await self._settle_locked(instance, guild, killed, players)

    async def _settle_locked(
        self, instance: GuildBossInstance, guild: Guild, killed: bool, players: Dict[str, Player],
    ) -> Optional[Dict]:
        """调用方已锁定公会、场次和参与者；不得刷新本次出手的未提交状态。"""
        if instance.status != "active" or instance.settled:
            return None
        if killed and instance.hp_left > 0:
            return None
        if not killed and datetime.now() < instance.expires_at:
            return None
        instance.status = "subdued" if killed else "expired"
        instance.settled = 1

        damage_done = instance.hp_max - instance.hp_left
        ratio = 1.0 if killed else (damage_done / instance.hp_max if instance.hp_max > 0 else 0.0)

        tier_cfg = BLOOD_TIERS.get(instance.blood_tier, {})
        reward_mult = tier_cfg.get("reward_mult", 1.0)
        # 邪坛专属奖励只在镇压成功时发放
        grant_exclusive = killed and tier_cfg.get("exclusive_pool", False)

        rows = await self.get_damage_rows(instance.id, for_update=True)
        participants = []
        relic_winners: List[str] = []
        title_new_owners: List[str] = []
        for idx, row in enumerate(rows):
            p = players.get(row.player_id)
            if not p:
                continue  # 玩家已注销：伤害留榜，奖励跳过
            pts = POINTS_PARTICIPANT
            if row.attacks_used >= ATTACKS_PER_INSTANCE:
                pts += POINTS_FULL_ATTENDANCE
            if idx < len(POINTS_TOP3):
                pts += POINTS_TOP3[idx]
            pts = int(pts * reward_mult * ratio)
            if pts > 0:
                p.gold2 += pts
                self._session.add(p)
            if grant_exclusive:
                if idx < BLOOD_RELIC_TOP_N:
                    from ..models.inventory import ItemInstance
                    try:
                        await ItemInstance.add_item(self._session, p.id, BLOOD_RELIC_ITEM_ID, 1)
                        relic_winners.append(p.nickname)
                    except ValueError:
                        pass  # 背包满：该玩家遗物发放失败，不中断结算
                if self._grant_blood_title(p):
                    title_new_owners.append(p.nickname)
            participants.append({
                "player_id": p.id,
                "nickname": p.nickname,
                "damage": row.total_damage,
                "attacks": row.attacks_used,
                "points": pts,
            })

        # 公会经验：与 GuildEconomyService.add_guild_experience 同口径（吃经验神龛倍率）
        base_exp = int(GUILD_EXP_BASE * ferocity_multiplier(instance.boss_level) * reward_mult)
        if not killed:
            base_exp = int(base_exp * ratio / 2)
        actual_exp = 0
        if base_exp > 0:
            from ..guild.guild_building_service import GuildBuildingService
            from ..infrastructure.repositories.guild_repository import GuildRepository
            from ..infrastructure.repositories.guild_building_repository import GuildBuildingRepository

            building_service = GuildBuildingService(
                guild_repo=GuildRepository(self._session),
                building_repo=GuildBuildingRepository(self._session),
                item_repo=None,
            )
            bonuses = await building_service.get_guild_bonuses(guild.id)
            actual_exp = int(base_exp * bonuses.get("exp_multiplier", 1.0))
            guild.exp += actual_exp

        old_ferocity = guild.boss_level
        if killed:
            guild.boss_level += 1
        else:
            guild.boss_level = max(1, guild.boss_level - 1)
        self._session.add(guild)
        self._session.add(instance)

        return {
            "killed": killed,
            "ratio": ratio,
            "damage_done": damage_done,
            "participants": participants,
            "guild_exp": actual_exp,
            "old_ferocity": old_ferocity,
            "new_ferocity": guild.boss_level,
            "final_blow_by": instance.final_blow_by,
            "blood_tier": instance.blood_tier,
            "relic_winners": relic_winners,
            "title_new_owners": title_new_owners,
            "flavour": random.choice(SUBDUE_LINES if killed else EXPIRE_LINES),
        }

    @staticmethod
    def _grant_blood_title(player: Player) -> bool:
        """授予邪坛限定称号（写入 extra_attrs 称号列表）。返回是否为新获得"""
        from ..event.knocker_event import KnockerEventService

        pdata = KnockerEventService._get_player_data(player)
        owned = pdata.get("owned_titles", [])
        if BLOOD_TITLE in owned:
            return False
        owned.append(BLOOD_TITLE)
        pdata["owned_titles"] = owned
        KnockerEventService._set_player_data(player, pdata)
        return True
