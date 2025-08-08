from __future__ import annotations

"""世界BOSS系统核心服务

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


class WorldBossService:
    """世界BOSS系统核心服务类"""
    
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
    
    # 理智削减配置
    SANITY_DAMAGE_CONFIG = {
        "low_level_threshold": 50,  # 低等级阈值
        "low_level_fixed_damage": (40, 80),  # 低等级固定伤害范围
        "high_level_percentage": (0.10, 0.20),  # 高等级百分比伤害范围
    }
    
    # 奖励区间配置（按累计伤害排名）
    REWARD_TIERS = [
        {"rank_range": (1, 1), "chest": "深渊霸主宝箱", "description": "🏆 第1名"},
        {"rank_range": (2, 3), "chest": "深渊王者宝箱", "description": "🥈 第2-3名"},
        {"rank_range": (4, 10), "chest": "深渊勇士宝箱", "description": "🥉 第4-10名"},
        {"rank_range": (11, 30), "chest": "深渊探索者宝箱", "description": "🎖️ 第11-30名"},
        {"rank_range": (31, 100), "chest": "深渊挑战者宝箱", "description": "🏅 第31-100名"},
        {"rank_range": (101, 999999), "chest": "深渊参与者宝箱", "description": "🎁 参与奖"}
    ]
    
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
    
    @staticmethod
    async def check_and_refresh_cycle(session: AsyncSession) -> Tuple[WorldBossCycle, Optional[str]]:
        """检查并刷新周期（懒加载触发）
        
        Returns:
            (当前周期, 刷新提示信息)
        """
        now = datetime.now()
        
        # 获取最新的周期
        stmt = select(WorldBossCycle).order_by(desc(WorldBossCycle.id)).limit(1)
        current_cycle = (await session.execute(stmt)).scalars().first()
        
        # 如果没有周期或者已到刷新时间，创建新周期
        if not current_cycle or now >= current_cycle.next_refresh_at:
            # 结算旧周期（如果存在且未结算）
            settlement_tip = None
            if current_cycle and not current_cycle.settled:
                settlement_tip = await WorldBossService._settle_cycle(session, current_cycle)
            
            # 创建新周期
            next_refresh = WorldBossService._get_next_refresh_time()
            cycle_key = WorldBossService._generate_cycle_key(next_refresh)
            
            # 随机选择BOSS
            boss_data = random.choice(WorldBossService.BOSS_POOL)
            
            new_cycle = WorldBossCycle(
                cycle_key=cycle_key,
                boss_name=boss_data["name"],
                boss_title=boss_data["title"],
                started_at=now,
                next_refresh_at=next_refresh,
                settled=False
            )
            
            session.add(new_cycle)
            await session.commit()
            
            tip = f"🌟 新的世界BOSS已降临！{boss_data['name']} 等待着勇士们的挑战！"
            if settlement_tip:
                tip = settlement_tip + "\n\n" + tip
            
            return new_cycle, tip
        
        return current_cycle, None
    
    @staticmethod
    async def _settle_cycle(session: AsyncSession, cycle: WorldBossCycle) -> str:
        """结算周期奖励"""
        # 获取排行榜
        stmt = select(WorldBossDamage, Player).join(
            Player, WorldBossDamage.player_id == Player.id
        ).where(
            WorldBossDamage.cycle_id == cycle.id
        ).order_by(desc(WorldBossDamage.total_damage))
        
        results = (await session.execute(stmt)).all()
        
        if not results:
            cycle.settled = True
            session.add(cycle)
            await session.commit()
            return f"⚰️ {cycle.boss_name} 消散在虚空中，无人获得其力量..."
        
        # 分发奖励
        reward_count = 0
        for rank, (damage_record, player) in enumerate(results, 1):
            if damage_record.total_damage <= 0:
                continue
                
            # 确定奖励等级
            chest_type = None
            for tier in WorldBossService.REWARD_TIERS:
                if tier["rank_range"][0] <= rank <= tier["rank_range"][1]:
                    chest_type = tier["chest"]
                    break
            
            if chest_type:
                # 根据宝箱类型确定item_id
                chest_item_id_map = {
                    "深渊霸主宝箱": "abyss_overlord_chest",
                    "深渊王者宝箱": "abyss_king_chest",
                    "深渊勇士宝箱": "abyss_warrior_chest",
                    "深渊探索者宝箱": "abyss_explorer_chest",
                    "深渊挑战者宝箱": "abyss_challenger_chest",
                    "深渊参与者宝箱": "abyss_participant_chest"
                }

                chest_item_id = chest_item_id_map.get(chest_type)
                if chest_item_id:
                    # 创建宝箱物品实例
                    chest_item = ItemInstance(
                        player_id=player.id,
                        item_id=chest_item_id,
                        quantity=1,
                        created_at=datetime.now()
                    )
                    session.add(chest_item)
                    reward_count += 1
        
        cycle.settled = True
        session.add(cycle)
        await session.commit()
        
        return f"⚔️ {cycle.boss_name} 的威胁已结束！共有 {reward_count} 名勇士获得了深渊宝箱奖励！"
    
    @staticmethod
    async def build_boss_view(session: AsyncSession, cycle: WorldBossCycle, player: Player) -> str:
        """构建BOSS信息视图"""
        # 获取BOSS描述
        boss_data = next((b for b in WorldBossService.BOSS_POOL if b["name"] == cycle.boss_name), None)
        description = boss_data["description"] if boss_data else "神秘的存在，其真实面目无人知晓..."
        
        # 获取玩家攻击状态
        damage_record = await WorldBossService._get_or_create_damage_record(session, cycle.id, player.id)
        
        # 检查今日攻击次数
        today = datetime.now().strftime("%Y-%m-%d")
        if damage_record.attacks_reset_date != today:
            damage_record.attacks_today = 0
            damage_record.attacks_reset_date = today
            session.add(damage_record)
            await session.commit()
        
        remaining_attacks = max(0, WorldBossService.DAILY_ATTACK_LIMIT - damage_record.attacks_today)
        
        # 冷却检查
        now_ts = int(time.time())
        cooldown_remaining = max(0, WorldBossService.ATTACK_COOLDOWN - (now_ts - damage_record.last_attack_ts))
        
        # 获取总参与人数和总伤害
        stmt = select(func.count(WorldBossDamage.id), func.sum(WorldBossDamage.total_damage)).where(
            and_(WorldBossDamage.cycle_id == cycle.id, WorldBossDamage.total_damage > 0)
        )
        result = (await session.execute(stmt)).first()
        total_participants = result[0] or 0
        total_damage = result[1] or 0
        
        # 构建消息
        lines = [
            f"🌟 世界BOSS：{cycle.boss_name}",
            f"👑 {cycle.boss_title}",
            "━━━━━━━━━━━━━",
            f"📖 {description}",
            "",
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
            "💎 奖励预览：",
            "🏆 第1名：深渊霸主宝箱",
            "🥈 第2-3名：深渊王者宝箱", 
            "🥉 第4-10名：深渊勇士宝箱",
            "🎖️ 第11-30名：深渊探索者宝箱",
            "🏅 第31-100名：深渊挑战者宝箱",
            "🎁 参与奖：深渊参与者宝箱"
        ])
        
        return "\n".join(lines)

    @staticmethod
    async def _get_or_create_damage_record(session: AsyncSession, cycle_id: int, player_id: str) -> WorldBossDamage:
        """获取或创建伤害记录"""
        stmt = select(WorldBossDamage).where(
            and_(WorldBossDamage.cycle_id == cycle_id, WorldBossDamage.player_id == player_id)
        )
        record = (await session.execute(stmt)).scalars().first()

        if not record:
            record = WorldBossDamage(
                cycle_id=cycle_id,
                player_id=player_id,
                total_damage=0,
                last_attack_ts=0,
                attacks_today=0,
                attacks_reset_date=""
            )
            session.add(record)
            await session.commit()

        return record

    @staticmethod
    async def attack_boss(session: AsyncSession, cycle: WorldBossCycle, player: Player) -> Tuple[bool, str]:
        """讨伐BOSS

        Returns:
            (是否成功, 结果消息)
        """
        # 获取伤害记录
        damage_record = await WorldBossService._get_or_create_damage_record(session, cycle.id, player.id)

        # 检查今日攻击次数
        today = datetime.now().strftime("%Y-%m-%d")
        if damage_record.attacks_reset_date != today:
            damage_record.attacks_today = 0
            damage_record.attacks_reset_date = today
            session.add(damage_record)
            await session.commit()

        if damage_record.attacks_today >= WorldBossService.DAILY_ATTACK_LIMIT:
            return False, f"⛔ 今日攻击次数已用完！明日20:00重置（{damage_record.attacks_today}/{WorldBossService.DAILY_ATTACK_LIMIT}）"

        # 检查冷却时间
        now_ts = int(time.time())
        if now_ts - damage_record.last_attack_ts < WorldBossService.ATTACK_COOLDOWN:
            remaining = WorldBossService.ATTACK_COOLDOWN - (now_ts - damage_record.last_attack_ts)
            return False, f"⏰ 攻击冷却中，请等待 {remaining} 秒"

        # 检查玩家状态
        if player.hp <= 0:
            return False, "💀 你已重伤倒地，无法参与战斗！请先恢复生命值"

        # 构建BOSS属性（基于最高等级玩家）
        boss_stats = await WorldBossService._calculate_boss_stats(session, cycle)

        # 执行战斗（新的理智削减机制）
        battle_timestamp = int(time.time() * 1000)
        seed = f"WorldBoss_{cycle.id}:{player.id}:{battle_timestamp}"

        victory, battle_log, sanity_damage = WorldBossService._execute_sanity_battle(
            player, boss_stats, f"{cycle.boss_name}·{cycle.boss_title}", seed=seed, max_rounds=30
        )

        # 计算造成的伤害（基于战斗过程）
        damage_dealt = WorldBossService._calculate_damage_from_battle(battle_log, player, boss_stats)

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
        session.add(damage_record)
        
        # 提交所有更改到数据库
        await session.commit()

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

        return True, "\n".join(lines)

    @staticmethod
    def _execute_sanity_battle(player: Player, boss_stats: Dict, boss_name: str, 
                              seed: str = None, max_rounds: int = 30) -> Tuple[bool, List[str], int]:
        """执行理智战斗（新的战斗机制）
        
        Args:
            player: 玩家对象
            boss_stats: BOSS属性
            boss_name: BOSS名称
            seed: 随机种子
            max_rounds: 最大回合数
            
        Returns:
            (是否胜利, 战斗日志, 理智损失)
        """
        import random
        if seed:
            import hashlib
            rng = random.Random(hashlib.md5(seed.encode()).hexdigest())
        else:
            rng = random.Random()
        
        battle_log = []
        sanity_damage = 0
        
        battle_log.append(f"⚔️ {player.nickname} VS {boss_name}")
        
        # 执行战斗回合
        for round_num in range(1, max_rounds + 1):
            if player.mp <= 0:
                break
                
            battle_log.append(f"━━━ 第{round_num}回合 ━━━")
            
            # 玩家讨伐BOSS（造成伤害）
            player_damage = WorldBossService._calculate_player_damage(player, boss_stats, rng)
            battle_log.append(f"⚔️ {player.nickname} 攻击 {boss_name}，造成 {player_damage} 点伤害")
            
            # BOSS反击（削减理智）
            round_sanity_damage = WorldBossService._calculate_sanity_damage(player, rng)
            sanity_damage += round_sanity_damage
            
            if round_sanity_damage > 0:
                battle_log.append(f"🧠 {boss_name} 的攻击侵蚀了你的理智，损失 {round_sanity_damage} 点理智")
                battle_log.append(f"   当前理智：{player.mp - sanity_damage}")
            
            # 检查理智是否归零
            if player.mp - sanity_damage <= 0:
                battle_log.append("💀 你的理智彻底崩溃，陷入了永恒的疯狂...")
                break
        
        # 战斗结果
        victory = player.mp - sanity_damage > 0
        
        if victory:
            battle_log.append(f"🎉 你成功抵抗了 {boss_name} 的疯狂侵蚀！")
        else:
            battle_log.append(f"💀 你被 {boss_name} 的疯狂力量彻底击垮...")
        
        return victory, battle_log, sanity_damage

    @staticmethod
    def _calculate_sanity_damage(player: Player, rng: random.Random) -> int:
        """计算理智削减量
        
        Args:
            player: 玩家对象
            rng: 随机数生成器
            
        Returns:
            理智削减量
        """
        config = WorldBossService.SANITY_DAMAGE_CONFIG
        
        if player.level <= config["low_level_threshold"]:
            # 低等级玩家：固定伤害
            min_damage, max_damage = config["low_level_fixed_damage"]
            return rng.randint(min_damage, max_damage)
        else:
            # 高等级玩家：百分比伤害
            min_percent, max_percent = config["high_level_percentage"]
            damage_percent = rng.uniform(min_percent, max_percent)
            return max(1, int(player.max_mp * damage_percent))

    @staticmethod
    def _calculate_player_damage(player: Player, boss_stats: Dict, rng: random.Random) -> int:
        """计算玩家对BOSS造成的伤害"""
        # 基础伤害计算（基于玩家攻击力和BOSS防御）
        base_damage = max(1, player.attack - boss_stats["defense"] // 2)
        
        # 添加随机波动
        damage_variance = rng.randint(-base_damage // 4, base_damage // 4)
        final_damage = max(1, base_damage + damage_variance)
        
        # 运气加成
        luck_bonus = player.luck * 2
        final_damage += luck_bonus
        
        return final_damage

    @staticmethod
    async def _calculate_boss_stats(session: AsyncSession, cycle: WorldBossCycle) -> Dict[str, int]:
        """计算BOSS属性（基于最高等级玩家）"""
        # 获取最高等级玩家
        stmt = select(Player).order_by(desc(Player.level)).limit(1)
        top_player = (await session.execute(stmt)).scalars().first()
        
        if not top_player:
            # 如果没有玩家，使用默认值
            base_defense = 100
            base_agility = 80
        else:
            # 基于最高等级玩家的属性
            base_defense = top_player.defense
            base_agility = top_player.agility
        
        # 添加随机波动（±10%）
        defense_variance = random.uniform(0.9, 1.1)
        agility_variance = random.uniform(0.9, 1.1)
        
        return {
            "defense": int(base_defense * defense_variance),
            "agility": int(base_agility * agility_variance),
            "level": "???"  # 等级显示为???
        }

    @staticmethod
    def _calculate_damage_from_battle(battle_log: List[str], player: Player, boss_stats: Dict[str, int]) -> int:
        """从战斗日志中计算造成的伤害"""
        # 基础伤害计算（基于玩家属性和BOSS防御）
        base_damage = max(1, player.attack - boss_stats["defense"] // 2)

        # 添加随机波动
        damage_variance = random.randint(-base_damage // 4, base_damage // 4)
        final_damage = max(1, base_damage + damage_variance)

        # 运气加成
        luck_bonus = player.luck * 2
        final_damage += luck_bonus

        return final_damage

    @staticmethod
    async def build_ranking_view(session: AsyncSession, cycle: WorldBossCycle) -> str:
        """构建排行榜视图"""
        # 获取排行榜数据
        stmt = select(WorldBossDamage, Player).join(
            Player, WorldBossDamage.player_id == Player.id
        ).where(
            and_(WorldBossDamage.cycle_id == cycle.id, WorldBossDamage.total_damage > 0)
        ).order_by(desc(WorldBossDamage.total_damage)).limit(50)

        results = (await session.execute(stmt)).all()

        if not results:
            return f"🌟 世界BOSS：{cycle.boss_name}\n👑 {cycle.boss_title}\n━━━━━━━━━━━━━━━━━━━━\n\n💀 暂无勇士敢于挑战这位深渊霸主...\n\n⏳ 结算时间：{cycle.next_refresh_at.strftime('%m-%d %H:%M')}"

        # 构建排行榜
        lines = [
            f"🌟 世界BOSS：{cycle.boss_name}",
            f"👑 {cycle.boss_title}",
            "━━━━━━━━━━━━━",
            "🏆 伤害排行榜",
            ""
        ]

        # 显示前20名
        for rank, (damage_record, player) in enumerate(results[:20], 1):
            # 确定奖励等级
            reward_desc = "🎁 参与奖"
            for tier in WorldBossService.REWARD_TIERS:
                if tier["rank_range"][0] <= rank <= tier["rank_range"][1]:
                    reward_desc = tier["description"]
                    break

            # 排名图标
            if rank == 1:
                rank_icon = "🥇"
            elif rank == 2:
                rank_icon = "🥈"
            elif rank == 3:
                rank_icon = "🥉"
            elif rank <= 10:
                rank_icon = "🎖️"
            else:
                rank_icon = "🏅"

            lines.append(f"{rank_icon} {rank:2d}. {player.nickname}({player.uid}) - {damage_record.total_damage:,}")

        if len(results) > 20:
            lines.append(f"... 还有 {len(results) - 20} 名勇士参与挑战")

        # 统计信息
        total_damage = sum(record.total_damage for record, _ in results)
        lines.extend([
            "",
            f"👥 参与勇士：{len(results)} 人",
            f"💥 累计伤害：{total_damage:,}",
            f"⏳ 结算时间：{cycle.next_refresh_at.strftime('%m-%d %H:%M')}",
            "",
            "💎 奖励区间：",
            "🏆 第1名：深渊霸主宝箱",
            "🥈 第2-3名：深渊王者宝箱",
            "🥉 第4-10名：深渊勇士宝箱",
            "🎖️ 第11-30名：深渊探索者宝箱",
            "🏅 第31-100名：深渊挑战者宝箱",
            "🎁 参与奖：深渊参与者宝箱"
        ])

        return "\n".join(lines)
