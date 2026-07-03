from __future__ import annotations

"""世界BOSS系统核心服务 (DI架构版本)

改造说明:
- 混合模式设计：5个纯计算方法保持@staticmethod + 7个数据访问方法转为实例方法
- 通过构造函数注入4个Repository依赖
- 移除所有内部commit()调用（7处），由外层safe_session()统一管理事务
- 保持业务逻辑完全一致
- 集成事件系统：发布WorldBossDamageEvent

功能：
1. 懒加载周期刷新（周三/六 20:00）
2. BOSS攻击与理智削减计算
3. 排行榜与奖励结算
4. 宝箱系统与奖励分发
"""

import random
import time
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from sqlalchemy import select, and_, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.world_boss import WorldBossCycle, WorldBossDamage
from ..models.inventory import ItemInstance
from ..battle.integration_helper import BattleIntegrationHelper
from ..config import config
from ..infrastructure.repositories.world_boss_cycle_repository import WorldBossCycleRepository
from ..infrastructure.repositories.world_boss_damage_repository import WorldBossDamageRepository
from ..infrastructure.repositories.player_repository import PlayerRepository
from ..infrastructure.repositories.item_repository import ItemRepository
# 事件系统
from ..domain.events import event_bus, WorldBossDamageEvent
from ..server_config import get_servers_config
from ..utils_markdown import cmd


class WorldBossService:
    """世界BOSS系统核心服务类 (DI架构版本)"""

    # 克苏鲁神话BOSS配置
    BOSS_POOL = [
        {
            "name": "巴虺",
            "title": "深渊之蛇·无尽吞噬者",
            "description": "盘踞于深渊裂隙中的古老巨蛇，其鳞片如黑曜石般闪烁着不祥的光芒。传说它能吞噬整个世界的光明，将一切拖入永恒的黑暗。"
        },
        {
            "name": "黑太岁",
            "title": "腐朽之王·时间侵蚀者",
            "description": "从时间深处爬出的腐朽存在，身躯由无数腐烂的肉块拼接而成。它的存在本身就是对现实的亵渎，每一次呼吸都在腐蚀着周围的时空。"
        },
        {
            "name": "夜魇之母",
            "title": "梦境支配者·恐惧编织者",
            "description": "栖息在梦境与现实交界处的恐怖存在，拥有无数触手和眼球。它以恐惧为食，将噩梦编织成现实的枷锁。"
        },
        {
            "name": "深海咏者",
            "title": "深渊传道者·疯狂低语者",
            "description": "来自深海最深处的古老祭司，身躯半鱼半人，口中不断吟唱着令人疯狂的古老咒文。其歌声能够扭曲现实，将理智拖入深渊。"
        },
        {
            "name": "虚空行者",
            "title": "次元撕裂者·现实扭曲者",
            "description": "游荡在维度裂缝中的无形存在，只有在攻击时才会显现出扭曲的轮廓。它的每一次移动都在撕裂空间，留下无法愈合的虚空伤痕。"
        },
        {
            "name": "血肉教主",
            "title": "生命亵渎者·血肉重塑者",
            "description": "由无数生灵的血肉融合而成的邪恶存在，身躯不断变化着形态。它能够重塑生命的本质，将一切生物扭曲成自己的奴仆。"
        }
    ]

    # 每日攻击次数限制
    DAILY_ATTACK_LIMIT = 3
    ATTACK_COOLDOWN = 1  # 秒

    # 段位名称（每两转一段，0转单独一段）
    TIER_NAMES = ["凡尘段", "轮回段", "超脱段", "传说段", "永恒段", "无上段"]

    # C: 各段位BOSS属性倍率 (防御倍率, 敏捷倍率, 攻击=player.max_mp的百分比)
    TIER_STATS_MULTIPLIERS = [
        (0.30, 0.25, 0.07),  # tier 0: 凡尘(0转)
        (0.50, 0.40, 0.09),  # tier 1: 轮回(1-2转)
        (0.70, 0.60, 0.11),  # tier 2: 超脱(3-4转)
        (1.00, 0.80, 0.13),  # tier 3: 传说(5-6转)
        (1.30, 1.10, 0.16),  # tier 4: 永恒(7-8转)
        (1.60, 1.40, 0.19),  # tier 5+: 无上(9+转)
    ]

    # E: Boss弱点类型（由cycle_key哈希确定，无需DB字段）
    WEAKNESS_TYPES = ["暴击", "穿透", "连击"]

    @staticmethod
    def get_reincarnation_tier(reincarnation_level: int) -> int:
        """获取转数对应的段位编号（0=凡尘/0转，1=轮回/1-2转，2=超脱/3-4转，...）"""
        if reincarnation_level <= 0:
            return 0
        tier = (reincarnation_level - 1) // 2 + 1
        max_tier = len(WorldBossService.TIER_NAMES) - 1
        return min(tier, max_tier)

    @staticmethod
    def get_tier_label(tier: int) -> str:
        """获取段位展示名称，如'轮回段（1-2转）'"""
        names = WorldBossService.TIER_NAMES
        name = names[tier] if tier < len(names) else names[-1]
        if tier == 0:
            return f"{name}（0转）"
        max_tier = len(names) - 1
        if tier >= max_tier:
            low = (max_tier - 1) * 2 + 1
            return f"{name}（{low}+转）"
        low = (tier - 1) * 2 + 1
        high = tier * 2
        return f"{name}（{low}-{high}转）"

    # E: Boss弱点图标映射（便于内联使用）
    WEAKNESS_ICONS = {"暴击": "💥", "穿透": "🔥", "连击": "⚡"}

    @staticmethod
    def get_boss_weakness(cycle: "WorldBossCycle") -> str:
        """基于cycle_key哈希确定本期弱点（无需DB字段，可重现）"""
        idx = abs(hash(cycle.cycle_key)) % len(WorldBossService.WEAKNESS_TYPES)
        return WorldBossService.WEAKNESS_TYPES[idx]

    # 奖励区间配置（按累计伤害排名）
    REWARD_TIERS = [
        {"rank_range": (1, 1), "chest": "深渊霸主宝箱", "description": "🏆 第1名"},
        {"rank_range": (2, 3), "chest": "深渊王者宝箱", "description": "🥈 第2-3名"},
        {"rank_range": (4, 10), "chest": "深渊勇士宝箱", "description": "🥉 第4-10名"},
        {"rank_range": (11, 30), "chest": "深渊探索者宝箱", "description": "🎖️ 第11-30名"},
        {"rank_range": (31, 100), "chest": "深渊挑战者宝箱", "description": "🏅 第31-100名"},
        {"rank_range": (101, 999999), "chest": "深渊参与者宝箱", "description": "🎁 参与奖"}
    ]

    def __init__(
        self,
        session: AsyncSession,
        cycle_repo: WorldBossCycleRepository,
        damage_repo: WorldBossDamageRepository,
        player_repo: PlayerRepository,
        item_repo: ItemRepository
    ):
        """
        初始化WorldBossService

        Args:
            session: 数据库会话
            cycle_repo: 世界BOSS周期仓储
            damage_repo: 世界BOSS伤害记录仓储
            player_repo: 玩家仓储
            item_repo: 物品仓储
        """
        self._session = session
        self._cycle_repo = cycle_repo
        self._damage_repo = damage_repo
        self._player_repo = player_repo
        self._item_repo = item_repo

    @staticmethod
    def _get_next_refresh_time() -> datetime:
        """计算下次刷新时间（周三/六 20:00）"""
        now = datetime.now()

        # 找到下一个周三或周六的20:00
        days_ahead = 0
        while True:
            target_date = now + timedelta(days=days_ahead)
            weekday = target_date.weekday()  # 0=周一, 2=周三, 5=周六

            if weekday in [2, 5]:  # 周三或周六
                target_time = target_date.replace(hour=20, minute=0, second=0, microsecond=0)
                if target_time > now:
                    return target_time

            days_ahead += 1
            if days_ahead > 7:  # 防止无限循环
                break

        # 兜底：7天后
        return now + timedelta(days=7)

    @staticmethod
    def _generate_cycle_key(refresh_time: datetime) -> str:
        """生成周期键"""
        year = refresh_time.year
        week = refresh_time.isocalendar()[1]
        day_name = "WED" if refresh_time.weekday() == 2 else "SAT"
        return f"{year}W{week:02d}_{day_name}_20"

    async def check_and_refresh_cycle(self) -> Tuple[WorldBossCycle, Optional[str]]:
        """检查并刷新周期（懒加载触发）

        Returns:
            (当前周期, 刷新提示信息)

        改造说明:
            - 原Line 84内部commit()已移除，由调用方控制事务
            - 使用self._cycle_repo替代session.execute(select(WorldBossCycle))
        """
        now = datetime.now()

        # 获取最新的周期
        current_cycle = await self._cycle_repo.get_current_cycle()

        # 如果没有周期或者已到刷新时间，创建新周期
        if not current_cycle or now >= current_cycle.next_refresh_at:
            # 结算旧周期（如果存在且未结算）
            settlement_tip = None
            if current_cycle and not current_cycle.settled:
                settlement_tip = await self._settle_cycle(current_cycle)

            # 创建新周期
            next_refresh = WorldBossService._get_next_refresh_time()
            cycle_key = WorldBossService._generate_cycle_key(next_refresh)

            # 随机选择BOSS
            boss_data = random.choice(WorldBossService.BOSS_POOL)

            new_cycle = await self._cycle_repo.create_cycle(
                cycle_key=cycle_key,
                boss_name=boss_data["name"],
                boss_title=boss_data["title"],
                next_refresh_at=next_refresh
            )

            tip = f"🌟 新的世界BOSS已降临！{boss_data['name']} 等待着勇士们的挑战！"
            if settlement_tip:
                tip = settlement_tip + "\n\n" + tip

            return new_cycle, tip

        return current_cycle, None

    async def _settle_cycle(self, cycle: WorldBossCycle) -> str:
        """结算周期奖励（各区服独立，区内按段位分组、各段独立排名）"""
        from collections import defaultdict

        chest_item_id_map = {
            "深渊霸主宝箱": "abyss_overlord_chest",
            "深渊王者宝箱": "abyss_king_chest",
            "深渊勇士宝箱": "abyss_warrior_chest",
            "深渊探索者宝箱": "abyss_explorer_chest",
            "深渊挑战者宝箱": "abyss_challenger_chest",
            "深渊参与者宝箱": "abyss_participant_chest"
        }

        reward_count = 0
        for server_id in get_servers_config():
            results = await self._damage_repo.get_ranking(cycle.id, limit=999999, server_id=server_id)
            if not results:
                continue

            # 按段位分组
            tier_groups: dict = defaultdict(list)
            for damage_record, nickname, uid, player_reincarnation in results:
                if damage_record.total_damage <= 0:
                    continue
                snapshot = damage_record.reincarnation_snapshot
                # 快照为-1说明是旧数据，回退到玩家当前转数
                effective_reincarnation = snapshot if snapshot != -1 else player_reincarnation
                tier = WorldBossService.get_reincarnation_tier(effective_reincarnation)
                tier_groups[tier].append((damage_record, nickname, uid))

            # 每个段位独立排名发奖
            for tier, group in tier_groups.items():
                # 组内已按伤害降序（来自get_ranking），直接遍历
                for rank, (damage_record, nickname, uid) in enumerate(group, 1):
                    chest_type = None
                    for reward_tier in WorldBossService.REWARD_TIERS:
                        if reward_tier["rank_range"][0] <= rank <= reward_tier["rank_range"][1]:
                            chest_type = reward_tier["chest"]
                            break

                    if chest_type:
                        chest_item_id = chest_item_id_map.get(chest_type)
                        if chest_item_id:
                            chest_item = ItemInstance(
                                player_id=damage_record.player_id,
                                item_id=chest_item_id,
                                quantity=1,
                                created_at=datetime.now()
                            )
                            await self._item_repo.add(chest_item)
                            reward_count += 1

        cycle.settled = True
        await self._cycle_repo.mark_as_settled(cycle)

        if reward_count == 0:
            return f"⚰️ {cycle.boss_name} 消散在虚空中，无人获得其力量..."
        return f"⚔️ {cycle.boss_name} 的威胁已结束！共有 {reward_count} 名勇士获得了深渊宝箱奖励！"

    async def build_boss_view(self, cycle: WorldBossCycle, player: Player) -> str:
        """构建BOSS信息视图

        改造说明:
            - 原Line 227内部commit()已移除，由调用方控制事务
            - 使用self._damage_repo替代session.execute
        """
        # 获取BOSS描述
        boss_data = next((b for b in WorldBossService.BOSS_POOL if b["name"] == cycle.boss_name), None)
        description = boss_data["description"] if boss_data else "神秘的存在，其真实面目无人知晓..."

        # 获取玩家攻击状态
        damage_record = await self._damage_repo.get_or_create(cycle.id, player.id)

        # 确定玩家段位（优先使用快照，未攻击过则用当前转数预测）
        snapshot = damage_record.reincarnation_snapshot
        display_reincarnation = snapshot if snapshot != -1 else player.reincarnation_level
        player_tier = WorldBossService.get_reincarnation_tier(display_reincarnation)
        tier_label = WorldBossService.get_tier_label(player_tier)

        # 检查今日攻击次数
        today = datetime.now().strftime("%Y-%m-%d")
        if damage_record.attacks_reset_date != today:
            damage_record.attacks_today = 0
            damage_record.attacks_reset_date = today
            await self._damage_repo.update(damage_record)

        remaining_attacks = max(0, WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today)

        # 冷却检查
        now_ts = int(time.time())
        cooldown_remaining = max(0, WorldBossService.ATTACK_COOLDOWN - (now_ts - damage_record.last_attack_ts))

        # 获取总参与人数和总伤害
        stmt = select(func.count(WorldBossDamage.id), func.sum(WorldBossDamage.total_damage)).where(
            and_(WorldBossDamage.cycle_id == cycle.id, WorldBossDamage.total_damage > 0)
        )
        result = (await self._session.execute(stmt)).first()
        total_participants = result[0] or 0
        total_damage = result[1] or 0

        # C: 按玩家段位计算BOSS属性；E: 获取弱点
        boss_stats = await self._calculate_boss_stats(cycle, player)
        weakness = WorldBossService.get_boss_weakness(cycle)
        weakness_icon = {"暴击": "💥", "穿透": "🔥", "连击": "⚡"}.get(weakness, "🎯")

        # 构建消息
        lines = [
            f"🌟 世界BOSS：{cycle.boss_name}",
            f"👑 {cycle.boss_title}",
            "━━━━━━━━━━━━━",
            f"📖 {description}",
            "",
            f"🛡️ 对你的防御：{boss_stats['defense']:,}",
            f"⚡ 对你的敏捷：{boss_stats['agility']:,}",
            f"{weakness_icon} 本期弱点：{weakness}（触发时伤害 ×1.5）",
            "",
            f"🎖️ 你的段位：{tier_label}",
            f"⚔️ 你的累计伤害：{damage_record.total_damage:,}",
            f"🎯 今日剩余攻击次数：{remaining_attacks}/{WorldBossService.DAILY_ATTACK_LIMIT}",
        ]

        if cooldown_remaining > 0:
            lines.append(f"⏰ 攻击冷却：{cooldown_remaining}秒")

        lines.extend([
            "",
            f"👥 参与勇士：{total_participants} 人",
            f"💥 累计伤害：{total_damage:,}",
            f"⏳ 结算时间：{cycle.next_refresh_at.strftime('%m-%d %H:%M')}",
            "",
            "💎 奖励预览（各段位独立排名）：",
            "🏆 段内第1名：深渊霸主宝箱",
            "🥈 段内第2-3名：深渊王者宝箱",
            "🥉 段内第4-10名：深渊勇士宝箱",
            "🎖️ 段内第11-30名：深渊探索者宝箱",
            "🏅 段内第31-100名：深渊挑战者宝箱",
            "🎁 参与奖：深渊参与者宝箱",
            "",
            "⚔️ 战斗机制：",
            "  · 装备暴击/连击/穿透/吸血效果全部生效",
            f"  · 命中弱点({weakness})伤害 ×1.5",
            "  · 存活至战斗结束：总伤害 ×1.2",
            "  · 理智防护：闪避可完全躲避，防御15%效益",
            "",
            "📊 段位划分：凡尘(0转) / 轮回(1-2转) / 超脱(3-4转) / 传说(5-6转) / 永恒(7-8转) / 无上(9+转)"
        ])

        return "\n".join(lines)

    async def _get_or_create_damage_record(self, cycle_id: int, player_id: str) -> WorldBossDamage:
        """获取或创建伤害记录

        改造说明:
            - 原Line 324内部commit()已移除，由调用方控制事务
            - 使用self._damage_repo.get_or_create()替代session.execute
        """
        return await self._damage_repo.get_or_create(cycle_id, player_id)

    async def attack_boss(self, cycle: WorldBossCycle, player: Player) -> Tuple[bool, list, str, str]:
        """讨伐BOSS

        Returns:
            (是否成功, 结果行列表, 标题字符串, 摘要字符串)
            ok=True:  list[str]，包含完整 battle_log 与摘要行; title=造成伤害; hint=累计/余次
            ok=False: list[str]，单行错误文字; title=""; hint=""

        改造说明:
            - 原Line 502, 514, 517内部commit()已移除，由调用方控制事务
            - 使用self._damage_repo替代session.execute和session.add
        """
        # 获取伤害记录
        damage_record = await self._get_or_create_damage_record(cycle.id, player.id)

        # 首次攻击时记录转数快照（用于分段排行）
        if damage_record.reincarnation_snapshot == -1:
            damage_record.reincarnation_snapshot = player.reincarnation_level
            await self._damage_repo.update(damage_record)

        # 检查今日攻击次数
        today = datetime.now().strftime("%Y-%m-%d")
        if damage_record.attacks_reset_date != today:
            damage_record.attacks_today = 0
            damage_record.attacks_reset_date = today
            await self._damage_repo.update(damage_record)

        if damage_record.attacks_today >= WorldBossService.DAILY_ATTACK_LIMIT:
            return False, [f"⛔ 今日攻击次数已用完！明日20:00重置（{damage_record.attacks_today}/{WorldBossService.DAILY_ATTACK_LIMIT}）"], "", ""

        # 检查冷却时间
        now_ts = int(time.time())
        if now_ts - damage_record.last_attack_ts < WorldBossService.ATTACK_COOLDOWN:
            remaining = WorldBossService.ATTACK_COOLDOWN - (now_ts - damage_record.last_attack_ts)
            return False, [f"⏰ 攻击冷却中，请等待 {remaining} 秒"], "", ""

        # 检查玩家状态
        if player.hp <= 0:
            return False, ["💀 你已重伤倒地，无法参与战斗！请先恢复生命值"], "", ""

        # C: 按玩家段位计算BOSS属性；E: 获取本期弱点
        boss_stats = await self._calculate_boss_stats(cycle, player)
        weakness = WorldBossService.get_boss_weakness(cycle)

        # A+B+D+E: 执行完整战斗，直接返回 total_damage_dealt
        battle_timestamp = int(time.time() * 1000)
        seed = f"WorldBoss_{cycle.id}:{player.id}:{battle_timestamp}"

        victory, battle_log, sanity_damage, damage_dealt = await self._execute_sanity_battle_v2(
            player, boss_stats, f"{cycle.boss_name}·{cycle.boss_title}",
            weakness=weakness, seed=seed, max_rounds=30
        )

        # 更新玩家状态（理智削减）
        original_mp = player.mp
        player.mp = max(0, player.mp - sanity_damage)

        # 理智归零则血量也为零
        if player.mp <= 0:
            player.hp = 0

        # 更新攻击记录
        damage_record.total_damage += damage_dealt
        damage_record.attacks_today += 1
        damage_record.last_attack_ts = now_ts
        await self._damage_repo.update(damage_record)

        # 发布世界BOSS伤害事件
        await event_bus.publish(WorldBossDamageEvent(
            player_id=player.id,
            boss_id=str(cycle.id),
            boss_name=f"{cycle.boss_name}·{cycle.boss_title}",
            damage=damage_dealt,
            total_damage=damage_record.total_damage,
            is_final_blow=False  # 这里不判断是否为最后一击，可在后续优化
        ))

        # 构建结果消息
        lines = [
            f"⚔️ 你向 {cycle.boss_name} 发起了攻击！",
            "",
            f"💥 造成伤害：{damage_dealt:,}",
            f"📊 累计伤害：{damage_record.total_damage:,}",
            f"🎯 剩余攻击次数：{WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today}/{WorldBossService.DAILY_ATTACK_LIMIT}",
        ]

        if sanity_damage > 0:
            lines.append(f"🧠 你的理智受到了 {sanity_damage} 点侵蚀！({original_mp} → {player.mp})")
            if player.mp <= 0:
                lines.append("💀 你的理智彻底崩溃，陷入了永恒的疯狂")

        # 添加一些克苏鲁风格的战斗描述
        flavor_texts = [
            f"🌀 {cycle.boss_name}的触手在虚空中扭动，散发着令人不安的气息...",
            f"👁️ 无数眼球注视着你，仿佛要将你的灵魂拖入深渊...",
            f"🌊 扭曲的现实在你周围波动，理智在疯狂的边缘摇摆...",
            f"⚡ 古老的力量在空气中激荡，每一击都撼动着维度的壁垒...",
            f"🔮 虚无的低语在你耳边回响，诉说着不可名状的真理..."
        ]
        lines.append("")
        lines.append(random.choice(flavor_texts))

        # 组合完整战斗内容：battle_log + 分割线 + 摘要
        remaining_attacks = WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today
        boss_title = f"🌑 造成 {damage_dealt:,} 伤害"
        boss_hint = f"累计 {damage_record.total_damage:,} · 余{remaining_attacks}次"
        full_lines = list(battle_log) + ["━━━━━━━━━━━━━"] + lines
        return True, full_lines, boss_title, boss_hint

    async def _execute_sanity_battle_v2(
        self,
        player: Player,
        boss_stats: Dict,
        boss_name: str,
        weakness: str,
        seed: str = None,
        max_rounds: int = 30,
    ) -> Tuple[bool, List[str], int, int]:
        """执行理智战斗 v2（A+D+E）

        改进：
        - A: 加载装备并初始化引擎，暴击/连击/穿透/吸血等装备效果全部生效
        - B: 直接返回 total_damage_dealt，不再正则解析日志
        - D: 存活30回合 → 伤害×1.2 奖励
        - E: 命中弱点时该次伤害×1.5

        Returns:
            (是否胜利, 战斗日志, 理智损失, 本次总伤害)
        """
        from ..battle.enhanced_engine import EnhancedBattleEngine
        from ..battle.battle_attributes import BattleAttributeCalculator
        from ..battle.integration_helper import BattleIntegrationHelper
        from sqlalchemy import select as sa_select
        from ..models.inventory import ItemInstance

        # A: 加载已装备物品，初始化引擎触发器
        stmt = sa_select(ItemInstance).where(
            ItemInstance.player_id == player.id,
            ItemInstance.equipped == True,
        )
        equipped_items = (await self._session.execute(stmt)).scalars().all()

        # 预计算含临时buff/宠物/T1词缀的属性（与PVE开战一致），战斗循环内同步判定走缓存
        from ..item.affix_service import get_affixes_from_equipment, get_t1_battle_bonuses
        affix_bonus = {}
        for eq in equipped_items:
            affixes = get_affixes_from_equipment(getattr(eq, 'extra_attrs', None))
            for attr, val in get_t1_battle_bonuses(affixes).items():
                affix_bonus[attr] = affix_bonus.get(attr, 0) + val
        # 叠加套装T1加成（与 integration_helper 预计算保持一致）
        from ..item.set_bonus_service import get_set_t1_bonuses
        for attr, val in get_set_t1_bonuses([getattr(eq, 'item_id', '') for eq in equipped_items]).items():
            affix_bonus[attr] = affix_bonus.get(attr, 0) + val
        player_base_attrs = await player.get_effective_attributes(self._session)
        player._cached_attack = player_base_attrs.get('attack', player.attack)
        player._cached_defense = player_base_attrs.get('defense', player.defense)
        player._cached_max_hp = player_base_attrs.get('max_hp', getattr(player, 'max_hp', 0))
        player._cached_max_mp = player_base_attrs.get('max_mp', getattr(player, 'max_mp', 0))
        player._cached_agility = player_base_attrs.get('agility', player.agility)
        player._cached_battle_attrs = await BattleAttributeCalculator.calculate_effective_attributes_async(
            player, self._session, equipment_bonus=affix_bonus
        )

        engine = EnhancedBattleEngine(seed)
        engine.start_battle(player, boss_stats, equipped_items)

        battle_log: List[str] = []
        sanity_damage = 0
        total_damage_dealt = 0

        battle_log.append(f"⚔️ {player.nickname} VS {boss_name}")
        if weakness:
            weakness_icon = {"暴击": "💥", "穿透": "🔥", "连击": "⚡"}.get(weakness, "🎯")
            battle_log.append(f"{weakness_icon} 弱点：{weakness}（触发时伤害 ×1.5）")
        battle_log.append("")

        for round_num in range(1, max_rounds + 1):
            if player.mp - sanity_damage <= 0:
                break

            battle_log.append(f"━━━ 第{round_num}回合 ━━━")

            # 玩家攻击BOSS（完整属性系统：暴击/连击/穿透/吸血均生效，攻击力含临时buff）
            player_attack = getattr(player, '_cached_attack', player.attack)
            attack_result = engine.execute_player_turn(player, boss_stats, player_attack, False)

            if attack_result["hit"]:
                damage = attack_result.get("total_damage", attack_result.get("damage", 0))
                is_crit = attack_result.get("is_critical", False)
                is_pen = attack_result.get("is_penetration", False)
                combo_count = attack_result.get("combo_count", 1)

                # E: 弱点加成
                weakness_triggered = (
                    (weakness == "暴击" and is_crit) or
                    (weakness == "穿透" and is_pen) or
                    (weakness == "连击" and combo_count > 1)
                )
                if weakness_triggered:
                    damage = int(damage * 1.5)

                total_damage_dealt += damage

                effects = []
                if is_crit:
                    effects.append("💥暴击")
                if is_pen:
                    effects.append("🔥穿透")
                if combo_count > 1:
                    effects.append(f"⚡连击x{combo_count}")
                if weakness_triggered:
                    effects.append("🎯弱点")

                attack_desc = f"⚔️ {player.nickname} 攻击 {boss_name}"
                if effects:
                    attack_desc += f"({' '.join(effects)})"
                attack_desc += f"，造成 {damage:,} 点伤害"
                battle_log.append(attack_desc)
            else:
                battle_log.append(f"💨 {player.nickname} 的攻击被 {boss_name} 闪避了")

            # BOSS反击：通过完整怪物攻击逻辑计算理智侵蚀（玩家防御/闪避生效）
            round_sanity = WorldBossService._calculate_sanity_damage_v2(boss_stats, player, engine)
            sanity_damage += round_sanity

            if round_sanity > 0:
                battle_log.append(
                    f"🧠 {boss_name} 侵蚀了你的理智，损失 {round_sanity} 点"
                    f"（防御减免后）"
                )
                battle_log.append(f"   当前理智：{max(0, player.mp - sanity_damage)}")
            else:
                battle_log.append(f"💨 你成功闪避了 {boss_name} 的精神侵蚀！")

            if player.mp - sanity_damage <= 0:
                battle_log.append("💀 你的理智彻底崩溃，陷入了永恒的疯狂...")
                break

            battle_log.append("")

        victory = player.mp - sanity_damage > 0

        if victory:
            # D: 存活奖励：伤害 ×1.2
            survival_bonus = int(total_damage_dealt * 0.2)
            total_damage_dealt += survival_bonus
            battle_log.append(f"🎉 你成功抵抗了 {boss_name} 的疯狂侵蚀！")
            battle_log.append(f"✨ 存活奖励 +20%：+{survival_bonus:,} 伤害")
        else:
            battle_log.append(f"💀 你被 {boss_name} 的疯狂力量彻底击垮...")

        battle_log.append("")
        battle_log.append(f"📊 本次讨伐总伤害：{total_damage_dealt:,}")

        # 重置首回合临时加成（如灵影体质）
        try:
            engine.reset_temp_bonuses(player)
        except Exception:
            pass

        return victory, battle_log, sanity_damage, total_damage_dealt

    @staticmethod
    def _calculate_sanity_damage_v2(boss_stats: Dict, player: Player, engine: "EnhancedBattleEngine") -> int:
        """计算理智侵蚀量（A: 玩家防御和闪避均有效）

        使用与普通怪物攻击相同的命中/减伤逻辑：
        - 玩家闪避率可完全躲避
        - 玩家防御力部分减免（理智侵蚀只受15%防御效益）
        """
        from ..battle.battle_attributes import BattleAttributeCalculator
        from ..utils import apply_defense_mitigation

        base_attack = boss_stats.get("attack", 0)
        if base_attack <= 0:
            return 0

        # 闪避判定（优先使用开战预计算缓存，含临时buff/宠物/词缀）
        player_attrs = BattleAttributeCalculator.effective_attrs_in_battle(player)
        dodge_rate = player_attrs.get("dodge_rate", 0)
        if engine.rng.random() * 100 < dodge_rate:
            return 0  # 闪避成功，本回合无理智损失

        # 防御减伤（只有15%效益体现在理智防护上，体现出"精神防御难以依赖肉体"）
        effective_defense = int(getattr(player, '_cached_defense', player.defense) * 0.15)
        variation = engine.rng.uniform(0.85, 1.15)
        raw = max(1, int(base_attack * variation))
        mitigation = apply_defense_mitigation(raw, effective_defense)
        return max(1, int(mitigation["final_damage"]))

    async def _calculate_boss_stats(self, cycle: WorldBossCycle, player: Player = None) -> Dict:
        """计算BOSS属性（C: 按玩家段位分级，基准来自同区最高玩家）"""
        # 获取最高等级玩家（基准参考，限玩家所在区服）
        stmt = select(Player)
        if player is not None:
            stmt = stmt.where(Player.server_id == player.server_id)
        stmt = stmt.order_by(desc(Player.level)).limit(1)
        top_player = (await self._session.execute(stmt)).scalars().first()

        if not top_player:
            return {"hp": 9_999_999_999, "defense": 100, "agility": 80, "attack": 50, "level": "???"}

        # C: 根据当前玩家的段位选取倍率
        ref = player if player else top_player
        tier = WorldBossService.get_reincarnation_tier(ref.reincarnation_level)
        tier_idx = min(tier, len(WorldBossService.TIER_STATS_MULTIPLIERS) - 1)
        def_mult, agi_mult, atk_mult = WorldBossService.TIER_STATS_MULTIPLIERS[tier_idx]

        base_defense = 10 + int(top_player.defense * def_mult)
        base_agility = 10 + int(top_player.agility * agi_mult)
        # 攻击力 = 玩家理智上限 × 倍率（用于削减玩家理智，受玩家防御/闪避减弱）
        base_attack = int((ref.max_mp if ref.max_mp > 0 else 1000) * atk_mult)

        return {
            "hp": 9_999_999_999,  # 实际无限血量
            "defense": int(base_defense),
            "agility": int(base_agility),
            "attack": int(base_attack),
            "level": "???"
        }



    async def build_ranking_view(self, cycle: WorldBossCycle, server_id: int) -> str:
        """构建分段排行榜视图（限同区服）"""
        results = await self._damage_repo.get_ranking(cycle.id, limit=999999, server_id=server_id)

        header = [
            f"🌟 世界BOSS：{cycle.boss_name}",
            f"👑 {cycle.boss_title}",
            "━━━━━━━━━━━━━",
        ]

        if not results:
            return "\n".join(header + [
                "",
                "💀 暂无勇士敢于挑战这位深渊霸主...",
                "",
                f"⏳ 结算时间：{cycle.next_refresh_at.strftime('%m-%d %H:%M')}"
            ])

        # 按段位分组（已按伤害降序，维持顺序）
        from collections import defaultdict
        tier_groups: dict = defaultdict(list)
        for damage_record, nickname, uid, player_reincarnation in results:
            if damage_record.total_damage <= 0:
                continue
            snapshot = damage_record.reincarnation_snapshot
            effective_reincarnation = snapshot if snapshot != -1 else player_reincarnation
            tier = WorldBossService.get_reincarnation_tier(effective_reincarnation)
            tier_groups[tier].append((damage_record, nickname, uid))

        lines = header[:]

        # 按段位从高到低展示（高段在上）
        for tier in sorted(tier_groups.keys(), reverse=True):
            group = tier_groups[tier]
            tier_label = WorldBossService.get_tier_label(tier)
            lines.extend(["", f"🏛️ {tier_label}"])

            for rank, (damage_record, nickname, uid) in enumerate(group[:10], 1):
                reward_desc = "🎁 参与奖"
                for reward_tier in WorldBossService.REWARD_TIERS:
                    if reward_tier["rank_range"][0] <= rank <= reward_tier["rank_range"][1]:
                        reward_desc = reward_tier["description"]
                        break

                if rank == 1:
                    icon = "🥇"
                elif rank == 2:
                    icon = "🥈"
                elif rank == 3:
                    icon = "🥉"
                else:
                    icon = "🎖️"

                lines.append(f"{icon} {rank}. {cmd(nickname, f'面板 {uid}')} - {damage_record.total_damage:,}")

            if len(group) > 10:
                lines.append(f"   ... 还有 {len(group) - 10} 名勇士参与")

        total_participants = sum(len(g) for g in tier_groups.values())
        total_damage = sum(r.total_damage for r, _, _, _ in results if r.total_damage > 0)
        lines.extend([
            "",
            "━━━━━━━━━━━━━",
            f"👥 总参与：{total_participants} 人  💥 总伤害：{total_damage:,}",
            f"⏳ 结算时间：{cycle.next_refresh_at.strftime('%m-%d %H:%M')}",
            "",
            "💎 各段位独立排名，同等奖励",
            "📊 段位：凡尘(0转) / 轮回(1-2转) / 超脱(3-4转) / 传说(5-6转) / 永恒(7-8转) / 无上(9+转)"
        ])

        return "\n".join(lines)
