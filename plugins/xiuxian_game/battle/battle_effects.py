"""
战斗效果系统 - 状态效果(Buff/Debuff)和触发系统
支持持续性效果、效果叠加、触发条件判定等
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import random


class TriggerType(str, Enum):
    """触发类型"""
    ON_ATTACK = "on_attack"          # 攻击时触发
    ON_DEFENSE = "on_defense"        # 防御时触发(被攻击时)
    ON_CRITICAL = "on_critical"      # 暴击时触发
    ON_DODGE = "on_dodge"           # 闪避成功时触发
    ON_KILL = "on_kill"             # 击杀敌人时触发
    FIRST_TURN = "first_turn"       # 战斗首回合触发
    EACH_TURN = "each_turn"         # 每回合开始时触发
    LOW_HP = "low_hp"               # 低血量时触发(<=30%)
    ON_HIT = "on_hit"               # 命中时触发


class EffectType(str, Enum):
    """效果类型"""
    # 伤害相关
    LIFESTEAL = "lifesteal"         # 吸血(基于造成伤害的百分比恢复HP)
    TRUE_DAMAGE = "true_damage"     # 真实伤害(持续状态，攻击完全无视防御)
    DAMAGE_BOOST = "damage_boost"   # 伤害提升(百分比加成)

    # 控制相关
    FEAR = "fear"                   # 恐惧(无法行动)

    # 属性增益
    BUFF_ATTACK = "buff_attack"     # 攻击力提升
    BUFF_DEFENSE = "buff_defense"   # 防御力提升
    BUFF_CRITICAL = "buff_critical" # 暴击率提升
    BUFF_DODGE = "buff_dodge"       # 闪避率提升
    BUFF_ACCURACY = "buff_accuracy" # 命中率提升

    # 属性削弱
    DEBUFF_ATTACK = "debuff_attack"     # 攻击力降低
    DEBUFF_DEFENSE = "debuff_defense"   # 防御力降低

    # 回复相关
    REGEN = "regen"                 # 每回合回血
    HEAL = "heal"                   # 立即回血

    # 特殊效果
    SHIELD = "shield"               # 护盾
    REFLECT = "reflect"             # 反弹伤害
    INVINCIBLE = "invincible"       # 无敌

    # 复杂连锁效果（天退星刀专用）
    TIGER_BULLET = "tiger_bullet"           # 虎标弹：造成伤害提高(计数型)
    FIERCE_TIGER_BULLET = "fierce_tiger_bullet"  # 猛虎标弹：虎标弹失效后激活
    RIGID_QI_HEART = "rigid_qi_heart"       # 刚气-心：猛虎标弹失效后触发


@dataclass
class BattleEffect:
    """战斗效果数据类"""
    effect_type: EffectType
    value: float                    # 效果数值(可以是百分比或固定值)
    duration: int = 0               # 持续回合数(0表示立即生效)
    stacks: int = 1                 # 当前叠加层数
    max_stacks: int = 1             # 最大叠加层数
    source: str = ""                # 效果来源(装备名称等)
    description: str = ""           # 效果描述
    is_percentage: bool = True      # 是否为百分比值
    trigger_count: int = 0          # 触发计数器（用于计数型效果，如虎标弹）
    max_trigger_count: int = 0      # 最大触发次数（0表示无限制）
    next_effect: str = ""           # 失效后触发的下一个效果类型

    def apply_stack(self, new_value: float = None) -> bool:
        """叠加效果"""
        if self.stacks < self.max_stacks:
            self.stacks += 1
            if new_value is not None:
                self.value += new_value
            return True
        return False

    def tick(self) -> bool:
        """回合结算，返回是否还有效"""
        if self.duration > 0:
            self.duration -= 1
        return self.duration > 0 or self.duration == -1  # -1表示永久效果

    def consume_trigger(self) -> bool:
        """消耗一次触发次数，返回是否还有剩余次数"""
        if self.max_trigger_count <= 0:
            return True  # 无限制
        self.trigger_count += 1
        return self.trigger_count < self.max_trigger_count


@dataclass
class TriggerConfig:
    """触发配置"""
    trigger: TriggerType
    chance: float                   # 触发概率(0-100)
    effect: EffectType
    value: float = 0                # 效果数值
    duration: int = 0               # 持续回合数
    max_stacks: int = 1             # 最大叠加层数
    threshold: float = 0            # 触发阈值(如低血量百分比)
    description: str = ""
    is_percentage: bool = True      # 是否为百分比值
    max_trigger_count: int = 0      # 最大触发次数（0表示无限制）
    next_effect: str = ""           # 失效后触发的下一个效果类型
    next_effect_value: float = 0    # 下一个效果的数值
    next_effect_duration: int = 0   # 下一个效果的持续时间


class BattleEffectManager:
    """战斗效果管理器"""
    
    def __init__(self):
        # 存储每个战斗单位的效果 {unit_id: [BattleEffect, ...]}
        self.active_effects: Dict[str, List[BattleEffect]] = {}
        # 存储每个战斗单位的触发配置 {unit_id: [TriggerConfig, ...]}
        self.trigger_configs: Dict[str, List[TriggerConfig]] = {}
    
    def add_effect(self, unit_id: str, effect: BattleEffect) -> bool:
        """添加效果到单位"""
        if unit_id not in self.active_effects:
            self.active_effects[unit_id] = []

        # 检查是否已存在相同类型的效果
        for existing in self.active_effects[unit_id]:
            if existing.effect_type == effect.effect_type and existing.source == effect.source:
                # 尝试叠加
                if existing.apply_stack(effect.value if effect.is_percentage else None):
                    return True
                else:
                    # 无法叠加，刷新持续时间
                    existing.duration = max(existing.duration, effect.duration)
                    return True

        # 添加新效果
        self.active_effects[unit_id].append(effect)
        return True

    def remove_effect(self, unit_id: str, effect: BattleEffect) -> bool:
        """移除指定效果

        Args:
            unit_id: 单位ID
            effect: 要移除的效果对象

        Returns:
            是否成功移除
        """
        if unit_id not in self.active_effects:
            return False

        try:
            self.active_effects[unit_id].remove(effect)
            return True
        except ValueError:
            return False
    
    def register_triggers(self, unit_id: str, triggers: List[TriggerConfig]):
        """注册触发器"""
        if unit_id not in self.trigger_configs:
            self.trigger_configs[unit_id] = []
        self.trigger_configs[unit_id].extend(triggers)
    
    def check_triggers(self, unit_id: str, trigger_type: TriggerType,
                      context: Dict[str, Any]) -> List[BattleEffect]:
        """检查并触发效果"""
        triggered_effects = []

        if unit_id not in self.trigger_configs:
            return triggered_effects

        for trigger_config in self.trigger_configs[unit_id]:
            if trigger_config.trigger != trigger_type:
                continue

            # 检查触发条件
            if not self._check_condition(trigger_config, context):
                continue

            # 概率判定
            if random.random() * 100 > trigger_config.chance:
                continue

            # 创建效果
            effect = BattleEffect(
                effect_type=trigger_config.effect,
                value=trigger_config.value,
                duration=trigger_config.duration,
                max_stacks=trigger_config.max_stacks,
                source=context.get("source", "未知"),
                description=trigger_config.description,
                is_percentage=trigger_config.is_percentage,
                max_trigger_count=trigger_config.max_trigger_count,
                next_effect=trigger_config.next_effect
            )

            triggered_effects.append(effect)

        return triggered_effects
    
    def _check_condition(self, trigger: TriggerConfig, context: Dict[str, Any]) -> bool:
        """检查触发条件"""
        if trigger.trigger == TriggerType.LOW_HP:
            current_hp = context.get('current_hp', 100)
            max_hp = context.get('max_hp', 100)
            hp_percentage = (current_hp / max_hp) * 100 if max_hp > 0 else 0
            return hp_percentage <= (trigger.threshold or 30)
        
        return True
    
    def get_active_effects(self, unit_id: str, effect_type: EffectType = None) -> List[BattleEffect]:
        """获取单位的活跃效果"""
        if unit_id not in self.active_effects:
            return []
        
        if effect_type:
            return [e for e in self.active_effects[unit_id] if e.effect_type == effect_type]
        
        return self.active_effects[unit_id].copy()
    
    def tick_effects(self, unit_id: str) -> List[str]:
        """回合结算效果，返回消息列表"""
        messages = []
        
        if unit_id not in self.active_effects:
            return messages
        
        # 处理持续效果
        effects_to_remove = []
        for effect in self.active_effects[unit_id]:
            if not effect.tick():
                effects_to_remove.append(effect)
                messages.append(f"✨ {effect.description} 效果结束")
        
        # 移除过期效果
        for effect in effects_to_remove:
            self.active_effects[unit_id].remove(effect)
        
        return messages
    
    def clear_effects(self, unit_id: str):
        """清除单位所有效果"""
        if unit_id in self.active_effects:
            self.active_effects[unit_id].clear()
        if unit_id in self.trigger_configs:
            self.trigger_configs[unit_id].clear()
    
    def has_control_effect(self, unit_id: str) -> bool:
        """检查单位是否被控制(恐惧等)"""
        if unit_id not in self.active_effects:
            return False

        control_effects = [EffectType.FEAR]
        for effect in self.active_effects[unit_id]:
            if effect.effect_type in control_effects:
                return True

        return False
    
    def calculate_attribute_modifier(self, unit_id: str, attr_name: str) -> float:
        """计算属性修正值(百分比)"""
        if unit_id not in self.active_effects:
            return 0.0

        # 映射属性名到效果类型
        attr_effect_map = {
            "attack": (EffectType.BUFF_ATTACK, EffectType.DEBUFF_ATTACK),
            "defense": (EffectType.BUFF_DEFENSE, EffectType.DEBUFF_DEFENSE),
            "critical_rate": (EffectType.BUFF_CRITICAL, None),
            "dodge_rate": (EffectType.BUFF_DODGE, None),
            "accuracy_rate": (EffectType.BUFF_ACCURACY, None),
        }

        if attr_name not in attr_effect_map:
            return 0.0

        buff_type, debuff_type = attr_effect_map[attr_name]
        total_modifier = 0.0

        for effect in self.active_effects[unit_id]:
            if effect.effect_type == buff_type:
                total_modifier += effect.value * effect.stacks
            elif debuff_type and effect.effect_type == debuff_type:
                total_modifier -= effect.value * effect.stacks

        return total_modifier

    def get_active_effects(self, unit_id: str, effect_type: EffectType = None) -> List[BattleEffect]:
        """获取单位的活跃效果

        Args:
            unit_id: 单位ID
            effect_type: 效果类型(可选，不指定则返回所有效果)

        Returns:
            效果列表
        """
        if unit_id not in self.active_effects:
            return []

        if effect_type is None:
            return self.active_effects[unit_id].copy()

        return [e for e in self.active_effects[unit_id] if e.effect_type == effect_type]


def parse_triggers_from_yaml(special_effects: List[Dict]) -> List[TriggerConfig]:
    """从YAML配置解析触发器"""
    triggers = []

    for effect_data in special_effects:
        try:
            trigger = TriggerConfig(
                trigger=TriggerType(effect_data.get("trigger", "on_attack")),
                chance=float(effect_data.get("chance", 100)),
                effect=EffectType(effect_data.get("effect", "damage_boost")),
                value=float(effect_data.get("value", 0)),
                duration=int(effect_data.get("duration", 0)),
                max_stacks=int(effect_data.get("max_stacks", 1)),
                threshold=float(effect_data.get("threshold", 0)),
                description=effect_data.get("description", ""),
                is_percentage=effect_data.get("is_percentage", True),
                max_trigger_count=int(effect_data.get("max_trigger_count", 0)),
                next_effect=effect_data.get("next_effect", ""),
                next_effect_value=float(effect_data.get("next_effect_value", 0)),
                next_effect_duration=int(effect_data.get("next_effect_duration", 0))
            )
            triggers.append(trigger)
        except (ValueError, KeyError) as e:
            # 配置错误时跳过
            continue

    return triggers


def format_effect_message(effect: BattleEffect, target_name: str, is_trigger: bool = True) -> str:
    """格式化效果消息"""
    emoji_map = {
        EffectType.LIFESTEAL: "🧡",
        EffectType.TRUE_DAMAGE: "🔥",
        EffectType.FEAR: "😱",
        EffectType.BUFF_ATTACK: "⚔️",
        EffectType.BUFF_DEFENSE: "🛡️",
        EffectType.BUFF_CRITICAL: "💥",
        EffectType.BUFF_DODGE: "⚡",
        EffectType.BUFF_ACCURACY: "🎯",
        EffectType.DEBUFF_ATTACK: "🔻",
        EffectType.DEBUFF_DEFENSE: "📉",
        EffectType.REGEN: "💚",
        EffectType.HEAL: "💚",
        EffectType.SHIELD: "🛡️",
        EffectType.REFLECT: "↩️",
        EffectType.INVINCIBLE: "✨"
    }

    emoji = emoji_map.get(effect.effect_type, "✨")

    # 根据效果类型生成描述
    if effect.effect_type == EffectType.FEAR:
        msg = f"{emoji} {target_name}被恐惧{effect.duration}回合"
    elif effect.effect_type == EffectType.LIFESTEAL:
        msg = f"{emoji} 吸血{effect.value:.0f}%"
    elif effect.effect_type == EffectType.TRUE_DAMAGE:
        msg = f"{emoji} {target_name}进入真伤状态(持续{effect.duration}回合)"
    elif effect.effect_type in [EffectType.BUFF_ATTACK, EffectType.BUFF_DEFENSE,
                                EffectType.BUFF_CRITICAL, EffectType.BUFF_DODGE,
                                EffectType.BUFF_ACCURACY]:
        attr_name = {
            EffectType.BUFF_ATTACK: "攻击力",
            EffectType.BUFF_DEFENSE: "防御力",
            EffectType.BUFF_CRITICAL: "暴击率",
            EffectType.BUFF_DODGE: "闪避率",
            EffectType.BUFF_ACCURACY: "命中率",
        }.get(effect.effect_type, "属性")

        stack_info = f"(第{effect.stacks}层)" if effect.max_stacks > 1 else ""
        duration_info = f"{effect.duration}回合" if effect.duration > 0 else "永久"
        msg = f"{emoji} {target_name}{attr_name}+{effect.value:.0f}%{stack_info}，持续{duration_info}"
    elif effect.effect_type == EffectType.REGEN:
        msg = f"{emoji} {target_name}每回合回复{effect.value:.0f}%生命值"
    elif effect.effect_type == EffectType.SHIELD:
        msg = f"{emoji} {target_name}获得{effect.value:.0f}点护盾"
    elif effect.description:
        msg = f"{emoji} {effect.description}"
    else:
        msg = f"{emoji} 未知效果"

    return msg
