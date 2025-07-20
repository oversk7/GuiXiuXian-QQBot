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
        required_attr = ghost_config["required_attribute"]
        attr_per_level = ghost_config["attribute_per_level"]
        base_level = ghost_config["base_prestige_level"]
        
        # 获取玩家对应属性值
        player_attr_value = getattr(player, required_attr, 0)
        bonus_levels = player_attr_value // attr_per_level
        
        return base_level + bonus_levels
    
    @staticmethod
    def simulate_battle(player_ghost_config: dict, player: Player, wild_ghost_config: dict) -> Tuple[bool, str, int]:
        """
        模拟战斗
        返回: (是否胜利, 战斗描述, 造成伤害)
        """
        # 计算双方属性
        player_hp = player_ghost_config["hp"] + player.hp // 2
        player_attack = player_ghost_config["attack"] + player.attack
        player_defense = player_ghost_config["defense"] + player.defense
        player_agility = player_ghost_config["agility"] + player.agility
        
        wild_hp = wild_ghost_config["hp"]
        wild_attack = wild_ghost_config["attack"]
        wild_defense = wild_ghost_config["defense"]
        wild_agility = wild_ghost_config["agility"]
        
        # 简化战斗计算
        battle_log = []
        rounds = 0
        max_rounds = 10
        
        while player_hp > 0 and wild_hp > 0 and rounds < max_rounds:
            rounds += 1
            
            # 敏捷决定先手
            if player_agility >= wild_agility:
                # 玩家先攻
                damage = max(1, player_attack - wild_defense + random.randint(-5, 5))
                wild_hp -= damage
                battle_log.append(f"第{rounds}回合：你的{player_ghost_config['name']}造成{damage}点伤害")
                
                if wild_hp <= 0:
                    break
                
                # 野生鬼反击
                damage = max(1, wild_attack - player_defense + random.randint(-5, 5))
                player_hp -= damage
                battle_log.append(f"野生{wild_ghost_config['name']}反击造成{damage}点伤害")
            else:
                # 野生鬼先攻
                damage = max(1, wild_attack - player_defense + random.randint(-5, 5))
                player_hp -= damage
                battle_log.append(f"第{rounds}回合：野生{wild_ghost_config['name']}造成{damage}点伤害")
                
                if player_hp <= 0:
                    break
                
                # 玩家反击
                damage = max(1, player_attack - wild_defense + random.randint(-5, 5))
                wild_hp -= damage
                battle_log.append(f"你的{player_ghost_config['name']}反击造成{damage}点伤害")
        
        victory = wild_hp <= 0
        total_damage = wild_ghost_config["hp"] - max(0, wild_hp)
        
        battle_description = "\n".join(battle_log)
        if victory:
            battle_description += f"\n🎉 镇压成功！野生{wild_ghost_config['name']}被彻底击败！"
        else:
            battle_description += f"\n💀 镇压失败！你的{player_ghost_config['name']}不敌对手..."
        
        return victory, battle_description, total_damage
    
    @staticmethod
    async def attempt_suppression(
        session: AsyncSession, 
        player: Player, 
        invasion: GhostInvasion,
        use_coffin_nail: bool = False
    ) -> Tuple[bool, str, Optional[List[str]]]:
        """
        尝试镇压鬼怪
        返回: (是否成功, 详细描述, 掉落物品列表)
        """
        # 获取鬼怪配置
        wild_ghost_config = config.ghosts_config["by_id"].get(invasion.ghost_id)
        if not wild_ghost_config:
            return False, "❌ 未知的鬼怪类型", None
        
        # 获取玩家当前驾驭的鬼怪
        player_ghost = await GhostSuppressionService.get_player_active_ghost(session, player.id)
        if not player_ghost:
            return False, "❌ 你没有驾驭任何鬼，能对付鬼的只有鬼，请先通过【试炼】领取鬼", None
        
        player_ghost_config = config.ghosts_config["by_id"].get(player_ghost.ghost_id)
        if not player_ghost_config:
            return False, "❌ 你驾驭的鬼怪配置异常", None
        
        result_messages = []
        
        # 第一阶段：威压判定
        player_prestige = GhostSuppressionService.calculate_prestige_level(player_ghost_config, player)
        wild_prestige = wild_ghost_config["base_prestige_level"]
        
        result_messages.append(f"🔥 威压对决：")
        result_messages.append(f"你的{player_ghost_config['name']} 威压等级: {player_prestige}")
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
            return False, "\n".join(result_messages), None
        
        # 第二阶段：数值战斗
        result_messages.append("\n⚔️ 进入战斗阶段：")
        victory, battle_desc, damage = GhostSuppressionService.simulate_battle(
            player_ghost_config, player, wild_ghost_config
        )
        result_messages.append(battle_desc)
        
        if not victory:
            return False, "\n".join(result_messages), None
        
        # 第三阶段：战利品获取
        result_messages.append("\n💎 战利品获取：")
        drops = []
        
        # 计算碎片掉落
        drop_rate = wild_ghost_config["fragment_drop_rate"]
        if random.random() < drop_rate:
            fragment_id = wild_ghost_config["fragment_item_id"]
            drop_count = 1
            
            # 根据稀有度调整掉落数量
            rarity = wild_ghost_config.get("rarity", "common")
            if rarity == "rare":
                drop_count = random.randint(1, 2)
            elif rarity == "epic":
                drop_count = random.randint(2, 3)
            elif rarity == "legendary":
                drop_count = random.randint(3, 5)
            
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
        
        return True, "\n".join(result_messages), drops
