"""
战斗系统集成助手

提供将新战斗属性系统集成到现有战斗逻辑中的工具函数
"""

import random
from typing import Dict, List, Tuple, Optional
from ..models.player import Player
from .battle_engine import BattleEngine


class BattleIntegrationHelper:
    """战斗系统集成助手"""
    
    @staticmethod
    def enhanced_player_vs_monster_battle(
        player: Player,
        monster_stats: Dict,
        monster_name: str,
        seed: Optional[str] = None,
        max_rounds: int = 20
    ) -> Tuple[bool, List[str], int]:
        """增强版玩家vs怪物战斗

        Args:
            player: 玩家对象
            monster_stats: 怪物属性字典 {"hp": int, "attack": int, "defense": int, "agility": int}
            monster_name: 怪物名称
            seed: 随机种子
            max_rounds: 最大回合数

        Returns:
            (是否胜利, 战斗日志, 玩家受到的伤害)
        """
        engine = BattleEngine(seed)
        battle_log = []

        # 初始化战斗状态
        player_hp = player.hp
        monster_hp = monster_stats["hp"]
        initial_player_hp = player_hp

        battle_log.append(f"⚔️ {player.nickname} VS {monster_name}")
        
        # 判定先后手（基于敏捷）
        from .battle_attributes import BattleAttributeCalculator
        player_first = BattleAttributeCalculator.determine_turn_order(
            player.agility, monster_stats.get("agility", 10), engine.rng
        )

        for round_num in range(1, max_rounds + 1):
            if player_hp <= 0 or monster_hp <= 0:
                break

            round_actions = []  # 紧凑模式的单行显示

            # 根据先后手判定执行攻击顺序
            if player_first:
                # 玩家先手
                if player_hp > 0 and monster_hp > 0:
                    player_attack_result = engine.execute_player_turn(
                        player, monster_stats, player.attack, is_skill=False
                    )

                    if player_attack_result["hit"]:
                        monster_hp = max(0, monster_hp - player_attack_result["total_damage"])
                        # 紧凑格式：显示效果和总伤害
                        effects = []
                        if player_attack_result["is_critical"]:
                            effects.append("💥")
                        if player_attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{player_attack_result['combo_count']}")
                        if player_attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)
                        round_actions.append(f"{effect_text}{player.nickname}→{player_attack_result['total_damage']}")
                    else:
                        round_actions.append(f"{player.nickname}→MISS")

                # 怪物反击（如果存活）
                if monster_hp > 0 and player_hp > 0:
                    monster_attack_result = BattleIntegrationHelper._monster_attack_player(
                        monster_stats, player, engine
                    )

                    if monster_attack_result["hit"]:
                        player_hp = max(0, player_hp - monster_attack_result["damage"])
                        # 紧凑模式：显示伤害和格挡信息
                        if monster_attack_result["blocked"] > 0:
                            round_actions.append(f"{monster_name}→{monster_attack_result['damage']}🛡️{monster_attack_result['blocked']}")
                        else:
                            round_actions.append(f"{monster_name}→{monster_attack_result['damage']}")
                    else:
                        round_actions.append(f"{monster_name}→MISS")
            else:
                # 怪物先手攻击
                monster_attack_result = BattleIntegrationHelper._monster_attack_player(
                    monster_stats, player, engine
                )

                if monster_attack_result["hit"]:
                    player_hp = max(0, player_hp - monster_attack_result["damage"])
                    # 紧凑模式：显示伤害和格挡信息
                    if monster_attack_result["blocked"] > 0:
                        round_actions.append(f"{monster_name}→{monster_attack_result['damage']}🛡️{monster_attack_result['blocked']}")
                    else:
                        round_actions.append(f"{monster_name}→{monster_attack_result['damage']}")

                    # 检查反击
                    if player_hp > 0:
                        counter_result = engine.check_counter_attack(player, monster_stats)
                        if counter_result:
                            monster_hp = max(0, monster_hp - counter_result["total_damage"])
                            round_actions.append(f"🛡️反击→{counter_result['total_damage']}")
                else:
                    round_actions.append(f"{monster_name}→MISS")

                # 玩家反击（如果存活且怪物未死）
                if player_hp > 0 and monster_hp > 0:
                    player_attack_result = engine.execute_player_turn(
                        player, monster_stats, player.attack, is_skill=False
                    )

                    if player_attack_result["hit"]:
                        monster_hp = max(0, monster_hp - player_attack_result["total_damage"])
                        # 紧凑格式：显示效果和总伤害
                        effects = []
                        if player_attack_result["is_critical"]:
                            effects.append("💥")
                        if player_attack_result.get("combo_count", 1) > 1:
                            effects.append(f"🔄x{player_attack_result['combo_count']}")
                        if player_attack_result.get("is_penetration", False):
                            effects.append("🗡️")

                        effect_text = "".join(effects)
                        round_actions.append(f"{effect_text}{player.nickname}→{player_attack_result['total_damage']}")
                    else:
                        round_actions.append(f"{player.nickname}→MISS")


            # 将回合动作合并为一行
            if round_actions:
                battle_log.append(f"R{round_num}: " + " | ".join(round_actions))
        
        # 战斗结果
        victory = monster_hp <= 0
        damage_taken = initial_player_hp - player_hp

        # 紧凑格式的结果显示
        remaining_player_hp = player_hp
        if victory:
            battle_log.append(f"🎉 胜利！{round_num}回合，剩余{remaining_player_hp}血")
        else:
            # 显示失败原因和剩余血量
            remaining_monster_hp = monster_hp
            battle_log.append(f"💀 战败！{round_num}回合，剩余{remaining_player_hp}血，敌剩{remaining_monster_hp}血")

        return victory, battle_log, damage_taken
    
    @staticmethod
    def _monster_attack_player(monster_stats: Dict, player: Player, engine: BattleEngine) -> Dict:
        """怪物攻击玩家的简化逻辑

        Args:
            monster_stats: 怪物属性
            player: 玩家对象
            engine: 战斗引擎

        Returns:
            攻击结果字典
        """
        # 使用固定的怪物基础伤害，不再有随机波动
        base_damage = monster_stats["attack"]

        # 获取玩家战斗属性
        from .battle_attributes import BattleAttributeCalculator
        player_attrs = BattleAttributeCalculator.calculate_effective_attributes(player)

        result = {
            "hit": False,
            "damage": 0,
            "blocked": 0,  # 新增：格挡伤害
            "effects": []
        }

        # 命中判定（怪物命中率固定85%，玩家闪避率来自装备）
        monster_accuracy = 85.0
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            monster_accuracy, player_attrs["dodge_rate"]
        )

        if engine.rng.random() > hit_chance:
            return result

        result["hit"] = True

        # 防御减伤计算
        from ..utils import damage_reduction_rate
        damage_reduction = damage_reduction_rate(player.defense)
        final_damage = max(1, int(base_damage * (1 - damage_reduction)))
        blocked_damage = base_damage - final_damage

        result["damage"] = final_damage
        result["blocked"] = blocked_damage
        return result
    
    @staticmethod
    def create_battle_summary(player: Player, victory: bool, battle_log: List[str], 
                            damage_taken: int, exp_gain: int = 0) -> str:
        """创建战斗总结
        
        Args:
            player: 玩家对象
            victory: 是否胜利
            battle_log: 战斗日志
            damage_taken: 受到的伤害
            exp_gain: 获得的经验
            
        Returns:
            格式化的战斗总结
        """
        summary_lines = []
        
        # 战斗结果
        if victory:
            summary_lines.append("🎉 战斗胜利！")
        else:
            summary_lines.append("💀 战斗失败...")
        
        # 关键战斗日志（最多显示8条）
        key_logs = [log for log in battle_log if any(keyword in log for keyword in 
                   ["暴击", "连击", "反击", "穿透", "闪避", "胜利", "战败", "回合"])]
        
        if len(key_logs) > 8:
            summary_lines.extend(key_logs[:3])
            summary_lines.append("...")
            summary_lines.extend(key_logs[-3:])
        else:
            summary_lines.extend(key_logs)
        
        # 战斗统计
        summary_lines.append("")
        summary_lines.append("📊 战斗统计:")
        summary_lines.append(f"剩余血量: {player.hp}/{player.max_hp}")
        summary_lines.append(f"受到伤害: {damage_taken}")
        
        if exp_gain > 0:
            summary_lines.append(f"获得经验: {exp_gain}")
        
        return "\n".join(summary_lines)
    
    @staticmethod
    def get_battle_attribute_display(player: Player) -> str:
        """获取战斗属性显示
        
        Args:
            player: 玩家对象
            
        Returns:
            格式化的战斗属性显示
        """
        from .battle_attributes import BattleAttributeCalculator
        attrs = BattleAttributeCalculator.calculate_effective_attributes(player)
        
        # 计算暴击倍数显示（基础1.5倍 + 暴击力*0.1倍）
        crit_multiplier = 1.5 + (attrs['critical_power'] * 0.1)

        lines = [
            "⚔️ 战斗属性 ⚔️",
            f"💥 暴击率: {attrs['critical_rate']:.1f}%",
            f"💢 暴击力: {crit_multiplier:.1f}倍",
            f"🔄 连击率: {attrs['combo_rate']:.1f}%",
            f"🛡️ 反击率: {attrs['counter_rate']:.1f}%",
            f"⚡ 闪避率: {attrs['dodge_rate']:.1f}%",
            f"🎯 命中率: {attrs['accuracy_rate']:.1f}%",
            f"✨ 灵爆率: {attrs['skill_crit_rate']:.1f}%",
            f"🗡️ 穿透率: {attrs['penetration_rate']:.1f}%"
        ]
        
        return "\n".join(lines)
