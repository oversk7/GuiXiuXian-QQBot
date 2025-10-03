"""
增强战斗引擎 - 集成状态效果和触发系统
基于现有battle_engine.py扩展，不替换原有逻辑
"""

import random
from typing import Dict, List, Optional, Any, Tuple
from ..models.player import Player
from .battle_engine import BattleEngine
from .battle_attributes import BattleAttributeCalculator
from .battle_effects import (
    BattleEffectManager, TriggerType, EffectType, BattleEffect, 
    TriggerConfig, parse_triggers_from_yaml, format_effect_message
)


class EnhancedBattleEngine(BattleEngine):
    """增强战斗引擎 - 支持状态效果和触发系统"""
    
    def __init__(self, seed: Optional[str] = None):
        """初始化增强战斗引擎"""
        super().__init__(seed)
        self.effect_manager = BattleEffectManager()
        self.turn_counter = 0
        self.battle_log: List[str] = []
    
    def start_battle(self, player: Player, enemy: Any, player_equipped_items: List = None):
        """战斗开始，初始化效果和触发器
        
        Args:
            player: 玩家对象
            enemy: 敌人(Player或怪物字典)
            player_equipped_items: 玩家装备的物品列表
        """
        self.turn_counter = 0
        self.battle_log = []
        
        # 清除旧效果
        self.effect_manager.clear_effects(player.id)
        enemy_id = enemy.id if hasattr(enemy, 'id') else "enemy"
        self.effect_manager.clear_effects(enemy_id)
        
        # 注册玩家装备的触发器
        if player_equipped_items:
            self._register_equipment_triggers(player.id, player_equipped_items)

        # 触发首回合效果
        triggered = self.effect_manager.check_triggers(player.id, TriggerType.FIRST_TURN, {
            "source": "战斗开始",
            "current_hp": player.hp,
            "max_hp": player.max_hp
        })

        for effect in triggered:
            self.effect_manager.add_effect(player.id, effect)
    
    def _register_equipment_triggers(self, unit_id: str, equipped_items: List):
        """注册装备的触发器"""
        for item in equipped_items:
            # 从装备配置中获取special_effects
            config = item.config if hasattr(item, 'config') else None
            if not config:
                continue
            
            special_effects = getattr(config, 'special_effects', None)
            if not special_effects:
                continue
            
            # 解析触发器配置
            triggers = parse_triggers_from_yaml(special_effects)
            
            # 为每个触发器添加来源信息
            for trigger in triggers:
                if not trigger.description:
                    trigger.description = f"{config.name}的特殊效果"
            
            self.effect_manager.register_triggers(unit_id, triggers)
    
    def execute_turn(self, attacker: Player, defender: Any, is_player_turn: bool = True) -> Dict:
        """执行一个回合，包含效果处理

        Args:
            attacker: 攻击者
            defender: 防御者
            is_player_turn: 是否为玩家回合

        Returns:
            回合结果字典，包含 damage_dealt 和 hp_restored
        """
        self.turn_counter += 1
        turn_result = {
            "turn": self.turn_counter,
            "messages": [],
            "damage_dealt": 0,
            "hp_restored": 0,  # 新增：记录恢复的HP
            "effects_triggered": []
        }
        
        attacker_id = attacker.id
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"

        # 回合开始效果
        turn_start_msgs, turn_start_hp = self._process_turn_start(attacker_id, attacker)
        turn_result["messages"].extend(turn_start_msgs)
        turn_result["hp_restored"] += turn_start_hp
        
        # 检查是否被控制
        if self.effect_manager.has_control_effect(attacker_id):
            turn_result["messages"].append(f"⛓️ {attacker.nickname}被定身，无法行动")
            return turn_result
        
        # 执行攻击
        attack_result = self._execute_enhanced_attack(attacker, defender, is_player_turn)
        turn_result["messages"].extend(attack_result["messages"])
        turn_result["damage_dealt"] = attack_result.get("total_damage", 0)
        turn_result["hp_restored"] = attack_result.get("hp_restored", 0)  # 新增：传递恢复的HP
        turn_result["effects_triggered"] = attack_result.get("effects_triggered", [])

        return turn_result
    
    def _process_turn_start(self, unit_id: str, unit: Any) -> Tuple[List[str], int]:
        """处理回合开始效果

        Returns:
            (消息列表, 恢复的HP)
        """
        messages = []
        hp_restored = 0

        # 触发每回合效果
        triggered = self.effect_manager.check_triggers(unit_id, TriggerType.EACH_TURN, {
            "source": "回合开始",
            "current_hp": getattr(unit, 'hp', 100),
            "max_hp": getattr(unit, 'max_hp', 100)
        })

        for effect in triggered:
            self.effect_manager.add_effect(unit_id, effect)
            messages.append(format_effect_message(effect, unit.nickname if hasattr(unit, 'nickname') else "敌人"))

        # 处理回血效果
        regen_effects = self.effect_manager.get_active_effects(unit_id, EffectType.REGEN)
        total_regen = 0
        for effect in regen_effects:
            regen_amount = int(getattr(unit, 'max_hp', 100) * effect.value / 100)
            total_regen += regen_amount

        if total_regen > 0:
            hp_restored += total_regen
            messages.append(f"💚 {unit.nickname if hasattr(unit, 'nickname') else '敌人'}回复{total_regen}生命值")

        # 效果持续时间递减
        tick_msgs = self.effect_manager.tick_effects(unit_id)
        messages.extend(tick_msgs)

        return messages, hp_restored
    
    def _execute_enhanced_attack(self, attacker: Player, defender: Any,
                                is_player_turn: bool) -> Dict:
        """执行增强攻击，包含触发效果"""
        result = {
            "messages": [],
            "total_damage": 0,
            "hp_restored": 0,  # 新增：记录恢复的HP
            "effects_triggered": []
        }
        
        attacker_id = attacker.id
        defender_id = defender.id if hasattr(defender, 'id') else "enemy"
        attacker_name = attacker.nickname
        defender_name = defender.nickname if hasattr(defender, 'nickname') else defender.get("name", "敌人")
        
        # 获取属性修正
        attack_modifier = self.effect_manager.calculate_attribute_modifier(attacker_id, "attack")
        
        # 计算基础攻击力(应用属性修正)
        base_attack = int(attacker.attack * (1 + attack_modifier / 100))
        
        # 执行基础攻击
        if hasattr(defender, 'defense'):
            # 对玩家
            from .battle_attributes import BattleEffectProcessor
            attack_result = BattleEffectProcessor.process_attack(
                attacker, defender, base_attack, False, self.rng
            )
        else:
            # 对怪物
            attack_result = self._process_monster_attack(
                attacker, defender, base_attack, False
            )
        
        # 格式化基础攻击消息
        if not attack_result["hit"]:
            result["messages"].append(f"⚡ {attacker_name}攻击{defender_name}，但被闪避了")
            
            # 触发闪避效果(防御方)
            dodge_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_DODGE, {
                "source": "闪避成功",
                "current_hp": getattr(defender, 'hp', 100),
                "max_hp": getattr(defender, 'max_hp', 100)
            })
            
            for effect in dodge_effects:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(format_effect_message(effect, defender_name))
                result["effects_triggered"].append(effect.effect_type.value)
            
            return result
        
        # 命中
        damage = attack_result["damage"]
        is_critical = attack_result.get("is_critical", False)
        
        # 构建攻击消息
        attack_msg = f"⚔️ {attacker_name}攻击{defender_name}"
        if is_critical:
            attack_msg += " 💥暴击！"
        attack_msg += f" 造成{damage}伤害"
        result["messages"].append(attack_msg)
        result["total_damage"] = damage
        
        # 触发攻击时效果
        context = {
            "source": attacker_name,
            "damage": damage,
            "is_critical": is_critical,
            "current_hp": attacker.hp,
            "max_hp": attacker.max_hp
        }
        
        attack_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_ATTACK, context)
        
        # 如果暴击，触发暴击效果
        if is_critical:
            crit_effects = self.effect_manager.check_triggers(attacker_id, TriggerType.ON_CRITICAL, context)
            attack_effects.extend(crit_effects)
        
        # 处理触发的效果
        for effect in attack_effects:
            # 立即生效的效果
            if effect.effect_type == EffectType.LIFESTEAL:
                lifesteal_amount = int(damage * effect.value / 100)
                # 实际恢复HP（不超过最大值）
                result["hp_restored"] += lifesteal_amount
                result["messages"].append(f"🧡 吸血恢复{lifesteal_amount}生命值")
                result["effects_triggered"].append("lifesteal")

            elif effect.effect_type == EffectType.TRUE_DAMAGE:
                true_damage = int(damage * effect.value / 100)
                result["total_damage"] += true_damage
                result["messages"].append(f"🔥 真实伤害额外造成{true_damage}伤害")
                result["effects_triggered"].append("true_damage")

            elif effect.effect_type == EffectType.IMMOBILIZE:
                # 对敌人施加定身效果
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(format_effect_message(effect, defender_name))
                result["effects_triggered"].append("immobilize")

            elif effect.duration > 0:
                # 持续性效果
                self.effect_manager.add_effect(attacker_id, effect)
                result["messages"].append(format_effect_message(effect, attacker_name))
                result["effects_triggered"].append(effect.effect_type.value)
        
        # 触发防御时效果(被攻击方)
        defense_effects = self.effect_manager.check_triggers(defender_id, TriggerType.ON_DEFENSE, {
            "source": defender_name,
            "damage": damage,
            "current_hp": getattr(defender, 'hp', 100),
            "max_hp": getattr(defender, 'max_hp', 100)
        })
        
        for effect in defense_effects:
            if effect.effect_type == EffectType.REFLECT:
                # 反弹伤害
                reflect_damage = int(damage * effect.value / 100)
                result["messages"].append(f"↩️ {defender_name}反弹{reflect_damage}伤害给{attacker_name}")
                result["effects_triggered"].append("reflect")
            else:
                self.effect_manager.add_effect(defender_id, effect)
                result["messages"].append(format_effect_message(effect, defender_name))
                result["effects_triggered"].append(effect.effect_type.value)
        
        return result
    
    def get_battle_log(self) -> List[str]:
        """获取战斗日志"""
        return self.battle_log.copy()
    
    def format_battle_summary(self) -> str:
        """格式化战斗摘要"""
        return "\n".join(self.battle_log)
