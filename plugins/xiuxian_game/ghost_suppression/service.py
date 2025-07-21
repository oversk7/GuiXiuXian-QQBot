"""鬼怪镇压系统核心服务"""
from typing import List, Tuple, Optional, Dict
import random
from datetime import date, datetime
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.player import Player
from ..models.ghost_invasion import GhostInvasion
from ..models.player_ghost import PlayerGhost
from ..models.inventory import ItemInstance
from ..config import config


class GhostSuppressionService:
    """鬼怪镇压系统服务类"""
    
    @staticmethod
    async def get_daily_invasions(session: AsyncSession, target_date: date = None) -> List[GhostInvasion]:
        """获取指定日期的鬼怪入侵事件"""
        if target_date is None:
            target_date = date.today()
        
        result = await session.execute(
            select(GhostInvasion).where(GhostInvasion.invasion_date == target_date)
        )
        return result.scalars().all()
    
    @staticmethod
    async def get_invasion_at_location(session: AsyncSession, region: str, x: int, y: int) -> Optional[GhostInvasion]:
        """获取指定位置的鬼怪入侵事件"""
        today = date.today()
        result = await session.execute(
            select(GhostInvasion).where(
                and_(
                    GhostInvasion.region == region,
                    GhostInvasion.x == x,
                    GhostInvasion.y == y,
                    GhostInvasion.invasion_date == today,
                    GhostInvasion.is_suppressed == False
                )
            )
        )
        return result.scalars().first()
    
    @staticmethod
    async def get_player_active_ghost(session: AsyncSession, player_id: str) -> Optional[PlayerGhost]:
        """获取玩家当前驾驭的鬼怪"""
        result = await session.execute(
            select(PlayerGhost).where(
                and_(
                    PlayerGhost.player_id == player_id,
                    PlayerGhost.is_active == True
                )
            )
        )
        return result.scalars().first()
    
    @staticmethod
    async def get_player_ghosts(session: AsyncSession, player_id: str) -> List[PlayerGhost]:
        """获取玩家拥有的所有鬼怪"""
        result = await session.execute(
            select(PlayerGhost).where(PlayerGhost.player_id == player_id)
        )
        return result.scalars().all()
    
    @staticmethod
    def calculate_prestige_level(ghost_config: dict, player: Player) -> int:
        """计算鬼怪在玩家手中的威压等级"""
        from .ghost_utils import GhostUtils

        required_attr = ghost_config["required_attribute"]
        player_attr_value = getattr(player, required_attr, 0)

        return GhostUtils.calculate_prestige_level(ghost_config, player_attr_value)
    
    @staticmethod
    def simulate_battle(player_ghost: PlayerGhost, player: Player, wild_ghost_config: dict) -> Tuple[bool, str, int]:
        """
        模拟战斗 - 参考副本系统的战斗机制
        返回: (是否胜利, 战斗描述, 造成伤害)
        """
        from .ghost_utils import GhostUtils

        # 获取玩家鬼怪配置
        player_ghost_config = player_ghost.get_config()

        # 计算玩家鬼怪的实际属性（考虑等级）
        player_ghost_attrs = player_ghost.get_actual_attributes()
        player_hp = player_ghost_attrs["hp"] + player.hp // 2
        player_attack = player_ghost_attrs["attack"] + player.attack
        player_defense = player_ghost_attrs["defense"] + player.defense
        player_agility = player_ghost_attrs["agility"] + player.agility

        # 野生鬼怪属性（固定等级1）
        wild_ghost_attrs = GhostUtils.calculate_ghost_attributes(wild_ghost_config, 1)
        wild_hp = wild_ghost_attrs["hp"]
        wild_attack = wild_ghost_attrs["attack"]
        wild_defense = wild_ghost_attrs["defense"]
        wild_agility = wild_ghost_attrs["agility"]

        # 记录初始血量用于计算伤害
        initial_player_hp = player_hp
        initial_wild_hp = wild_hp

        # 使用确定性随机数生成器
        import hashlib
        seed = f"{player_ghost.id}:{wild_ghost_config['ghost_id']}:{player.id}"
        rng = random.Random(hashlib.md5(seed.encode()).hexdigest())

        battle_log = []
        dodge_count = 0
        max_rounds = 20

        def record_battle(round_num, text, force=False):
            """记录战斗日志，只记录关键回合"""
            if force or round_num == 1 or round_num % 3 == 0:
                battle_log.append(text)

        for round_num in range(1, max_rounds + 1):
            if player_hp <= 0 or wild_hp <= 0:
                break

            # 敏捷决定先手概率
            player_first = rng.random() < (player_agility / (player_agility + wild_agility))

            def player_attack_turn(r_num):
                nonlocal wild_hp
                # 伤害计算：基础攻击力 * 随机系数 - 防御力
                base_damage = int(player_attack * rng.uniform(0.8, 1.2))
                damage = max(1, base_damage - wild_defense)

                # 暴击判定（基于玩家的幸运值）
                crit = False
                from ..utils import luck_prob
                if rng.random() < luck_prob(player.luck):
                    damage = int(damage * 1.5)
                    crit = True

                wild_hp = max(0, wild_hp - damage)
                crit_text = "💥 暴击！" if crit else ""
                record_battle(r_num, f"[回合{r_num}] {crit_text}你的{player_ghost_config['name']}造成 {damage} 伤害", force=(crit or wild_hp == 0))

            def wild_attack_turn(r_num):
                nonlocal player_hp, dodge_count

                # 闪避判定
                dodge_chance = player_agility / (player_agility + wild_agility + 30)
                if rng.random() < dodge_chance:
                    dodge_count += 1
                    record_battle(r_num, f"[回合{r_num}] ⚡ 你的{player_ghost_config['name']}敏捷地闪避了攻击！")
                    return

                # 伤害计算
                base_damage = rng.randint(int(wild_attack * 0.8), int(wild_attack * 1.2))
                # 防御减伤：效果递减
                damage = max(1, int(base_damage * 100 / (100 + player_defense)))
                blocked = base_damage - damage

                player_hp = max(0, player_hp - damage)

                if blocked > 0:
                    record_battle(r_num, f"[回合{r_num}] 野生{wild_ghost_config['name']}造成 {damage} 伤害（格挡 {blocked}）", force=(player_hp == 0))
                else:
                    record_battle(r_num, f"[回合{r_num}] 野生{wild_ghost_config['name']}造成 {damage} 伤害", force=(player_hp == 0))

            # 回合制战斗：先手方优先攻击，击杀对方则后手无法行动
            if player_first:
                player_attack_turn(round_num)
                if wild_hp > 0:
                    wild_attack_turn(round_num)
            else:
                wild_attack_turn(round_num)
                if player_hp > 0:
                    player_attack_turn(round_num)

        victory = wild_hp <= 0
        total_damage = initial_wild_hp - max(0, wild_hp)

        # 生成简洁的战斗报告
        battle_summary = []

        # 添加关键战斗日志（最多显示5条）
        if len(battle_log) > 5:
            battle_summary.extend(battle_log[:2])  # 前两回合
            battle_summary.append("...")
            battle_summary.extend(battle_log[-2:])  # 最后两回合
        else:
            battle_summary.extend(battle_log)

        # 战斗统计
        battle_summary.append(f"📊 总计 {round_num} 回合，你的{player_ghost_config['name']} HP {player_hp}/{initial_player_hp}，野生{wild_ghost_config['name']} HP {wild_hp}/{initial_wild_hp}")

        if dodge_count > 0:
            battle_summary.append(f"🌀 成功闪避 {dodge_count} 次攻击！")

        # 结果
        if victory:
            battle_summary.append(f"🎉 镇压成功！野生{wild_ghost_config['name']}被彻底击败！")
        else:
            battle_summary.append(f"💀 镇压失败！你的{player_ghost_config['name']}不敌对手...")

        return victory, "\n".join(battle_summary), total_damage
    
    @staticmethod
    async def check_prestige_phase(
        session: AsyncSession,
        player: Player,
        invasion: GhostInvasion,
        use_coffin_nail: bool = False
    ) -> dict:
        """
        威压判定阶段
        返回: {"success": bool, "message": str, "player_ghost": PlayerGhost, "wild_ghost_config": dict}
        """
        # 获取鬼怪配置
        wild_ghost_config = config.ghosts_config["by_id"].get(invasion.ghost_id)
        if not wild_ghost_config:
            return {"success": False, "message": "❌ 未知的鬼怪类型"}

        # 获取玩家当前驾驭的鬼怪
        player_ghost = await GhostSuppressionService.get_player_active_ghost(session, player.id)
        if not player_ghost:
            return {"success": False, "message": "❌ 你没有驾驭任何鬼，能对付鬼的只有鬼，请先通过【试炼】领取鬼"}

        player_ghost_config = player_ghost.get_config()
        if not player_ghost_config:
            return {"success": False, "message": "❌ 你驾驭的鬼怪配置异常"}

        # 威压判定
        player_prestige = GhostSuppressionService.calculate_prestige_level(player_ghost_config, player)
        wild_prestige = wild_ghost_config["base_prestige_level"]

        result_messages = []
        result_messages.append(f"🔥 威压对决：")
        result_messages.append(f"你的{player_ghost_config['name']}(Lv.{player_ghost.level}) 威压等级: {player_prestige}")
        result_messages.append(f"野生{wild_ghost_config['name']} 威压等级: {wild_prestige}")

        prestige_passed = False
        if use_coffin_nail:
            result_messages.append("⚰️ 使用棺材钉强制压制灵异规则！")
            prestige_passed = True
        elif player_prestige >= wild_prestige:
            result_messages.append("✅ 威压判定通过！")
            prestige_passed = True
        else:
            result_messages.append("❌ 威压不足，无法压制对方的灵异规则！")

        return {
            "success": prestige_passed,
            "message": "\n".join(result_messages),
            "player_ghost": player_ghost if prestige_passed else None,
            "wild_ghost_config": wild_ghost_config if prestige_passed else None
        }

    @staticmethod
    async def execute_battle_phase(
        session: AsyncSession,
        player: Player,
        invasion: GhostInvasion,
        player_ghost: PlayerGhost,
        wild_ghost_config: dict
    ) -> dict:
        """
        战斗阶段
        返回: {"success": bool, "message": str, "drops": Optional[List[str]]}
        """
        result_messages = []

        # 数值战斗
        result_messages.append("⚔️ 进入战斗阶段：")
        victory, battle_desc, damage = GhostSuppressionService.simulate_battle(
            player_ghost, player, wild_ghost_config
        )
        result_messages.append(battle_desc)

        if not victory:
            return {"success": False, "message": "\n".join(result_messages), "drops": None}

        # 战利品获取
        result_messages.append("\n💎 战利品获取：")
        drops = []

        # 计算碎片掉落
        from .ghost_utils import GhostUtils

        drop_rate = wild_ghost_config["fragment_drop_rate"]
        if random.random() < drop_rate:
            fragment_id = wild_ghost_config["fragment_item_id"]
            rarity = wild_ghost_config.get("rarity", "common")
            drop_count = GhostUtils.get_fragment_drop_count(rarity)

            drops.append(fragment_id)

            # 添加到玩家背包
            try:
                await ItemInstance.add_item(session, player.id, fragment_id, drop_count)
                fragment_config = config.items_config["by_id"].get(fragment_id)
                fragment_name = fragment_config.name if fragment_config else fragment_id
                result_messages.append(f"🎁 获得 {fragment_name} x{drop_count}")
            except ValueError as e:
                result_messages.append(f"⚠️ 背包空间不足，无法获得战利品")
        else:
            result_messages.append("💔 很遗憾，这次没有获得任何碎片")

        # 标记入侵事件为已镇压
        invasion.suppress(player.id)
        session.add(invasion)

        return {"success": True, "message": "\n".join(result_messages), "drops": drops}