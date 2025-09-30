"""
战斗引擎模块

提供完整的战斗流程处理，包括回合制战斗、连击、反击等复杂逻辑
"""

import random
from typing import Dict, List, Tuple, Optional
from ..models.player import Player
from .battle_attributes import BattleAttributeCalculator, BattleEffectProcessor


class BattleEngine:
    """战斗引擎"""
    
    def __init__(self, seed: Optional[str] = None):
        """初始化战斗引擎
        
        Args:
            seed: 随机种子，用于确定性战斗
        """
        if seed:
            import hashlib
            self.rng = random.Random(hashlib.md5(seed.encode()).hexdigest())
        else:
            self.rng = random.Random()
    
    def execute_player_turn(self, attacker: Player, defender, base_attack: int,
                           is_skill: bool = False) -> Dict:
        """执行玩家回合攻击

        Args:
            attacker: 攻击者玩家
            defender: 防御者（Player或怪物）
            base_attack: 基础攻击力
            is_skill: 是否为技能攻击

        Returns:
            攻击结果字典
        """
        # 使用固定的基础伤害，不再有随机波动
        base_damage = base_attack
        
        # 处理攻击效果
        if hasattr(defender, 'defense'):  # 对玩家
            attack_result = BattleEffectProcessor.process_attack(
                attacker, defender, base_damage, is_skill, self.rng
            )
        else:  # 对怪物，使用简化逻辑
            attack_result = self._process_monster_attack(
                attacker, defender, base_damage, is_skill
            )
        
        # 处理连击
        if not is_skill and attack_result["combo_count"] > 1:
            attack_result["combo_attacks"] = []
            total_damage = attack_result["damage"]
            
            # 执行额外的连击
            for i in range(attack_result["combo_count"] - 1):
                combo_damage = int(base_damage * 0.85)  # 连击伤害固定为85%
                
                if hasattr(defender, 'defense'):
                    combo_result = BattleEffectProcessor.process_attack(
                        attacker, defender, combo_damage, False, self.rng
                    )
                else:
                    combo_result = self._process_monster_attack(
                        attacker, defender, combo_damage, False
                    )
                
                attack_result["combo_attacks"].append(combo_result)
                if combo_result["hit"]:
                    total_damage += combo_result["damage"]
            
            attack_result["total_damage"] = total_damage
        else:
            attack_result["total_damage"] = attack_result["damage"] if attack_result["hit"] else 0
        
        return attack_result
    
    def _process_monster_attack(self, attacker: Player, monster_stats: Dict, 
                               base_damage: int, is_skill: bool) -> Dict:
        """处理对怪物的攻击（简化版）
        
        Args:
            attacker: 攻击者玩家
            monster_stats: 怪物属性字典
            base_damage: 基础伤害
            is_skill: 是否为技能攻击
            
        Returns:
            攻击结果字典
        """
        attacker_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)
        
        result = {
            "hit": False,
            "damage": 0,
            "is_critical": False,
            "is_penetration": False,
            "combo_count": 1,
            "effects": []
        }
        
        # 命中判定（怪物闪避率固定为0，敏捷只影响先后手）
        monster_dodge_rate = 0.0  # 怪物闪避率固定为0

        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs["accuracy_rate"], monster_dodge_rate
        )
        
        if self.rng.random() > hit_chance:
            result["effects"].append("被闪避")
            return result
        
        result["hit"] = True
        
        # 穿透比例计算
        penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
            attacker_attrs["penetration_rate"]
        )
        if penetration_ratio > 0:
            result["is_penetration"] = True
            result["penetration_ratio"] = penetration_ratio
        
        # 暴击判定（考虑怪物抗暴率）
        crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
        monster_anti_crit_rate = monster_stats.get("anti_crit_rate", 0)

        # 计算实际暴击率（玩家暴击率 - 怪物抗暴率）
        effective_crit_rate = max(0, crit_rate - monster_anti_crit_rate)
        is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, self.rng)
        result["is_critical"] = is_critical
        
        # 连击判定（仅普攻）
        if not is_skill:
            combo_count = BattleAttributeCalculator.roll_combo_attack(
                attacker_attrs["combo_rate"], self.rng
            )
            result["combo_count"] = combo_count
        
        # 伤害计算
        final_damage = base_damage
        
        # 应用暴击
        if is_critical:
            final_damage = BattleAttributeCalculator.calculate_critical_damage(
                final_damage, attacker_attrs["critical_power"]
            )
            result["effects"].append("CRITICAL")
        
        # 应用穿透和防御
        monster_defense = monster_stats.get("defense", 0)
        if penetration_ratio > 0:
            from ..utils import apply_defense_mitigation

            mitigation = apply_defense_mitigation(
                final_damage, monster_defense, penetration_ratio
            )
            final_damage = mitigation["final_damage"]
            result["effects"].append("PENETRATION")
        else:
            from ..utils import apply_defense_mitigation

            mitigation = apply_defense_mitigation(final_damage, monster_defense)
            final_damage = mitigation["final_damage"]

        result["damage"] = final_damage
        return result
    
    def check_counter_attack(self, defender: Player, attacker_stats: Dict) -> Optional[Dict]:
        """检查并执行反击
        
        Args:
            defender: 防御者玩家
            attacker_stats: 攻击者属性字典
            
        Returns:
            反击结果字典，如果没有反击则返回None
        """
        if not BattleEffectProcessor.check_counter_attack(defender, self.rng):
            return None
        
        # 执行反击攻击
        counter_damage = int(defender.attack * 0.85)  # 反击伤害固定为85%
        
        if isinstance(attacker_stats, Player):
            # 对玩家反击
            counter_result = BattleEffectProcessor.process_attack(
                defender, attacker_stats, counter_damage, False, self.rng
            )
        else:
            # 对怪物反击
            counter_result = self._process_monster_attack(
                defender, attacker_stats, counter_damage, False
            )
        
        counter_result["is_counter"] = True
        return counter_result
    
    def format_attack_result(self, attacker_name: str, defender_name: str, 
                           result: Dict, is_counter: bool = False) -> List[str]:
        """格式化攻击结果为显示文本
        
        Args:
            attacker_name: 攻击者名称
            defender_name: 防御者名称
            result: 攻击结果字典
            is_counter: 是否为反击
            
        Returns:
            格式化的文本列表
        """
        messages = []
        action = "反击" if is_counter else "攻击"
        
        if not result["hit"]:
            messages.append(f"⚡ {attacker_name} {action} {defender_name}，但被敏捷地闪避了！")
            return messages
        
        # 基础攻击信息
        damage_text = f"{result['damage']}"
        effects = []
        
        if result["is_critical"]:
            effects.append("💥 暴击！")

        if result.get("is_penetration", False):
            effects.append("🗡️ 穿透！")

        effect_text = "".join(effects) if effects else ""
        
        if result.get("combo_count", 1) > 1:
            # 连击攻击
            messages.append(f"{effect_text}{attacker_name} 对 {defender_name} 发动连击！")
            messages.append(f"第1击造成 {damage_text} 伤害")
            
            combo_attacks = result.get("combo_attacks", [])
            for i, combo in enumerate(combo_attacks, 2):
                if combo["hit"]:
                    combo_effects = []
                    if combo["is_critical"]:
                        combo_effects.append("💥 暴击！")
                    if combo.get("is_penetration", False):
                        combo_effects.append("🗡️ 穿透！")
                    combo_effect_text = "".join(combo_effects)
                    messages.append(f"第{i}击 {combo_effect_text}造成 {combo['damage']} 伤害")
                else:
                    messages.append(f"第{i}击被闪避！")
            
            total_damage = result.get("total_damage", result["damage"])
            messages.append(f"连击总伤害: {total_damage}")
        else:
            # 单次攻击
            messages.append(f"{effect_text}{attacker_name} {action} {defender_name}，造成 {damage_text} 伤害")
        
        return messages
