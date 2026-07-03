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
        "anti_crit_rate": 500,    # 抗暴率上限
        "anti_combo_rate": 500,   # 抗连击率上限
        "anti_counter_rate": 500  # 抗反击率上限
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
            "anti_crit_rate": player.anti_crit_rate,
            "anti_combo_rate": player.anti_combo_rate,
            "anti_counter_rate": player.anti_counter_rate,
            "lifesteal_rate": getattr(player, 'lifesteal_rate', 0),
            "immobilize_rate": getattr(player, 'immobilize_rate', 0),
            "true_damage_rate": getattr(player, 'true_damage_rate', 0),
            "regen_rate": getattr(player, 'regen_rate', 0),
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
    def effective_attrs_in_battle(cls, player: "Player") -> Dict[str, float]:
        """战斗内获取玩家战斗属性：优先使用开战时预计算的缓存

        _cached_battle_attrs 由开战入口用 calculate_effective_attributes_async
        预计算（含临时buff/宠物/T1词缀，已应用上限）。战斗循环内的同步判定
        必须走本方法而非 calculate_effective_attributes，否则吃不到这些加成。
        """
        cached = getattr(player, "_cached_battle_attrs", None)
        if cached is not None:
            return dict(cached)
        return cls.calculate_effective_attributes(player)

    @classmethod
    async def calculate_effective_attributes_async(cls, player: "Player", session=None, equipment_bonus: Optional[Dict] = None) -> Dict[str, float]:
        """计算玩家的有效战斗属性（异步版本，包含临时buff）

        Args:
            player: 玩家对象
            session: 数据库会话（用于获取临时buff）
            equipment_bonus: 装备加成字典（可选）

        Returns:
            包含所有战斗属性的字典，值为百分比（0-100）
        """
        # 获取包含临时buff的有效属性
        if session:
            effective_attrs = await player.get_effective_attributes(session)
        else:
            # 如果没有session，回退到基础属性
            effective_attrs = {
                "critical_rate": player.critical_rate,
                "critical_power": player.critical_power,
                "combo_rate": player.combo_rate,
                "counter_rate": player.counter_rate,
                "dodge_rate": player.dodge_rate,
                "accuracy_rate": player.accuracy_rate,
                "skill_crit_rate": player.skill_crit_rate,
                "penetration_rate": player.penetration_rate,
                "anti_crit_rate": player.anti_crit_rate,
                "anti_combo_rate": player.anti_combo_rate,
                "anti_counter_rate": player.anti_counter_rate,
                "lifesteal_rate": getattr(player, 'lifesteal_rate', 0),
                "immobilize_rate": getattr(player, 'immobilize_rate', 0),
                "true_damage_rate": getattr(player, 'true_damage_rate', 0),
                "regen_rate": getattr(player, 'regen_rate', 0),
            }

        attributes = {}

        # 基础属性名称映射
        base_attrs = {
            "critical_rate": effective_attrs["critical_rate"],
            "critical_power": effective_attrs["critical_power"],
            "combo_rate": effective_attrs["combo_rate"],
            "counter_rate": effective_attrs["counter_rate"],
            "dodge_rate": effective_attrs["dodge_rate"],
            "accuracy_rate": effective_attrs["accuracy_rate"],
            "skill_crit_rate": effective_attrs["skill_crit_rate"],
            "penetration_rate": effective_attrs["penetration_rate"],
            "anti_crit_rate": effective_attrs["anti_crit_rate"],
            "anti_combo_rate": effective_attrs["anti_combo_rate"],
            "anti_counter_rate": effective_attrs["anti_counter_rate"],
            "lifesteal_rate": effective_attrs.get("lifesteal_rate", 0),
            "immobilize_rate": effective_attrs.get("immobilize_rate", 0),
            "true_damage_rate": effective_attrs.get("true_damage_rate", 0),
            "regen_rate": effective_attrs.get("regen_rate", 0),
        }

        for attr_name, base_value in base_attrs.items():
            # 基础值（已包含临时buff）
            total_value = float(base_value)

            # 等级加成
            level_bonus = cls.LEVEL_BONUS.get(attr_name, 0) * (player.level - 1)
            total_value += level_bonus

            # 额外装备加成（如果有的话）
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
    def check_counter_attack(cls, defender: Player, rng: random.Random = None,
                             attacker_anti_counter: float = 0) -> bool:
        """检查是否触发反击

        Args:
            defender: 防御者
            rng: 随机数生成器
            attacker_anti_counter: 攻击方抗反击率（与 enhanced_engine.check_counter_attack 语义一致）

        Returns:
            是否触发反击
        """
        defender_attrs = BattleAttributeCalculator.effective_attrs_in_battle(defender)
        effective_counter = max(0, defender_attrs["counter_rate"] - attacker_anti_counter)
        return BattleAttributeCalculator.roll_counter_attack(
            effective_counter, rng
        )
