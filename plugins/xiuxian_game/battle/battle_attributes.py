"""
战斗属性计算模块

提供战斗属性的计算、判定和效果处理功能
"""

import random
from typing import Dict, Tuple, Optional
from ..models.player import Player


class BattleAttributeCalculator:
    """战斗属性计算器"""
    
    # 属性上限配置
    ATTRIBUTE_CAPS = {
        "critical_rate": 500,      # 暴击率
        "combo_rate": 60,         # 连击率上限60%
        "counter_rate": 80,       # 反击率上限80%
        "dodge_rate": 500,         # 闪避率
        "accuracy_rate": 500,     # 命中率能和闪避率抵消，所以可以超过100
        "skill_crit_rate": 70,    # 灵爆率上限70%
        "penetration_rate": 100,   # 穿透率
        "anti_crit_rate": 500     # 抗暴率上限
    }
    
    # 等级加成配置（移除等级加成，改为装备驱动）
    LEVEL_BONUS = {
        "critical_rate": 0.0,     # 不再有等级加成
        "combo_rate": 0.0,        # 不再有等级加成
        "counter_rate": 0.0,      # 不再有等级加成
        "dodge_rate": 0.0,        # 不再有等级加成
        "accuracy_rate": 0.0,     # 不再有等级加成
        "skill_crit_rate": 0.0,   # 不再有等级加成
        "penetration_rate": 0.0   # 不再有等级加成
    }
    
    @classmethod
    def calculate_effective_attributes(cls, player: Player, equipment_bonus: Optional[Dict] = None) -> Dict[str, float]:
        """计算玩家的有效战斗属性
        
        Args:
            player: 玩家对象
            equipment_bonus: 装备加成字典（可选）
            
        Returns:
            包含所有战斗属性的字典，值为百分比（0-100）
        """
        attributes = {}
        
        # 基础属性名称映射
        base_attrs = {
            "critical_rate": player.critical_rate,
            "critical_power": player.critical_power,
            "combo_rate": player.combo_rate,
            "counter_rate": player.counter_rate,
            "dodge_rate": player.dodge_rate,
            "accuracy_rate": player.accuracy_rate,
            "skill_crit_rate": player.skill_crit_rate,
            "penetration_rate": player.penetration_rate,
            "anti_crit_rate": player.anti_crit_rate
        }
        
        for attr_name, base_value in base_attrs.items():
            # 基础值
            total_value = float(base_value)
            
            # 等级加成
            level_bonus = cls.LEVEL_BONUS.get(attr_name, 0) * (player.level - 1)
            total_value += level_bonus
            
            # 装备加成
            if equipment_bonus and attr_name in equipment_bonus:
                total_value += equipment_bonus[attr_name]
            
            # 应用上限
            cap = cls.ATTRIBUTE_CAPS.get(attr_name, 100)
            total_value = min(total_value, cap)
            
            # 确保不为负数
            total_value = max(0, total_value)
            
            attributes[attr_name] = total_value
            
        return attributes
    
    @classmethod
    def calculate_hit_chance(cls, attacker_accuracy: float, defender_dodge: float) -> float:
        """计算命中概率
        
        Args:
            attacker_accuracy: 攻击者命中率(%)
            defender_dodge: 防御者闪避率(%)
            
        Returns:
            最终命中概率(0-1)
        """
        hit_chance = (attacker_accuracy - defender_dodge) / 100.0
        
        hit_chance = max(0.1, min(1.0, hit_chance))
        
        return hit_chance
    
    @classmethod
    def roll_critical_hit(cls, crit_rate: float, rng: random.Random = None) -> bool:
        """判定是否暴击
        
        Args:
            crit_rate: 暴击率(%)
            rng: 随机数生成器
            
        Returns:
            是否触发暴击
        """
        if rng is None:
            rng = random
        
        return rng.random() < (crit_rate / 100.0)
    
    @classmethod
    def roll_combo_attack(cls, combo_rate: float, rng: random.Random = None) -> int:
        """判定连击次数
        
        Args:
            combo_rate: 连击率(%)
            rng: 随机数生成器
            
        Returns:
            连击次数（1表示无连击，2-4表示连击次数）
        """
        if rng is None:
            rng = random
            
        if rng.random() < (combo_rate / 100.0):
            # 触发连击，随机2-4次
            return rng.randint(2, 4)
        
        return 1  # 无连击
    
    @classmethod
    def roll_counter_attack(cls, counter_rate: float, rng: random.Random = None) -> bool:
        """判定是否反击
        
        Args:
            counter_rate: 反击率(%)
            rng: 随机数生成器
            
        Returns:
            是否触发反击
        """
        if rng is None:
            rng = random
            
        return rng.random() < (counter_rate / 100.0)
    
    @classmethod
    def get_penetration_ratio(cls, penetration_rate: float) -> float:
        """获取穿透比例

        Args:
            penetration_rate: 穿透率(%)，直接作为穿透比例

        Returns:
            穿透比例（0-1，0表示无穿透，1表示完全穿透）
        """
        # 穿透率直接转换为穿透比例，不再有随机性
        return min(penetration_rate / 100.0, 1.0)
    
    @classmethod
    def calculate_critical_damage(cls, base_damage: int, crit_power: int = 0) -> int:
        """计算暴击伤害

        Args:
            base_damage: 基础伤害
            crit_power: 暴击力（每点增加0.1倍伤害）

        Returns:
            暴击后的伤害
        """
        # 基础暴击倍数1.5，暴击力每点增加0.1倍
        crit_multiplier = 1.5 + (crit_power * 0.1)
        return int(base_damage * crit_multiplier)

    @classmethod
    def determine_turn_order(cls, player_agility: int, monster_agility: int, rng: random.Random = None) -> bool:
        """根据敏捷值判定先后手

        Args:
            player_agility: 玩家敏捷值
            monster_agility: 怪物敏捷值
            rng: 随机数生成器

        Returns:
            True表示玩家先手，False表示怪物先手
        """
        if rng is None:
            rng = random

        # 敏捷差距越大，先手概率越高
        # 基础公式：玩家先手概率 = 玩家敏捷 / (玩家敏捷 + 怪物敏捷)
        total_agility = player_agility + monster_agility
        if total_agility == 0:
            return rng.random() < 0.5  # 如果都是0，随机决定

        player_first_chance = player_agility / total_agility

        # 添加一些随机性，避免完全确定性
        # 最终概率在 [0.1, 0.9] 之间
        player_first_chance = max(0.1, min(0.9, player_first_chance))

        return rng.random() < player_first_chance


class BattleEffectProcessor:
    """战斗效果处理器"""
    
    @classmethod
    def process_attack(cls, attacker: Player, defender: Player, base_damage: int, 
                      is_skill: bool = False, rng: random.Random = None) -> Dict:
        """处理一次攻击的所有效果
        
        Args:
            attacker: 攻击者
            defender: 防御者
            base_damage: 基础伤害
            is_skill: 是否为技能攻击
            rng: 随机数生成器
            
        Returns:
            攻击结果字典
        """
        if rng is None:
            rng = random
            
        # 获取双方战斗属性
        attacker_attrs = BattleAttributeCalculator.calculate_effective_attributes(attacker)
        defender_attrs = BattleAttributeCalculator.calculate_effective_attributes(defender)
        
        result = {
            "hit": False,
            "damage": 0,
            "is_critical": False,
            "is_penetration": False,
            "combo_count": 1,
            "effects": []
        }
        
        # 1. 命中判定
        hit_chance = BattleAttributeCalculator.calculate_hit_chance(
            attacker_attrs["accuracy_rate"], 
            defender_attrs["dodge_rate"]
        )
        
        if rng.random() > hit_chance:
            result["effects"].append("被闪避")
            return result
        
        result["hit"] = True
        
        # 2. 穿透比例计算
        penetration_ratio = BattleAttributeCalculator.get_penetration_ratio(
            attacker_attrs["penetration_rate"]
        )
        if penetration_ratio > 0:
            result["is_penetration"] = True
            result["penetration_ratio"] = penetration_ratio
        
        # 3. 暴击判定（考虑防御方抗暴率）
        crit_rate = attacker_attrs["skill_crit_rate"] if is_skill else attacker_attrs["critical_rate"]
        defender_anti_crit_rate = defender_attrs["anti_crit_rate"]

        # 计算实际暴击率（攻击方暴击率 - 防御方抗暴率）
        effective_crit_rate = max(0, crit_rate - defender_anti_crit_rate)
        is_critical = BattleAttributeCalculator.roll_critical_hit(effective_crit_rate, rng)
        result["is_critical"] = is_critical
        
        # 4. 连击判定（仅普攻）
        if not is_skill:
            combo_count = BattleAttributeCalculator.roll_combo_attack(
                attacker_attrs["combo_rate"], rng
            )
            result["combo_count"] = combo_count
        
        # 5. 伤害计算
        final_damage = base_damage
        
        # 应用暴击
        if is_critical:
            final_damage = BattleAttributeCalculator.calculate_critical_damage(
                final_damage, attacker_attrs["critical_power"]
            )
            result["effects"].append("CRITICAL")
        
        # 应用穿透
        if penetration_ratio > 0:
            # 穿透部分无视防御，非穿透部分正常计算防御
            from ..utils import damage_reduction_rate
            normal_reduction = damage_reduction_rate(defender.defense)
            penetration_reduction = normal_reduction * (1 - penetration_ratio)
            final_damage = max(1, int(final_damage * (1 - penetration_reduction)))
            result["effects"].append("PENETRATION")
        else:
            # 正常防御计算
            from ..utils import damage_reduction_rate
            damage_reduction = damage_reduction_rate(defender.defense)
            final_damage = max(1, int(final_damage * (1 - damage_reduction)))
        
        result["damage"] = final_damage
        
        return result
    
    @classmethod
    def check_counter_attack(cls, defender: Player, rng: random.Random = None) -> bool:
        """检查是否触发反击
        
        Args:
            defender: 防御者
            rng: 随机数生成器
            
        Returns:
            是否触发反击
        """
        defender_attrs = BattleAttributeCalculator.calculate_effective_attributes(defender)
        return BattleAttributeCalculator.roll_counter_attack(
            defender_attrs["counter_rate"], rng
        )
